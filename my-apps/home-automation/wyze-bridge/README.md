# Wyze Pan v4 bridge

This application configures an RTSP bridge for the Wyze camera named
`shed4k` (model `HL_PAN4`) for Frigate. It uses the pinned September 24, 2026 IDisposable bridge
build, version `4.6.1-beta.1`, with the Pan v4 WebRTC route and ICE-server fix.
[Upstream change](https://github.com/IDisposable/docker-wyze-bridge/commit/c4991b1e6980b94d9ee2636533c97b0d72f73000).

The camera uses Wyze WebRTC signaling; this is not native RTSP firmware and
still requires Wyze authentication and signaling availability. The camera
reported firmware `4.70.7.4397` during the October 2 account discovery.

## Configuration

- `ExternalSecret` reads the existing `wyze-bridge` and
  `wyze-bridge-local-auth` 1Password items. Item fields and Kubernetes Secret
  keys retain their existing names. The Deployment maps `API_ID`/`API_KEY`
  to `WYZE_API_ID`/`WYZE_API_KEY`, and `WB_USERNAME`/`WB_PASSWORD`/`WB_API`
  to `BRIDGE_USERNAME`/`BRIDGE_PASSWORD`/`BRIDGE_API_TOKEN`.
- Web authentication uses `BRIDGE_AUTH=true`. Explicit required Secret refs
  prevent startup with missing credentials. Keep this translation in the
  Deployment: a prior rollout was blocked on `BRIDGE_USERNAME` because the
  live ExternalSecret retained its old mappings despite successful Argo syncs.
- The container web port is `5080`; the Service retains port `5000` and the
  internal route `https://wyze-bridge.vanillax.me`.
- RTSP: `rtsp://wyze-bridge.wyze-bridge.svc.cluster.local:8554/shed4k`
  inside Kubernetes, or `rtsp://192.168.10.46:8554/shed4k` on the LAN.
- Health probes avoid the authenticated homepage. Liveness uses
  `/api/health`; readiness checks the RTSP listener. Neither proves video flows.
- `FILTER_NAMES=SHED4K` selects the observed camera name. Upstream filtering
  falls back to all discovered cameras if nothing matches; it is not an
  access-control boundary. Update it if the Wyze app renames the camera.
- `/config` is ephemeral. Authentication state is regenerated after pod
  replacement. The bridge does not record or take scheduled snapshots;
  Frigate owns recording storage.

## Frigate handoff and verification

Frigate has a `shed` go2rtc stream pointing to the bridge's actual `shed4k`
path, plus a configured `shed` camera. The camera remains disabled until
actual video is verified in the cluster. Local discovery and WebRTC bootstrap
succeeded, but the initial RTSP decode test produced no video. A bridge
`streaming` status alone is insufficient: it can mean only the source was
registered in go2rtc.

After this PR is merged and ArgoCD reconciles, check the bridge and Secret:

```bash
kubectl -n wyze-bridge get deploy,pods,externalsecret
kubectl -n wyze-bridge logs deploy/wyze-bridge --tail=100
kubectl -n wyze-bridge exec deploy/wyze-bridge -- \
  ffprobe -v error -rtsp_transport tcp -timeout 15000000 \
  -show_entries stream=codec_name,width,height,avg_frame_rate -of json \
  rtsp://127.0.0.1:8554/shed4k
kubectl -n wyze-bridge exec deploy/wyze-bridge -- \
  ffmpeg -hide_banner -loglevel warning -rtsp_transport tcp -timeout 15000000 \
  -i rtsp://127.0.0.1:8554/shed4k -map 0:v:0 -an -vf fps=5 \
  -frames:v 150 -f null -
```

Expect one Ready bridge pod, `ExternalSecret` Ready, a video codec and real
width/height from `ffprobe`, and 150 decoded frames without decode errors.
These commands discard video rather than writing recordings.

Once those checks pass, enable `cameras.shed.enabled` in
[Frigate config](../frigate/config.yml) through a follow-up PR. After sync,
verify `shed` reaches 5 detection FPS, live playback works, and a triggered
event creates a decodable recording. Inspect the actual source resolution;
`QUALITY=hd` does not guarantee 4K on Wyze's WebRTC path.

## Rollback

If the bridge fails to authenticate or produces no video, keep the Frigate
camera disabled and set the bridge Deployment back to zero replicas through
a PR. The previous Python image uses different Secret keys and web port;
rolling back the whole migration is safer than reverting only its image.
No firmware flashing or persistent-volume migration is involved.
