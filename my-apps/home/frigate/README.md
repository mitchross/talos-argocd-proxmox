# Frigate with Google Nest Camera Integration

This document outlines the configuration for running Frigate and integrating it with modern (post-2021) Google Nest cameras that use the WebRTC protocol.

## Overview

The integration uses Frigate's bundled `go2rtc` service to connect directly to the Google Smart Device Management (SDM) API. This method is the most reliable and performant, as it bypasses Home Assistant for the camera streams and connects directly to the source.

The setup involves three main components:
1.  **Kubernetes Secrets**: An `ExternalSecret` is used to securely pull the necessary API credentials from a 1Password vault.
2.  **Frigate Deployment**: The deployment is configured to pass these credentials as environment variables to the Frigate container.
3.  **Frigate `config.yml`**: The configuration file defines the `go2rtc` streams using the `nest:` provider, which uses the environment variables to authenticate with Google's API.

## Runtime and upgrade

Git declares Frigate **0.18.0-rc2**, pinned by image digest, with one replica on
`node.vanillax.dev/class: hp-elite-worker` (the HP Elite i5-13500T). Detection
uses the bundled **USB Coral EdgeTPU** model. Video decode
and the existing Nest H.264 re-encode streams also use CPU. The six Nest
streams retain their keyframe workaround; camera stability on this release
must be checked after deployment.

### USB Coral detector

The HP Talos VM receives the USB Coral through Proxmox passthrough. Frigate
mounts `/dev/bus/usb` and uses `detectors.coral` with `type: edgetpu` and
`device: usb`. Its pinned image supplies `/edgetpu_model.tflite`: a 320×320
RGB, NHWC, uint8-input SSD-family model with `/labelmap.txt`. The previous
OpenVINO XML model and BGR preprocessing are incompatible with this detector.

The pod requires the existing `custom-usb.coral-tpu` node label as well as
the HP node class. The NodeFeatureRule recognizes both the bootloader vendor
`1a6e` and initialized vendor `18d1`. The full USB IDs are `1a6e:089a` before
initialization and `18d1:9302` afterward. Mounting the entire USB bus accommodates
device-number changes during firmware loading. Proxmox passthrough must also
survive that re-enumeration; a physical-port mapping can avoid tying it to just
one vendor/product identity.

Use USB 3 and verify the device remains visible after the first inference.
See Frigate's [Coral setup](https://docs.frigate.video/configuration/object_detectors/#edge-tpu-detector)
and [USB troubleshooting](https://docs.frigate.video/troubleshooting/edgetpu/).

After merge and sync, check the pod becomes Ready, logs report `TPU found`,
and `/api/stats` reports a running `coral` detector with nonzero inference
speed. A USB label alone proves enumeration, not successful inference. Video
FPS and playable recordings must still be verified separately; Coral performs
object detection and does not repair Nest video transport or decoding.

If the device disappears, check Proxmox passthrough and the node label first.
To roll back, revert this detector/model, USB mount, and Coral selector change
through a PR to restore the prior CPU OpenVINO configuration. Do not pair the
OpenVINO XML model with an EdgeTPU detector.

### Nest go2rtc override

Frigate's stock go2rtc 1.9.14 connected to Google but repeatedly lost usable
frames with missing H.264 parameter sets and local RTSP 404 errors. This
application supplies [bober10113's session-fix branch](https://github.com/bober10113/go2rtc/tree/codex/b101-nest-sessionfix)
at commit `222d37fef8bdc2c8ce2c304fe5a2d5d3b27eb5dc`. The fork adds per-stream
session state, recurring renewal, keyframe requests and recovery coordination
for the derived FFmpeg streams. It is a community fork, not an upstream release.

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

Verify the startup log identifies `1.9.14+dev.222d37f`, all six cameras maintain
nonzero FPS, and successful `ExtendWebRtcStream` operations continue through
multiple five-minute session windows. Pod readiness alone is insufficient.
The pre-merge single-camera trial is evidence for this source revision, not
proof of long-term stability across every Nest model or on the HP node.

To return to bundled go2rtc, revert the override commit through a PR. That
removes the init container and binary mount while retaining Frigate RC2 and
the database. The next pod uses the bundled binary automatically. This
rollback can restore the known Nest frame-drop problem, but does not require
a database downgrade.

The Talos VM currently advertises no Intel GPU device or Intel GPU resource.
OpenVINO supports Intel integrated GPUs, but switching `device` to `GPU` alone
will not expose the physical GPU. GPU acceleration requires a separate
Proxmox passthrough change, Talos Intel driver/firmware support, and container
access to the render device. Once verified, OpenVINO can use `GPU` and FFmpeg
can use VAAPI. With FFmpeg 8, go2rtc hardware transcodes also require an explicit
`go2rtc.ffmpeg.global: "-vaapi_device /dev/dri/renderD128"` (using the verified
render path).

Sources: [0.18 RC2 release and breaking changes](https://github.com/blakeblackshear/frigate/discussions/24215),
[OpenVINO support](https://github.com/blakeblackshear/frigate/blob/v0.18.0-rc2/docs/docs/configuration/object_detectors.md#openvino-detector),
[FFmpeg 8 hardware transcoding](https://github.com/blakeblackshear/frigate/blob/v0.18.0-rc2/docs/docs/troubleshooting/go2rtc.md#hardware-accelerated-transcoding-with-ffmpeg-8).

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

Expect a ready Frigate pod on the HP Elite, ArgoCD Synced/Healthy, a running
Coral detector, and no repeated MQTT authentication or FFmpeg restart
errors. Use the stream check below to verify all six cameras receive frames;
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
front-porch-nest: nest/webrtc - 306955 bytes
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
| Front Porch doorbell | Nest Doorbell Battery, house doorbell wiring | `front-porch` |
| Front Porch doorbell 2 | Nest Doorbell Wired, 3rd generation | Not configured |

Each camera's `live.streams` explicitly selects its existing `-sub` stream.
Without this mapping, Frigate defaults to a stream named after the camera,
which does not exist in this configuration. Recording and detection already
use `-sub`, explaining how recordings can work while live viewing fails.
These derived streams provide video only at 5 FPS; this correction does not
add audio or increase live resolution. See [Frigate live stream selection](https://docs.frigate.video/configuration/live/#setting-streams-for-live-ui).

The battery doorbell remains battery-operated with house wiring supplying a
trickle charge. Its zero-day continuous retention setting does not stop the
active detect/record input. Google's session extension exception for battery
doorbells also applies despite that wiring. The externally powered garage
camera is a different case. See [Google power behavior](https://support.google.com/googlehome/answer/11830989?hl=en)
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
kubectl describe node talos-prod-cluster-v2-hp-elite-workers-rgkw5s
```

A verified outage followed `ResizeDeferred`, `EvictedByVPA`, then
`FailedScheduling: Insufficient memory`: VPA requested 3,481,230,109 bytes
when the pinned HP node had only 3,339,704,223 bytes of unreserved memory.
Actual memory usage was lower; scheduler reservations caused the rejection.

The Frigate policy caps memory requests at 3 GiB, retains `RequestsOnly` and
the 12 GiB runtime limit, and excludes the fixed-size binary installer.
Its earlier sync wave applies the policy before the Deployment rollout.
This cap fits the observed reservations with about 114 MiB remaining; it is
not a capacity guarantee if other workloads grow. Recheck placement and node
usage before increasing it or adding another continuously decoded camera.

After merge and sync, expect a Ready replacement with a memory request no
greater than 3 GiB. If an existing Pending pod retains the old request, wait
for the new capped VPA recommendation before recreating that Pending pod.
Then verify camera FPS and fresh recordings across multiple five-minute Nest
sessions. A Ready pod alone does not prove stream recovery. Roll back policy
changes through a PR, recognizing that restoring the old ceiling can repeat
the scheduling outage.
