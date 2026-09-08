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
uses the bundled SSD MobileNet model through **OpenVINO on CPU**. Video decode
and the existing Nest H.264 re-encode streams also use CPU. The six Nest
streams retain their keyframe workaround; camera stability on this release
must be checked after deployment.

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
OpenVINO detector, and no repeated MQTT authentication or FFmpeg restart
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

### Current Camera Configuration

All cameras are configured with WebRTC protocol:
- `backyard-nest`: WebRTC
- `garage-inside-nest`: WebRTC
- `garage-outside-nest`: WebRTC
- `front-porch-nest`: WebRTC
- `kitchen-nest`: WebRTC
- `living-room-nest`: WebRTC 