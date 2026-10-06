# Wyze Pan v4 receiver

**Purpose:** Supply the Wyze camera `shed4k` (`HL_PAN4`) to Frigate through RTSP.
**Status:** Deployment plan with local video verification; cluster video verification remains required after sync.

Wyze Bridge owns account login and the existing web interface.
The native `wyze-lake` receiver reads its login state and receives Lake/Agora video without Android.
The published receiver comes from [image PR #8](https://github.com/mitchross/homelab-images/pull/8).
[Deployment](deployment.yaml) pins both images by digest.

## Configuration

- [ExternalSecret](external-secret.yaml) retains the existing 1Password items and Kubernetes Secret keys.
  The Deployment maps these keys to Wyze Bridge's environment names.
- Web login remains at `https://wyze-bridge.vanillax.me`, through Service port `5000` and container port `5080`.
- RTSP uses `rtsp://wyze-bridge.wyze-bridge.svc.cluster.local:8554/shed` inside Kubernetes.
  LAN consumers use `rtsp://192.168.10.46:8554/shed`.
- The receiver owns go2rtc and port `8554`.
  `GO2RTC_URL=http://127.0.0.1:1984` makes Wyze Bridge use that server without starting a second listener.
  The go2rtc API listens only on loopback.
- The receiver starts as a [Kubernetes sidecar](https://kubernetes.io/docs/concepts/workloads/pods/sidecar-containers/).
  Its startup probe waits for the server before Wyze Bridge starts.
  Waiting for video here would prevent Wyze Bridge from writing login state.
- Both containers run as UID/GID `1000`.
  Wyze Bridge writes its private `0600` login file into `/config`.
  The receiver mounts the same directory read-only at `/auth`, so it sees atomic file replacements.
- Login state is ephemeral and regenerates after pod replacement.
  The receiver retries while Wyze Bridge completes login.
  Writable receiver files use bounded temporary volumes; its image filesystem remains read-only.
- `FILTER_NAMES=SHED4K` selects the camera for Wyze Bridge.
  `WYZE_CAMERA_NAME=shed4k` selects it for the receiver.
  Update both values if the Wyze app renames the camera.
- The native stream uses the separate name `shed`.
  This prevents Wyze Bridge's legacy `shed4k` registration from replacing the native producer.
- Receiver readiness checks recent encoded frames; it does not prove downstream decoding.
  Wyze Bridge liveness uses `/api/health`; its readiness checks the RTSP listener.
  [VPA](vpa.yaml) controls Wyze Bridge requests and excludes the fixed receiver resources.

## Verified limits

Local testing received H.265 video at `640x360`, without audio.
The receiver requests this resolution; this setup does not provide 4K.
Late RTSP joins can report missing H.265 references until the next keyframe.
Occasional timestamp warnings can also occur during passthrough.
A successful check must show sustained decoded frames after this initial period.

Wyze Bridge's discovered `shed4k` tile still selects its legacy KVS source.
Use the native `/shed` RTSP stream to test this receiver.
The receiver disables WebRTC; the retained HLS/WebRTC Service ports do not provide native playback.
Wyze authentication and signaling must remain available.

## Cluster verification

Prerequisites: Merge this deployment PR, wait for Argo CD sync, and use an authenticated `kubectl` context.
These commands discard video and do not create recordings.

Check both containers and the existing Secret integration:

```bash
kubectl -n wyze-bridge get deploy,pods,externalsecret
kubectl -n wyze-bridge logs deploy/wyze-bridge -c wyze-bridge --tail=100
kubectl -n wyze-bridge logs deploy/wyze-bridge -c wyze-lake --tail=100
```

Expect both containers Ready and the ExternalSecret Ready.
Expect Wyze Bridge to report `using external go2rtc`.
Expect the receiver to report `video_started` and continued `video_progress`.

Check the native stream after initial publication:

```bash
kubectl -n wyze-bridge exec deploy/wyze-bridge -c wyze-lake -- \
  ffprobe -v error -rtsp_transport tcp -timeout 15000000 \
  -show_entries stream=codec_name,width,height -of json \
  rtsp://127.0.0.1:8554/shed
kubectl -n wyze-bridge exec deploy/wyze-bridge -c wyze-lake -- \
  ffmpeg -hide_banner -loglevel warning -rtsp_transport tcp -timeout 15000000 \
  -i rtsp://127.0.0.1:8554/shed -map 0:v:0 -an -t 20 -progress pipe:1 -f null -
```

Expect `hevc`, width `640`, height `360`, and sustained decoding for 20 seconds.
If the first join returns `404`, wait for initial video publication and repeat the check.
If decoding never starts or repeatedly stops, keep the Frigate camera disabled and inspect both container logs.

[Frigate config](../frigate/config.yml) points its `shed` stream to the native `/shed` path.
The `shed` camera remains disabled until these cluster checks pass.
Enable `cameras.shed.enabled` through a follow-up PR after verification.
Then verify live playback, detection FPS, and a decodable event recording.

## Rollback

Keep the Frigate camera disabled if login or video fails.
Revert this deployment change through a PR to return to the previous single-container Wyze Bridge configuration.
That restores the previous login service; its Pan v4 KVS video path remains unsupported.
This change adds no persistent storage and changes no camera firmware.
