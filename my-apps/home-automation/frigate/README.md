# Frigate with Google Nest Camera Integration

This document outlines the configuration for running Frigate and integrating it with modern (post-2021) Google Nest cameras that use the WebRTC protocol.

## Overview

The integration uses Frigate's bundled `go2rtc` service to connect directly to the Google Smart Device Management (SDM) API. This method is the most reliable and performant, as it bypasses Home Assistant for the camera streams and connects directly to the source.

The setup involves three main components:
1.  **Kubernetes Secrets**: An `ExternalSecret` is used to securely pull the necessary API credentials from a 1Password vault.
2.  **Frigate Deployment**: The deployment is configured to pass these credentials as environment variables to the Frigate container.
3.  **Frigate `config.yml`**: The configuration file defines the `go2rtc` streams using the `nest:` provider, which uses the environment variables to authenticate with Google's API.

## Runtime and upgrade

Git declares Frigate **0.18.2**, pinned by image digest, with one replica on
`node.vanillax.dev/class: mini-pc-dell-ultra` (the bare-metal Dell Pro Micro,
Core Ultra 5 245T). Object detection runs on the **Intel NPU** through OpenVINO.
The Arrow Lake iGPU decodes the camera inputs and runs the go2rtc Nest H.264
re-encode. The Nest streams retain their keyframe workaround. The USB Coral is
no longer used ([#3088](https://github.com/mitchross/talos-argocd-proxmox/issues/3088)).

### Event recording

[config.yml](config.yml) retains alert and detection recordings with 60 seconds
before the event and 180 seconds after it ends. Frigate 0.18 RC2 limits
`pre_capture` to 60 seconds. `retain.mode: all` preserves quiet segments within
that window. Recordings remain available for 10 days; overlapping events can
produce a longer continuous stretch.

Both continuous and general motion retention are zero. Clips therefore follow
Frigate's object review events using each camera's existing tracked objects,
not every pixel change from shadows or moving plants. The camera streams,
decoding, detection, and temporary recording cache remain active so the
pre-event footage is available. This reduces persistent recording writes during
quiet periods; it does not fix Nest reconnect failures or reduce camera battery
use. Changing retention also lets cleanup expire older footage that no longer
matches the policy.

After merge and sync, check both `alerts` and `detections` in `/api/config`
show `pre_capture: 60`, `post_capture: 180`, and `retain.mode: all` for all
cameras. After at least a minute of healthy streaming, trigger a tracked object
event and verify playback covers the lead-in, activity, and three-minute tail.
Quiet periods outside event windows should not accumulate saved recordings.
Missing camera frames cannot be recovered by changing retention.

To restore continuous history, revert this recording-policy change through a
PR. Cleanup-deleted footage cannot be restored by changing the policy back.
See [Frigate recording retention](https://docs.frigate.video/configuration/record/).

### Intel NPU detector and iGPU video

Frigate uses `detectors.ov` with `type: openvino` and `device: NPU`. The NPU
compiles only static-shape models, so the top-level `model` block selects the
bundled SSDLite MobileNet v2 IR (`/openvino-model/ssdlite_mobilenet_v2.xml`,
300×300, NHWC, BGR) and its 91-class label map. A YOLOv9-t export is a later,
optional accuracy upgrade.

The pod requests `npu.intel.com/accel: 1` and `gpu.intel.com/i915: 1`. These
resources come from two device plugins:

| Resource | Plugin | Node selector |
|---|---|---|
| `npu.intel.com/accel` | [`intel-npu-plugin`](../../../infrastructure/gpu/intel-npu-plugin/) | `feature.node.kubernetes.io/custom-pci.intel-npu=true`, set by the NFD [`intel-npu-rule`](../../../infrastructure/scheduling/node-feature-discovery/intel-npu-rule.yaml) |
| `gpu.intel.com/i915` | [`intel-gpu-plugin`](../../../infrastructure/gpu/intel-gpu-plugin/) | `feature.node.kubernetes.io/pci-0300_8086.present=true` |

The NPU also needs the Talos `siderolabs/intel-npu` extension on the node. It
supplies the `intel_vpu` kernel module and the NPU firmware. Frigate bundles
its own NPU userspace; do not mount host NPU libraries. If the host firmware is
older than Frigate's bundled driver, inference fails with
`MAPPED_INFERENCE_VERSION is NOT compatible with the ELF`. Update the Talos
extension in that case. See Frigate's
[Intel NPU host requirements](https://github.com/blakeblackshear/frigate/blob/v0.18.2/docs/docs/configuration/object_detectors.md#intel-npu-requirements).

The Deployment stays `Pending` until the NPU plugin advertises
`npu.intel.com/accel` on the Dell. Argo CD sync waves cannot order Applications
from different ApplicationSets, so this is expected after a fresh sync. The
scheduler places the pod once the resource appears.

`ffmpeg.hwaccel_args: preset-vaapi` decodes the camera inputs on the iGPU.
Frigate's docs recommend QSV presets for the newest Intel generations; VAAPI
also works there and selects the H.264/H.265 profile automatically. The go2rtc
Nest re-encode streams use `#hardware=vaapi`. That replaces the `h264`
libx264 template with the `h264/vaapi` template, which keeps the same 5-frame
GOP. FFmpeg 8 needs an explicit device for this, so `go2rtc.ffmpeg.global`
sets `-vaapi_device /dev/dri/renderD128`. See
[FFmpeg 8 hardware transcoding](https://github.com/blakeblackshear/frigate/blob/v0.18.2/docs/docs/troubleshooting/go2rtc.md#hardware-accelerated-transcoding-with-ffmpeg-8).

After merge and sync, check the NPU resource and the device node:

```bash
kubectl get node mini-pc-dell-ultra-worker -o jsonpath='{.status.allocatable.npu\.intel\.com/accel}{"\n"}'
kubectl -n intel-npu-plugin get pods -o wide
kubectl -n frigate exec deployment/frigate -- ls -l /dev/accel/accel0 /dev/dri/renderD128
kubectl -n frigate exec deployment/frigate -- curl -s http://127.0.0.1:5000/api/stats | jq '.detectors'
```

Expect `1` allocatable NPU, a running plugin pod on the Dell, both device
nodes present, and an `ov` detector with an inference speed near 10 ms.
`intel_gpu_top` on the node should show video decode load. Then watch a 48-hour
soak for detection gaps.

If the NPU fails, check the plugin logs and the firmware message above first.
If go2rtc logs `A hardware device reference is required`, check the render node
path. To roll back, revert the move PR. That restores the Coral detector and
its node selector, so the pod runs again only on a node with a labeled Coral.

### Buffered Nest video input

The six Nest re-encoders use `#input=nest-buffered`, defined under
`go2rtc.ffmpeg`. The template keeps FFmpeg's input buffering, allows a
20-second/20-MB codec probe, uses RTSP over TCP with a 60-second socket timeout,
and limits decoder threads to two. The H264 encoder also uses two threads and
emits a keyframe every five frames (one second at the configured 5 FPS).

The previous go2rtc RTSP defaults combined `nobuffer`, `low_delay`, a five-second
socket timeout, and a 50-frame output GOP. During the offline-feed incident,
raw video sometimes decoded quickly while a derived stream took 28 seconds to
attach, longer than Frigate's 20-second no-frame watchdog. An isolated buffered
restream decoded 1,001 frames over 200 seconds without FFmpeg warnings; two
additional direct Nest sessions each decoded 150 frames without warnings.
Another test ended with an RTSP disconnect, and two streams failed to start.
These tests validate the combined settings on the successful feeds, not which
individual option caused the failures; they do not establish long-term
reliability across all cameras.

After deployment, verify sustained camera FPS and newly recorded playable
segments through multiple Nest renewals. Detector health alone is not a
camera-health check. If this configuration regresses capture, revert the
`go2rtc.ffmpeg` templates and all six `#input=nest-buffered` selectors together
through a PR; keep the NPU detector in place.

### Nest go2rtc override

Frigate's stock go2rtc 1.9.14 connected to Google but repeatedly lost usable
frames with missing H.264 parameter sets and local RTSP 404 errors. This
application supplies [bober10113's recovery follow-up](https://github.com/bober10113/go2rtc/tree/codex/b101-v63-recovery-followup)
at commit `ec152af109f3f2ead77b81650772444a91d3fb44`. The fork adds per-stream
session state, recurring renewal, keyframe requests and recovery coordination
for the derived FFmpeg streams. The follow-up separates successful-publish
observation from retry cooldown, rejects stale recovery callbacks, avoids
repeating completed video warm-up, bounds command-slot waiting, closes failed
WebRTC peers, and classifies Google errors without logging arbitrary response
bodies. It is a community fork, not an upstream release.

The publish regression test reproduces an incorrect 45-second cooldown on the
previous `222d37f` revision and passes on this revision. The image build runs
that test plus Nest command-admission, error-redaction, and failed-peer cleanup
regressions. This fixes verified recovery defects; it does not guarantee that
Google will make every camera available.

`go2rtc-image/Dockerfile` builds that exact revision. The image workflow tests
PRs and publishes `ghcr.io/mitchross/frigate-go2rtc` only from `main`. Change
`go2rtc-image/VERSION` and the init-container image tag together when changing
the image; published tags are not overwritten. The first rollout may wait in
`ImagePullBackOff` until the main-branch image build finishes. The GHCR package
must be public for the cluster's anonymous pull; if a first publish creates a
private package, set package visibility to public before expecting the init
container to start.

The init container copies the binary to an `emptyDir`. Frigate mounts it
read-only at its supported `/config/go2rtc` override path. Nothing is written
to the backed-up config PVC, so a rollback does not leave a custom binary
behind. VPA targets the Frigate container by name.

Verify the startup log identifies `1.9.14+dev.ec152af`, all five cameras maintain
nonzero FPS, and successful `ExtendWebRtcStream` operations continue through
multiple five-minute session windows. Pod readiness alone is insufficient.
The isolated pre-merge trial still saw a stream disconnect and a doorbell
capture timeout despite successful session requests. Sustained production
recovery and recording continuity remain rollout acceptance checks.

To roll back this follow-up, revert the source pin, image VERSION and
init-container tag together through a PR to `b101-222d37f-v1`. Keep the buffered
input templates and NPU configuration in place.

To return to bundled go2rtc, revert the override commit through a PR. That
removes the init container and binary mount while retaining Frigate RC2 and
the database. The next pod uses the bundled binary automatically. This
rollback can restore the known Nest frame-drop problem, but does not require
a database downgrade.

Sources: [0.18 RC2 release and breaking changes](https://github.com/blakeblackshear/frigate/discussions/24215),
[OpenVINO support](https://github.com/blakeblackshear/frigate/blob/v0.18.2/docs/docs/configuration/object_detectors.md#openvino-detector),
[FFmpeg 8 hardware transcoding](https://github.com/blakeblackshear/frigate/blob/v0.18.2/docs/docs/troubleshooting/go2rtc.md#hardware-accelerated-transcoding-with-ffmpeg-8).

The ConfigMap remains the Git-owned configuration; make configuration changes
through PRs. The file declares schema version `0.18-0` and is validated directly
against the RC image, because Frigate cannot migrate the mounted ConfigMap in
place. UI configuration writes are not supported with this mount.

Before upgrade, verify a successful `frigate-config` kopiur snapshot (the
config PVC includes `frigate.db`). The stopped deployment had successful daily
snapshots before this upgrade was prepared. Keep that pre-upgrade snapshot
for rollback: a newer database may not work with an older image.

After merge:

```bash
kubectl -n frigate rollout status deployment/frigate --timeout=180s
kubectl -n frigate get pods -o wide
kubectl -n argocd get application my-apps-frigate
kubectl -n frigate logs deployment/frigate --since=5m
```

Expect a ready Frigate pod on the Dell, ArgoCD Synced/Healthy, a running
NPU detector, and no repeated MQTT authentication or FFmpeg restart
errors. Use the stream check below to verify all five cameras receive frames;
pod readiness alone does not establish that cameras or recordings work.

To stop a failing rollout, submit a PR setting `replicas: 0`. To return to the
older release, revert the upgrade through a PR and restore the pre-upgrade
config/database snapshot if database migrations ran; follow the
[backup/restore architecture](../../../docs/domains/storage/kopiur-backup-architecture.md).
Do not mount a migrated database into the older image without a compatible
restore.

## Credentials and Setup Process

This integration requires a one-time, manual setup process to obtain the necessary credentials from Google.

### Required Credentials

The following credentials must be obtained and stored in a `frigate` item in a 1Password vault:

| 1Password Field        | Description                                     | Origin                           |
| ---------------------- | ----------------------------------------------- | -------------------------------- |
| `nest_client_id`       | OAuth 2.0 Client ID for your web application.   | Google Cloud Console             |
| `nest_client_secret`   | OAuth 2.0 Client Secret for your web application. | Google Cloud Console             |
| `nest_project_id`      | The unique ID for your Device Access project.   | Google Device Access Console     |
| `nest_refresh_token`   | A permanent token to re-authenticate with Google. | Manual OAuth2 OOB Flow           |

### Setup Guide

The definitive guide for this process can be found in the official Frigate GitHub discussions:
[**Nest Cam -> Frigate (Integrated go2rtc) Setup Workflow**](https://github.com/blakeblackshear/frigate/discussions/17527)

Follow **Phase 2, 3, and 4** of that guide carefully. Key steps include:
1.  Creating a Google Cloud Project and enabling the "Smart Device Management API".
2.  Configuring the OAuth Consent Screen and creating an OAuth Client ID.
3.  Creating a Device Access Project and linking it to your Google Cloud project ($5 fee required).
4.  Setting the OAuth app's **Publishing status** to **In production** to ensure the refresh token does not expire.
5.  Performing the manual "Out-of-Band" (OOB) authentication flow with a `curl` command to get the `refresh_token`.
6.  Using a temporary `access_token` to list devices and retrieve the unique `device_id` for each camera.

## Kubernetes Configuration Files

-   **`externalsecret.yaml`**: Defines the `ExternalSecret` resource that maps the credentials from the `frigate` item in 1Password to a native Kubernetes `Secret` named `frigate-secrets`.
-   **`deployment.yaml`**: Mounts the data from the `frigate-secrets` Secret as environment variables (e.g., `FRIGATE_NEST_CLIENT_ID`) into the Frigate container.
-   **`config.yml`**: Contains the primary Frigate configuration. The `go2rtc.streams` section is populated with the `nest:` provider string, which includes placeholders for the environment variables and the unique `device_id` for each camera.

This setup ensures that no sensitive credentials are hardcoded in the repository, adhering to GitOps best practices.

## Troubleshooting

### Common Issues

**401 Unauthorized Errors**
- Ensure the OAuth Consent Screen Publishing status is set to **"In production"** (not "Testing")
- Verify you're using the **enabled** client secret in Google Cloud Console
- Check that the refresh token hasn't expired (tokens in Testing mode expire after 7 days)
- Force refresh the ExternalSecret: `kubectl annotate externalsecret frigate-secrets -n frigate force-sync="$(date +%s)" --overwrite`

**400 Bad Request Errors**
- Try switching the camera protocol from `RTSP` to `WEB_RTC` (or vice versa)
- Most 2021+ Nest cameras work best with `&protocols=WEB_RTC&video=h264&audio=opus`

**Invalid Client Errors**
- Verify the OAuth client has `https://www.google.com` in Authorized redirect URIs
- Ensure client_id and client_secret match the **enabled** secret in Google Cloud Console

### Verifying Camera Streams

Check that all cameras are connected and streaming:

```bash
# Check go2rtc stream status
kubectl exec -n frigate deployment/frigate -- curl -s http://127.0.0.1:1984/api/streams | \
  jq -r 'to_entries[] | select(.key | endswith("-nest")) | "\(.key): \(.value.producers[0].format_name // "not connected") - \(.value.producers[0].bytes_recv // 0) bytes"'
```

Expected output for working cameras:
```
backyard-nest: nest/webrtc - 3921351 bytes
garage-inside-nest: nest/webrtc - 9738102 bytes
garage-outside-nest: nest/webrtc - 10256527 bytes
kitchen-nest: nest/webrtc - 9016256 bytes
living-room-nest: nest/webrtc - 10817595 bytes
```

### Camera inventory and live views

The operator identified these models; Google's device list confirms the names
and mappings below. All seven devices advertise only `WEB_RTC` through SDM.

| Google Home name | Operator-reported model / power | Frigate camera |
| --- | --- | --- |
| Kitchen camera | Nest Cam Indoor, wired | `kitchen` |
| Living Room camera | Nest Cam Indoor, wired | `living-room` |
| Backyard camera | Nest Cam Indoor, wired | `backyard` |
| Garage Inside | Nest Cam Indoor, wired | `garage-inside` |
| Garage camera | Nest Cam Battery, external cable power | `garage-outside` |
| Front Porch doorbell | Nest Doorbell Battery, house doorbell wiring | Not configured (streaming drains the battery) |
| Front Porch doorbell 2 | Nest Doorbell Wired, 3rd generation | Not configured |

Each camera's `live.streams` explicitly selects its existing `-sub` stream.
Without this mapping, Frigate defaults to a stream named after the camera,
which does not exist in this configuration. Recording and detection already
use `-sub`, explaining how recordings can work while live viewing fails.
These derived streams provide video only at 5 FPS; this correction does not
add audio or increase live resolution. See [Frigate live stream selection](https://docs.frigate.video/configuration/live/#setting-streams-for-live-ui).

Keep the battery doorbell out of Frigate: a continuous detect/record stream keeps it
awake and drains it even on house wiring, because house wiring only trickle-charges it.
The externally powered garage camera is a different case. See [Google power behavior](https://support.google.com/googlehome/answer/11830989?hl=en)
and [SDM live-session rules](https://developers.google.com/nest/device-access/traits/device/camera-live-stream#extendwebrtcstream).

### Garage outside and kitchen recovery trial

The externally powered battery-model garage camera and wired kitchen camera
use a 90-second FFmpeg retry interval as a recovery trial. On the deployed Nest bridge,
an independent reader took 40.33 seconds to decode its first frame and then
decoded 50 frames without errors, while Frigate repeatedly restarted its reader
after 20 seconds and produced no fresh recordings. A kitchen reader separately
decoded ten frames without errors in 68.18 seconds during the same failure.

In Frigate RC2, `retry_interval` gates watchdog restarts as well as initial
watchdog startup. It does not change the hard-coded 20-second stale-frame
threshold, so an offline status or stale-frame message can precede an actual
restart. This trial trades slower retries of genuine failures for more time to
finish Nest recovery; it does not fix session negotiation or keyframe delivery.

After merge and sync, verify `garage-outside` and `kitchen` reach their
configured 5 FPS and create fresh, decodable recordings across at least two session renewals.
Check live playback after reopening the viewer as well. If it remains offline
or recovery regresses, remove the affected camera's `retry_interval` through a PR to
restore the default 10-second interval. Keep the other cameras at their current
intervals until this trial establishes a benefit.

### Frigate Pending after a VPA eviction

If all feeds stop and the pod is Pending, check scheduling before debugging
Nest credentials:

```bash
kubectl -n frigate get pods
kubectl -n frigate get events --sort-by=.lastTimestamp
kubectl -n frigate get vpa frigate -o yaml
kubectl describe node -l node.vanillax.dev/class=mini-pc-dell-ultra
```

A verified outage followed `ResizeDeferred`, `EvictedByVPA`, then
`FailedScheduling: Insufficient memory`: VPA requested 3,481,230,109 bytes
when the pinned HP node had only 3,339,704,223 bytes of unreserved memory.
Actual memory usage was lower; scheduler reservations caused the rejection.

The Frigate policy caps memory requests at 3 GiB, retains `RequestsOnly` and
the 8 GiB runtime limit, and excludes the fixed-size binary installer.
Its earlier sync wave applies the policy before the Deployment rollout.
The cap was sized for the old HP node. On 2026-10-23 the Dell had about
14.5 GiB of unreserved memory, but planned control-plane duty
([#3071](https://github.com/mitchross/talos-argocd-proxmox/issues/3071)) will
share it. Recheck node usage before increasing the cap or adding a camera.

`FailedScheduling: Insufficient npu.intel.com/accel` means the NPU plugin is not
advertising the device. Check the plugin as described in
[Intel NPU detector and iGPU video](#intel-npu-detector-and-igpu-video).

After merge and sync, expect a Ready replacement with a memory request no
greater than 3 GiB. If an existing Pending pod retains the old request, wait
for the new capped VPA recommendation before recreating that Pending pod.
Then verify camera FPS and fresh recordings across multiple five-minute Nest
sessions. A Ready pod alone does not prove stream recovery. Roll back policy
changes through a PR, recognizing that restoring the old ceiling can repeat
the scheduling outage.
