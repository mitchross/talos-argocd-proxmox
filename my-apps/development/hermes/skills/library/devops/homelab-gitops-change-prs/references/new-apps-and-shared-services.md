# New apps and shared services

Rules for adding a new app, a shared in-cluster service, or a multi-PR feature.

## Before designing
- Before adding a shared service (token helper, proxy, model endpoint), exec into the existing consumers and probe whether they already have it working (`curl 127.0.0.1:<port>/ping`, `command -v <runtime>`). A bundled feature can be present but dead (missing runtime → 502), and that finding is the PR's "why".
- Before offering a fix in chat ("I'll throttle X", "I'll set flag Y"), grep the pinned tag for the knob and check live logs that the hypothesis fits. A promised knob that doesn't exist, or a cause the logs contradict, forces a visible change of plan; say so plainly when it happens.
- Placing an iGPU/NPU workload: see `accelerator-placement.md`.

## Networking and storage
- When a consumer's setting takes only an IP (no DNS name), pin the Service `clusterIP` inside the static band at the bottom of the service CIDR (`kubectl get servicecidrs`; for a /12 that's the first 256 addresses). Dynamic allocation avoids that band, so the pin survives cluster rebuilds. Check the IP is free first: `kubectl get svc -A -o jsonpath='{range .items[*]}{.spec.clusterIP}{"\n"}{end}'`.
- One NAS folder shared by apps in different namespaces: an SMB StorageClass with a fixed `subDir`, `onDelete: retain` and `csi.storage.k8s.io/provisioner-secret-*` (csi-driver-smb v1.20 creates the subDir only when a provisioner secret is set; without it the mount of a missing folder fails). Every PVC of that class mounts the same folder. Add `uid=`/`gid=` mount options for non-root writers, because SMB ignores chown. Reference: `media-inbox-smb`.

## Images and programs
- Upstream images whose entrypoint starts as root and drops to `PUID:PGID` with gosu (MeTube, linuxserver-style): when you disable their recursive chown (needed on SMB), dirs the entrypoint `mkdir`s on an emptyDir end up root-owned. Pre-create them in an initContainer (`mkdir -p ... && chown <uid>:<gid> ...`) with the same image.
- A small repo-owned program that needs python3 + ffmpeg can reuse an already-pinned image that ships both (e.g. MeTube's) with `command: [python3, /scripts/x.py]` from a `configMapGenerator`, instead of building a new image. Say why in a one-line comment.
- Test a repo-owned polling/HTTP script before the PR against an in-process mock: start `http.server.HTTPServer` in a `threading.Thread(daemon=True)` inside one Python test file and call the script's `run_once()` (the terminal tool rejects `&` backgrounding). Cover: happy path, second pass is a no-op, backend down, bad input.

## Sequencing and rollout
- Split a multi-part feature into one PR per layer, in dependency order (shared helper → consumer app → model backend → glue/skill). Tell the user the sequence up front and ship PR 1 without waiting for another go-ahead. Later PRs may be opened before earlier ones merge; say "merge after #N" in the body (a PVC on a not-yet-created StorageClass just stays `Pending`).
- After merge, ArgoCD may take ~5 min to pick up new commits and create new Applications. Poll `kubectl -n argocd get application <app> -o jsonpath='{.status.sync.revision}'` against `git log -1 origin/main` before calling anything missing. A LiteLLM `config.yaml` change rolls the LiteLLM pod; a newly added model answers `Invalid model name` until the new pod is Ready, so check pod age and retry before debugging.
- Run one real end-to-end test after merge (e.g. a real file through the whole pipeline) and report measured numbers (speed, latency) instead of estimates.
