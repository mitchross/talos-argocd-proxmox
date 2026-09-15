#!/usr/bin/env bash
# Validate rendered Collector configs with their deployment images.
# Requires: kustomize, python3 + pyyaml, docker, openssl.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OTEL_DIR="${REPO_ROOT}/infrastructure/controllers/opentelemetry-operator"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

echo "[otel-validate] rendering $OTEL_DIR"
kustomize build --enable-helm "$OTEL_DIR" > "$WORK/rendered.yaml"

# Extract each OpenTelemetryCollector CR's .spec.config into its own file.
python3 - "$WORK" <<'PYEOF'
import sys, yaml
work = sys.argv[1]
count = 0
with open(f"{work}/rendered.yaml") as f:
    docs = [doc for doc in yaml.safe_load_all(f) if doc]
default_images = {
    arg.split("=", 1)[1]
    for doc in docs if doc.get("kind") == "Deployment"
    for container in doc["spec"]["template"]["spec"]["containers"]
    for arg in container.get("args", [])
    if arg.startswith("--collector-image=")
}
for doc in docs:
    if doc.get("kind") != "OpenTelemetryCollector":
        continue
    name = doc["metadata"]["name"]
    spec = doc["spec"]
    image = spec.get("image")
    if not image:
        if len(default_images) != 1:
            raise SystemExit(f"[otel-validate] FAIL: cannot resolve image for {name}")
        image = next(iter(default_images))
    out = f"{work}/{name}.yaml"
    with open(out, "w") as o:
        yaml.safe_dump(spec["config"], o, default_flow_style=False)
    with open(f"{work}/{name}.image", "w") as o:
        o.write(image)
    print(f"[otel-validate] extracted {name} → {out}")
    count += 1
if count == 0:
    raise SystemExit("[otel-validate] FAIL: no OpenTelemetryCollector CRs found in render")
PYEOF

# Container runs as non-root — $(mktemp -d) defaults to 0700 which blocks
# traversal from inside. Loosen dir + files, and run as current uid.
chmod 755 "$WORK"
chmod 644 "$WORK"/*.yaml

# `otelcol validate` partially initializes receivers/extensions during
# validation. Some receivers (`kubeletstats`, `k8s_cluster`) try to read
# the serviceaccount CA cert at `/var/run/secrets/kubernetes.io/
# serviceaccount/ca.crt`, which doesn't exist outside a pod. Provide a
# dummy cert so the Start() path succeeds — we don't care about the cert
# content, only that the config references are valid.
mkdir -p "$WORK/sa"
# Real self-signed cert so `AppendCertsFromPEM` accepts it. Content is
# meaningless to the validator — we only care that parsing succeeds.
openssl req -x509 -newkey rsa:2048 -days 365 -nodes \
  -keyout "$WORK/sa/tls.key" -out "$WORK/sa/ca.crt" \
  -subj "/CN=otel-validate-dummy" >/dev/null 2>&1
echo "dummy" > "$WORK/sa/token"
chmod -R 755 "$WORK/sa"

fail=0
for cfg in "$WORK"/*.yaml; do
  case "$(basename "$cfg")" in rendered.yaml) continue;; esac
  name="$(basename "$cfg" .yaml)"
  image="${OTEL_IMAGE:-$(cat "$WORK/$name.image")}"
  echo ""
  echo "[otel-validate] validating $name with $image"
  # Mount the dummy SA dir over the in-container path receivers look for.
  if ! docker run --rm --user "$(id -u):$(id -g)" \
       -v "$WORK:/cfg:ro" \
       -v "$WORK/sa:/var/run/secrets/kubernetes.io/serviceaccount:ro" \
       -e KUBERNETES_SERVICE_HOST=127.0.0.1 \
       -e KUBERNETES_SERVICE_PORT=443 \
       -e K8S_NODE_NAME=validation-node \
       "$image" \
       validate --config="/cfg/$(basename "$cfg")"; then
    echo "[otel-validate] ❌ FAIL: $name"
    fail=1
  else
    echo "[otel-validate] ✅ OK: $name"
  fi
done

if [ "$fail" -ne 0 ]; then
  echo ""
  echo "[otel-validate] One or more collector configs are invalid."
  exit 1
fi
echo ""
echo "[otel-validate] all collector configs valid"
