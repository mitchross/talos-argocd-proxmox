# Frigate + Google Nest via a custom go2rtc build

## Layout
- App dir `my-apps/home-automation/frigate/`. go2rtc is replaced by an init container (`ghcr.io/mitchross/frigate-go2rtc:<VERSION>`) built from `go2rtc-image/Dockerfile`, which fetches `mitchross/go2rtc` at a pinned commit (branch `frigate-nest`) and runs the patched packages' tests.
- Change the Dockerfile commit, `go2rtc-image/VERSION` and the deployment init tag together. The image is published only from `main`, so the first rollout may sit in `ImagePullBackOff` for a few minutes. The workflow validates the tag with a regex, so a new tag prefix needs the regex widened.
- Streams: `<cam>-nest` (`nest:` WEB_RTC source) and `<cam>-sub` (`ffmpeg:<cam>-nest#video=h264...#hardware=vaapi`). Frigate reads `rtsp://127.0.0.1:8554/<cam>-sub`. The `go2rtc.preload` block keeps every `-nest` and `-sub` stream open.
- Frigate passes the whole `go2rtc:` section through to go2rtc, so go2rtc-only keys like `preload` work.

## The failure loop to recognise
1. Frigate's 20 s no-frame watchdog restarts its reader.
2. go2rtc drops the Nest session and asks Google for a new one (`GenerateWebRtcStream`).
3. Nest sends SPS/PPS and a keyframe only at dial, so the new session is slow to decode, and step 1 fires again.

Signature: per device, many `GenerateWebRtcStream` and few `ExtendWebRtcStream` (healthy is one Generate, then an Extend about every 3 min), RTSP 404 on `<cam>-sub`, and the failing camera rotating over hours. Not Google quota (check SDM metrics for 429s) and not VAAPI (a CPU A/B test changes nothing).

Second failure: Google freezes the video track while Opus audio keeps flowing. A watchdog that counts total bytes never reconnects. Frigate shows `camera_fps` 0, dozens of `reconnects_last_hour`, and ffmpeg logs `Could not find codec parameters ... unspecified size`. Confirm in go2rtc `/api/streams`: the h264 receiver's `bytes` is flat while the opus receiver's grows.

Third failure (one camera only, the re-encoder keeps exiting): the Nest feed switches resolution on its own (adaptive, e.g. 1920x1080 <-> 640x360). The VAAPI re-encode (`#hardware=vaapi`: hwaccel decode + `scale_vaapi`) dies on every size change, so go2rtc logs `producer.go ... error=EOF url="ffmpeg:<cam>-nest..."` dozens of times an hour while the `-nest` video bytes keep growing. Fix: drop `#hardware=vaapi` for that camera's `-sub` only; the CPU path rescales.

Fourth failure (`<cam> exceeded fps limit. Exiting ffmpeg...`, `camera_fps` ~100): a timestamp jump in the restream (from a re-encoder restart or a reconnect) makes Frigate's detect `fps` filter emit duplicate frames to fill the gap. Frigate kills a reader at `camera_fps >= detect.fps + 10` for 3 checks. Look for `DTS discontinuity` / `Non-monotonic DTS` in the dumped ffmpeg lines. Fix: add `-use_wallclock_as_timestamps 1` to the Nest cameras' `ffmpeg.input_args`.

### Probe a feed directly
The Hermes pod has `ffmpeg`/`ffprobe` and can reach the Frigate pod's go2rtc RTSP port. Sample each source for a minute and compare cameras:
```
ffprobe -v error -rtsp_transport tcp -select_streams v:0 -show_entries frame=width,height -of csv=p=0 "rtsp://<podIP>:8554/<cam>-nest?video" | sort | uniq -c
```
More than one size = adaptive feed (third failure). Decode errors like `non-existing PPS` right after joining are normal for Nest and appear on healthy cameras too; compare counts across cameras before blaming one.

## Upstream fixes worth porting (AlexxIT/go2rtc)
- PR #2516 (Inrego, includes #2351 by tillo): ignore pion's transient `disconnected` state for Nest; bind the track to its media, not its codec pointer (Nest answers H264 PT 96+98 and sends on 98); PLI when no keyframe for 5 s; extend retry with backoff; media inactivity watchdog.
- FIR alongside PLI (some Nest models ignore bare PLI, issue #2365).
- Retry config preloads whose first dial fails (issue #2359).
- Our own: the inactivity watchdog counts video receiver bytes only.
- Related issues: #2386 (the loop itself), #2108, #723, #2319 (extend-timer race).

## Checks after a rollout (wait ~30 min)
- Startup log: `go2rtc ... version=1.9.14+dev.<sha>`.
- The current build drops the per-command `[nest]` log lines, so Generate/Extend counts are only available on builds that log them; use the stats below instead.
- `curl http://<podIP>:5000/api/stats`: every enabled camera at its expected fps with low `reconnects_last_hour`. A camera far above its fps (e.g. 100) is the fourth failure, not health. `cpu_usages` lists every process with its cmdline: a detect ffmpeg at >100% CPU or the exact go2rtc `-sub` command line shows up there.
- Count `exceeded fps limit` per camera in Loki (`... |= "exceeded fps limit" | regexp "watchdog\\.(?P<cam>[a-z-]+)"`) next to `No frames received` and the `-sub` `error=EOF` lines; each points at a different failure above. Frigate logs "Ffmpeg process crashed" once per second while a camera is down, but other failure modes log only "No frames received", so don't rely on that count alone.
- `curl http://<podIP>:1984/api/streams`: per-receiver `bytes` growing for video on each `-nest`, and the `-sub` producer's `bytes_recv` growing.
- The `shed` camera is disabled on purpose.

## Recording health ("Unable to keep up with recording segments in cache")
- Mechanism (`frigate/record/maintainer.py`): every 10 s segment sits in `/tmp/cache` until detection has processed past the segment's end (start + ffprobe duration), then it is moved to `/media` or dropped. The warning fires when more than `MAX_SEGMENTS_IN_CACHE` (6) already-processed segments are still cached, and Frigate deletes the oldest. A steady ~1 warning per camera per 10 s means a segment lost every cycle.
- Check `record.alerts/detections.pre_capture` first. With event-only retention, a segment that overlaps no review item stays cached until it ends more than `event_pre_capture` (max of the two) before the processed frame time. So pre_capture + the segment being written must fit in 6 x 10 s: `pre_capture: 60` needs 7 segments and drops one every cycle. Keep pre_capture at 30 s or less. The live value is in `/api/config` → `cameras.<cam>.record`.
- Rule out slow storage and DB from inside the pod before blaming them: `kubectl -n frigate exec deploy/frigate -c frigate -- sh -c 'cp <cache seg> /media/frigate/.t && rm /media/frigate/.t'` timed (healthy: ~0.07 s per 2 MB on the CIFS share), and a `python3 -c` sqlite write + commit on `/config/frigate.db` (healthy: ~10 ms). The image has no `sqlite3` CLI.
- Measure the loss instead of counting warnings: pull `/api/review?after=&before=` and each `/api/<cam>/recordings?after=&before=`, then compute per camera the seconds of review items covered by recording segments and list the gaps. Event-only retention (continuous/motion `days: 0`) means gaps only show where there was activity, so busy cameras look worst.
- Inspect the cache without exec: `talosctl -n <node> list -l /var/lib/kubelet/pods/<podUID>/volumes/kubernetes.io~empty-dir/tmp-cache` shows segments waiting per camera; `talosctl read <path> > x.mp4` then `ffprobe -show_entries format=duration` checks a segment (the newest one is still being written and has no moov atom; skip it).
- Bucket the warning in Loki per hour and find the first second it appeared; all cameras starting in the same second means a shared cause (storage, DB, node), not a camera.
- `frigate-config` holds the SQLite DB. If its Longhorn volume has one replica on another node, an instance-manager restart there gives `no backend available`, the API hangs and the `/api/version` liveness probe kills Frigate. Check `replicas.longhorn.io` for the volume and keep 2 replicas.
- Heavy API queries (days of `/recordings`) are slow on this DB; keep query windows to hours.
