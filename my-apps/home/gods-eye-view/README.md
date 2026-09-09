# God's Eye View

Private LAN URL: <https://gods-eye-view.vanillax.me>.
ArgoCD discovers `my-apps-gods-eye-view` from this directory after merge.
The HTTPS route uses `gateway-internal-technitium`, which also supplies private
DNS through ExternalDNS. There is no application login or public tunnel route.

## Runtime

The image contains upstream commit
[`759652207fd1279ece97f0f19af566feb9a82146`](https://github.com/bilawalsidhu/gods-eye-view/commit/759652207fd1279ece97f0f19af566feb9a82146)
and its locked npm dependencies. `image/Dockerfile` pins the source archive
checksum and Node 24 base digest. `scripts/start.mjs` is mounted through a
hash-suffixed ConfigMap, so startup changes trigger a rollout.

The application needs the Vite development server: many upstream data proxies
only implement `configureServer`, so a static build or `vite preview` loses
live feeds. The launcher preserves those plugins, restricts accepted hostnames,
disables HMR and filesystem watching, and adds a local `/healthz` endpoint that
does not depend on public feed availability. Source files are read-only; Vite
dependency optimization, data caches, and debug logs use bounded `emptyDir`
volumes. No durable application data or PVC needs backups. Globe rendering uses
the browser's GPU, so no cluster GPU is requested.

## Optional credentials

The initial deployment is keyless, with anonymous OpenSky access. Available
feeds depend on upstream availability and anonymous rate limits. Google/Cesium
photorealistic tiles, voice control, AISStream ships, FIRMS fires, and TomTom
traffic require their respective optional provider credentials.

Provider Settings is disabled in this deployment: its upstream local `.env`
writer would bypass the repository's secret-management rules. To enable a
provider, store its credentials in the `homelab-prod` 1Password vault, then add
an app-owned ExternalSecret and Deployment environment references in a PR.
Only switch `OPENSKY_AUTH_MODE` to `oauth` when its client credentials exist.
Google and Cesium tokens are intentionally sent to the browser and must be
restricted to this hostname. Consult upstream
[`.env.example`](https://github.com/bilawalsidhu/gods-eye-view/blob/759652207fd1279ece97f0f19af566feb9a82146/.env.example)
for field names. Restart the Deployment through a Git pod-template change when
environment credentials rotate; Kubernetes does not refresh process env vars.

The upstream [security model](https://github.com/bilawalsidhu/gods-eye-view/blob/759652207fd1279ece97f0f19af566feb9a82146/SECURITY.md)
requires an authentication proxy before broader exposure. Provider budget
counters in the disposable cache reset on pod replacement; use provider-side
quotas for spend controls when enabling paid services.

## Build and upgrade

Run from the repository root. The existing internal registry accepts image
pushes; publishing an image does not deploy it until the manifest PR merges.

```sh
docker build --platform linux/amd64 \
  -t registry.vanillax.me/gods-eye-view:7596522-r1 \
  my-apps/home/gods-eye-view/image
docker push registry.vanillax.me/gods-eye-view:7596522-r1
docker buildx imagetools inspect registry.vanillax.me/gods-eye-view:7596522-r1
kustomize build my-apps/home/gods-eye-view
```

For an upgrade, change the upstream commit, archive checksum and revision label
together, build with a new tag, test the container and live-data endpoints, push,
and pin the resulting tag plus registry digest in `deployment.yaml`. Never
overwrite a deployed tag. Commit and open a PR; merge is a separate operator
action. The internal registry is the image source, so rebuild/push from this
Dockerfile if its stored image is lost.

After merge, verify:

```sh
kubectl -n argocd get application my-apps-gods-eye-view
kubectl -n gods-eye-view rollout status deployment/gods-eye-view
kubectl -n gods-eye-view get pods,service,httproute,vpa
curl -fsS https://gods-eye-view.vanillax.me/healthz
```

Confirm HTTPRoute `Accepted` and `ResolvedRefs`, open the globe in a WebGL2
browser on the LAN, and choose a first-run preset. Revert the manifest PR to
remove the app through ArgoCD or revert an image change to restore that version.
