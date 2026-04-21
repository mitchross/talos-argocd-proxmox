#!/usr/bin/env bash
# Validate OpenTelemetry Collector configs in the repo.
#
# Today's root-sync-jam (2026-04-20) was caused by an orphaned
# `k8sobjects` reference in the logs pipeline's receivers list after the
# receiver itself was deleted (VPA ripout collateral damage). The
# collector refused to boot with "invalid configuration: references
# receiver k8sobjects which is not configured" — 9 hours of
# CrashLoopBackOff before anyone noticed.
#
# This script renders each OpenTelemetryCollector CR in the repo,
# extracts the `.spec.config` (which IS a raw otelcol config YAML),
# and runs `otelcol validate` on it. Any pipeline/receiver/exporter
# mismatch is caught at CI time instead of mid-sync.
#
# Requires: kustomize, python3 + pyyaml, docker (for the otelcol-contrib
# image which carries all the receivers/processors we use).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OTEL_DIR="${REPO_ROOT}/infrastructure/controllers/opentelemetry-operator"
OTEL_IMAGE="${OTEL_IMAGE:-otel/opentelemetry-collector-contrib:0.148.0}"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

echo "[otel-validate] rendering $OTEL_DIR"
kustomize build --enable-helm "$OTEL_DIR" > "$WORK/rendered.yaml"

# Extract each OpenTelemetryCollector CR's .spec.config into its own file.
python3 <<PYEOF
import yaml, os
work = "$WORK"
count = 0
with open(f"{work}/rendered.yaml") as f:
    for doc in yaml.safe_load_all(f):
        if not doc:
            continue
        if doc.get("kind") != "OpenTelemetryCollector":
            continue
        name = doc["metadata"]["name"]
        cfg = doc.get("spec", {}).get("config")
        if cfg is None:
            continue
        out = f"{work}/{name}.yaml"
        with open(out, "w") as o:
            yaml.safe_dump(cfg, o, default_flow_style=False)
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
  echo ""
  echo "[otel-validate] validating $name"
  # Mount the dummy SA dir over the in-container path receivers look for.
  if ! docker run --rm --user "$(id -u):$(id -g)" \
       -v "$WORK:/cfg:ro" \
       -v "$WORK/sa:/var/run/secrets/kubernetes.io/serviceaccount:ro" \
       -e KUBERNETES_SERVICE_HOST=127.0.0.1 \
       -e KUBERNETES_SERVICE_PORT=443 \
       "$OTEL_IMAGE" \
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
