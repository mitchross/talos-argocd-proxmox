# Wyze Pan v4 receiver

**Purpose:** Supply the Wyze camera `shed4k` (`HL_PAN4`) to Frigate through RTSP.
**Status:** Deployment plan with local video verification; cluster video verification remains required after sync.

Wyze Bridge retains the existing web interface and developer API login.
The native `wyze-lake` receiver uses an official Web View session and receives Lake/Agora video without Android.
It refreshes that session independently, so developer API login failures do not block native video.
[Deployment](deployment.yaml) pins both images by digest.

## Configuration

- [ExternalSecret](external-secret.yaml) retains the existing Bridge credentials and Kubernetes Secret keys.
  [Web session Secret](web-session-secret.yaml) reads the concealed `WEB_SESSION` field from `homelab-prod/wyze-bridge`.
  The receiver mounts only this seed Secret; Wyze Bridge does not receive it.
- Web login remains at `https://wyze-bridge.vanillax.me`, through Service port `5000` and container port `5080`.
- RTSP uses `rtsp://wyze-bridge.wyze-bridge.svc.cluster.local:8554/shed` inside Kubernetes.
  LAN consumers use `rtsp://192.168.10.46:8554/shed`.
- The receiver owns go2rtc and port `8554`.
  `GO2RTC_URL=http://127.0.0.1:1984` makes Wyze Bridge use that server without starting a second listener.
  The go2rtc API listens only on loopback.
- The receiver starts as a [Kubernetes sidecar](https://kubernetes.io/docs/concepts/workloads/pods/sidecar-containers/).
  Its startup probe waits for the server before Wyze Bridge starts.
  Receiver readiness checks video separately.
- Both containers run as UID/GID `1000`.
  Wyze Bridge writes its private `0600` login file into `/config`.
  The receiver mounts the same directory read-only at `/auth`, so it sees atomic file replacements.
- Bridge login state remains ephemeral. Web View mode takes priority over the Bridge authentication file.
  `WYZE_WEB_SESSION_FILE=/web-seed/session` reads the initial cookie from a projected Secret.
  `WYZE_WEB_STATE=/session/web/state.json` stores the renewed cookie and account token privately.
  The [64 MiB Longhorn PVC](web-session-pvc.yaml) persists this state across pod replacement.
  The receiver owns state files as UID/GID `1000`, with directory mode `0700` and file mode `0600`.
  [Daily backups](kopiur/wyze-web-session.yaml) use kopiur, CSI snapshots, and restore-before-bind.
  The receiver image filesystem remains read-only; SDK logs and home files remain temporary.
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
Web View session refresh uses Wyze's undocumented web protocol, which can change.
The receiver refreshes account login hourly and renews viewer tokens separately.
Local tests verified decoded video, account refresh, viewer renewal, and recovery after container replacement.
These checks do not establish indefinite session validity. A revoked or expired session requires another official browser login.
Wyze Bridge may still report developer API login errors; this mode does not repair that endpoint.

## Session enrollment and recovery

Use the official Web View service cookie named `session`. Do not use a developer portal token.
The initial seed must exist before merging the deployment PR.

Install `agent-browser` and enable the 1Password CLI desktop integration.
Open a named, visible browser session:

```bash
agent-browser --session wyze-enroll --headed open https://my.wyze.com
```

Complete the official Web View login in that browser. Keep the authenticated `my.wyze.com` tab selected.
Save only its service session cookie to the existing item:

```bash
python3 my-apps/home-automation/wyze-bridge/scripts/save-web-session.py --session wyze-enroll
agent-browser --session wyze-enroll close
```

Expect `Saved concealed WEB_SESSION in homelab-prod/wyze-bridge.`
The helper uses private JSON input and retains the existing password and API fields.
It rejects an item containing a passkey because 1Password JSON editing cannot preserve passkeys.
Approve the 1Password desktop prompt when it appears.
Do not paste cookies into chat, command arguments, Git, or image build contexts.

The ExternalSecret refreshes hourly. The receiver detects projected seed changes without a pod restart.
It retains its rotated cookie on the PVC when the original seed remains unchanged.
After `WebLoginRequired`, repeat enrollment and wait for the Secret update.
Inspect private state metadata without printing its contents.

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
Expect the receiver to report `web_auth_refreshed`, `video_started`, and continued `video_progress`.
Expect `wyze-web-session` Bound and its ExternalSecret Ready.
Check backup resources after sync:

```bash
kubectl -n wyze-bridge get pvc,externalsecret,snapshotpolicy,snapshotschedule,restore
kubectl -n wyze-bridge get secret kopiur-rustfs
kubectl -n wyze-bridge get snapshot
```

The scheduled backup runs at 03:02 cluster time. Confirm its first `Snapshot` reaches `Succeeded` with non-zero files.
A new volume without backup history binds empty; do not rely on recovery until the first backup succeeds.

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
Revert the web-session deployment changes through a PR to return to Bridge-owned receiver authentication.
The previous receiver then waits for a successful developer API login. Its Pan v4 KVS tile remains unsupported.
Keep the PVC and backup manifests when reverting authentication settings to retain the latest session files.
Argo CD pruning a removed PVC deletes the live volume; retained kopiur backups remain in the Kopia repository.
No camera firmware changes are required.
