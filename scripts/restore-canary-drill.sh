#!/usr/bin/env bash
#
# restore-canary-drill.sh — scheduled restore canary for pvc-plumber/VolSync.
#
# Continuously provable claim:
#   "A known test PVC can be deleted, recreated from Git with its
#    dataSourceRef, restored by the VolSync populator, and verified
#    byte-correctly."
#
# This tests RESTORE, not merely backup. Full docs: docs/restore-canary.md.
#
# Modes:
#   (no flag)    status   — read-only preflight gates + canary status. No writes.
#   --seed       seed     — write a fresh sentinel, force a backup (RS manual
#                           trigger bump), refresh RD latestImage. No deletes.
#   --live-run   live     — the destructive drill: seed, then delete ONLY the
#                           canary PVC, let Argo/Git recreate it with its
#                           dataSourceRef, wait for the populator restore, and
#                           verify the sentinel hash byte-for-byte.
#   --bootstrap  (live only) first-ever drill: the live PVC is allowed to be
#                           missing its dataSourceRef (day-one populator
#                           deadlock workaround); the Git render at the
#                           verified revision must contain it instead.
#   --force-unlock          clear a stale drill-in-progress marker.
#
# CONTAINMENT: every write is pinned to namespace "restore-canary", PVC
# "restore-canary-data", RS "restore-canary-data", RD
# "restore-canary-data-dst", and Argo Application "my-apps-restore-canary".
# The script refuses to run if live objects don't match those constants, and
# it hashes the full non-canary PVC inventory before/after a live run to
# prove nothing else changed. Production app PVCs, CNPG, Redis, and PostHog
# are never touched.
#
# Known hazard handled (Argo stale cache): the app is hard-refreshed and its
# reconciled revision is pinned to origin/main BEFORE any delete; recreation
# uses an explicit SHA-pinned sync operation; live objects are verified, not
# Argo app status. See docs/restore-canary.md.
#
# Exit codes: 0 = all gates/drill passed; 1 = a gate or the drill failed.

set -euo pipefail

# --- Canary constants (the identity the script refuses to deviate from) ----
readonly NS="restore-canary"
readonly PVC_NAME="restore-canary-data"
readonly RS_NAME="restore-canary-data"
readonly RD_NAME="restore-canary-data-dst"
readonly APP="my-apps-restore-canary"
readonly ARGO_NS="argocd"
readonly WORKLOAD_SELECTOR="app.kubernetes.io/name=restore-canary"
readonly SENTINEL_PATH="/data/SENTINEL"
readonly AUDIT_RAW="/api/v1/namespaces/pvc-plumber/services/pvc-plumber-metrics:audit-http/proxy/audit"
readonly ANNO_PREFIX="restore-canary.vanillax.dev"
readonly KOPIA_SECRET="volsync-kopia-repository"
# Canonical trigger seeds rendered by pvc-plumber v4.0.2 for tier=manual.
readonly RS_TRIGGER_SEED="backup-on-demand"
readonly RD_TRIGGER_SEED="restore-once"

MODE="status"
BOOTSTRAP=0
FORCE_UNLOCK=0
for arg in "$@"; do
  case "$arg" in
    --seed) MODE="seed" ;;
    --live-run) MODE="live" ;;
    --bootstrap) BOOTSTRAP=1 ;;
    --force-unlock) FORCE_UNLOCK=1 ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown argument: $arg (see --help)" >&2; exit 1 ;;
  esac
done
if [[ "$BOOTSTRAP" -eq 1 && "$MODE" != "live" ]]; then
  echo "--bootstrap only makes sense with --live-run" >&2; exit 1
fi

DESTRUCTIVE_STARTED=0
DRILL_PASSED=0
MARKER_SET=0
UID_BEFORE=""
UID_AFTER=""
TARGET_SHA=""

log()  { printf '[%s] %s\n' "$(date -u +%H:%M:%S)" "$*"; }
fail_dump() {
  log "---- diagnostic dump (namespace ${NS}) ----"
  kubectl get pvc,replicationsource,replicationdestination,pods -n "$NS" -o wide 2>&1 || true
  kubectl get application "$APP" -n "$ARGO_NS" \
    -o jsonpath='{.status.sync.status} {.status.sync.revision} {.status.health.status} {.status.operationState.phase}{"\n"}' 2>&1 || true
  audit_entry_json 2>&1 || true
  log "---- end dump ----"
}
die() { log "FAIL: $*"; fail_dump; exit 1; }

on_exit() {
  local rc=$?
  if [[ "$MODE" == "live" && "$MARKER_SET" -eq 1 ]]; then
    kubectl annotate ns "$NS" "${ANNO_PREFIX}/drill-in-progress-" --overwrite >/dev/null 2>&1 || true
  fi
  if [[ "$MODE" == "live" && "$DESTRUCTIVE_STARTED" -eq 1 ]]; then
    local result="fail"
    [[ "$DRILL_PASSED" -eq 1 ]] && result="pass"
    kubectl annotate ns "$NS" --overwrite \
      "${ANNO_PREFIX}/last-drill-time=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
      "${ANNO_PREFIX}/last-drill-result=${result}" \
      "${ANNO_PREFIX}/last-drill-commit=${TARGET_SHA:-unknown}" \
      "${ANNO_PREFIX}/last-drill-uid-before=${UID_BEFORE:-unknown}" \
      "${ANNO_PREFIX}/last-drill-uid-after=${UID_AFTER:-unknown}" \
      >/dev/null 2>&1 || true
  fi
  exit "$rc"
}
trap on_exit EXIT

# wait_until <timeout_seconds> <description> <predicate-function> [args...]
wait_until() {
  local timeout="$1" desc="$2"; shift 2
  local start="$SECONDS"
  while true; do
    if "$@"; then return 0; fi
    if (( SECONDS - start > timeout )); then
      die "timeout (${timeout}s) waiting for: ${desc}"
    fi
    sleep 5
  done
}

jp() { # jp <kind/name|kind name...> <jsonpath> — namespaced get, empty on miss
  local path="$1"; shift
  kubectl get "$@" -n "$NS" -o jsonpath="$path" 2>/dev/null || true
}

audit_entry_json() {
  kubectl get --raw "$AUDIT_RAW" 2>/dev/null | python3 -c '
import json, sys
ns, pvc = sys.argv[1], sys.argv[2]
d = json.load(sys.stdin)
for e in d.get("entries", []):
    if e.get("namespace") == ns and e.get("pvc") == pvc:
        print(json.dumps(e)); break
' "$NS" "$PVC_NAME"
}

audit_field() { # audit_field <key>  (top-level entry key)
  audit_entry_json | python3 -c '
import json, sys
line = sys.stdin.read().strip()
if line:
    print(json.loads(line).get(sys.argv[1], ""))
' "$1"
}

non_canary_pvc_fingerprint() {
  # Excludes the canary namespace and VolSync's ephemeral mover PVCs
  # (volsync-*-src clones / -dst-dest caches) — unrelated fleet backups
  # legitimately create and delete those mid-drill.
  kubectl get pvc -A \
    -o jsonpath='{range .items[*]}{.metadata.namespace}/{.metadata.name}:{.metadata.uid}{"\n"}{end}' \
    | grep -v "^${NS}/" | grep -v '/volsync-' | sort | sha256sum | awk '{print $1}'
}

running_pod() {
  kubectl get pod -n "$NS" -l "$WORKLOAD_SELECTOR" \
    --field-selector=status.phase=Running -o name 2>/dev/null | head -n1
}

# --- predicates for wait_until ---------------------------------------------
pvc_absent() {
  [[ -z "$(kubectl get pvc "$PVC_NAME" -n "$NS" --ignore-not-found -o name)" ]]
}
pvc_present() {
  [[ -n "$(kubectl get pvc "$PVC_NAME" -n "$NS" --ignore-not-found -o name)" ]]
}
pvc_bound() { [[ "$(jp '{.status.phase}' pvc "$PVC_NAME")" == "Bound" ]]; }
pod_ready() {
  local p; p="$(running_pod)"
  [[ -n "$p" ]] || return 1
  [[ "$(kubectl get "$p" -n "$NS" -o jsonpath='{.status.containerStatuses[0].ready}' 2>/dev/null)" == "true" ]]
}
rs_synced_to() { # rs_synced_to <manual-value>
  [[ "$(jp '{.status.lastManualSync}' replicationsource "$RS_NAME")" == "$1" ]] \
    && [[ "$(jp '{.status.latestMoverStatus.result}' replicationsource "$RS_NAME")" == "Successful" ]]
}
rd_synced_to() { # rd_synced_to <manual-value>
  [[ "$(jp '{.status.lastManualSync}' replicationdestination "$RD_NAME")" == "$1" ]] \
    && [[ -n "$(jp '{.status.latestImage.name}' replicationdestination "$RD_NAME")" ]]
}
refresh_consumed() {
  [[ -z "$(kubectl get application "$APP" -n "$ARGO_NS" \
    -o jsonpath='{.metadata.annotations.argocd\.argoproj\.io/refresh}' 2>/dev/null)" ]]
}
app_at_target_sha() {
  [[ "$(kubectl get application "$APP" -n "$ARGO_NS" -o jsonpath='{.status.sync.revision}' 2>/dev/null)" == "$TARGET_SHA" ]]
}
app_op_done() {
  local phase
  phase="$(kubectl get application "$APP" -n "$ARGO_NS" -o jsonpath='{.status.operationState.phase}' 2>/dev/null)"
  [[ "$phase" != "Running" ]]
}
audit_action_matches() { [[ "$(audit_field action)" == "already-matches" ]]; }
audit_already_matches_fresh() {
  [[ "$(audit_field action)" == "already-matches" ]] && [[ "$(audit_field stale)" == "False" || "$(audit_field stale)" == "false" ]]
}

# --- shared actions ----------------------------------------------------------
bump_rs() { # bump_rs <value>
  kubectl patch replicationsource "$RS_NAME" -n "$NS" --type merge \
    -p "{\"spec\":{\"trigger\":{\"manual\":\"$1\"}}}" >/dev/null
}
bump_rd() { # bump_rd <value>
  kubectl patch replicationdestination "$RD_NAME" -n "$NS" --type merge \
    -p "{\"spec\":{\"trigger\":{\"manual\":\"$1\"}}}" >/dev/null
}

write_sentinel() { # writes fresh sentinel; sets SENTINEL_CONTENT + EXPECTED_SHA
  local pod uid ts nonce
  pod="$(running_pod)"
  [[ -n "$pod" ]] || die "no Running canary pod to write sentinel into"
  uid="$(jp '{.metadata.uid}' pvc "$PVC_NAME")"
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  nonce="$(od -An -N8 -tx1 /dev/urandom | tr -d ' \n')"
  SENTINEL_CONTENT="restore-canary uid=${uid} time=${ts} nonce=${nonce}"
  printf '%s\n' "$SENTINEL_CONTENT" | kubectl exec -i -n "$NS" "$pod" -- \
    sh -c "cat > ${SENTINEL_PATH} && cd /data && sha256sum SENTINEL > SENTINEL.sha256 && sync"
  EXPECTED_SHA="$(printf '%s\n' "$SENTINEL_CONTENT" | sha256sum | awk '{print $1}')"
  local live
  live="$(kubectl exec -n "$NS" "$pod" -- sha256sum "$SENTINEL_PATH" | awk '{print $1}')"
  [[ "$live" == "$EXPECTED_SHA" ]] || die "sentinel write verification mismatch (wrote ${EXPECTED_SHA}, read ${live})"
  log "sentinel written: ${SENTINEL_CONTENT}"
  log "sentinel sha256:  ${EXPECTED_SHA}"
}

verify_sentinel() { # verify against EXPECTED_SHA + embedded UID_BEFORE
  local pod live content
  pod="$(running_pod)"
  [[ -n "$pod" ]] || die "no Running canary pod to verify sentinel in"
  live="$(kubectl exec -n "$NS" "$pod" -- sha256sum "$SENTINEL_PATH" | awk '{print $1}')"
  [[ "$live" == "$EXPECTED_SHA" ]] || die "RESTORED SENTINEL HASH MISMATCH: expected ${EXPECTED_SHA}, got ${live} — restore is NOT byte-correct"
  kubectl exec -n "$NS" "$pod" -- sh -c 'cd /data && sha256sum -c SENTINEL.sha256' >/dev/null \
    || die "restored SENTINEL.sha256 self-check failed"
  content="$(kubectl exec -n "$NS" "$pod" -- cat "$SENTINEL_PATH")"
  [[ "$content" == *"uid=${UID_BEFORE}"* ]] \
    || die "restored sentinel does not embed pre-delete PVC uid ${UID_BEFORE} (got: ${content}) — data did not come from the drill backup"
  log "restored sentinel verified byte-correct: ${content}"
}

# --- preflight gates ---------------------------------------------------------
preflight() {
  log "preflight: verifying canary identity and contract (namespace=${NS}, pvc=${PVC_NAME})"
  command -v kubectl >/dev/null || die "kubectl not found"
  command -v python3 >/dev/null || die "python3 not found"
  kubectl get ns "$NS" >/dev/null 2>&1 || die "namespace ${NS} not found"

  [[ "$(jp '{.metadata.labels.pvc-plumber\.io/managed-namespace}' ns "$NS")" == "true" ]] \
    || die "namespace ${NS} missing pvc-plumber.io/managed-namespace=true"
  [[ "$(jp '{.metadata.labels.volsync\.backube/privileged-movers}' ns "$NS")" == "true" ]] \
    || die "namespace ${NS} missing volsync.backube/privileged-movers=true"

  pvc_present || die "PVC ${NS}/${PVC_NAME} not found"
  [[ "$(jp "{.metadata.labels.pvc-plumber\\.io/enabled}" pvc "$PVC_NAME")" == "true" ]] \
    || die "PVC missing pvc-plumber.io/enabled=true"
  [[ "$(jp "{.metadata.labels.pvc-plumber\\.io/manage-volsync}" pvc "$PVC_NAME")" == "true" ]] \
    || die "PVC missing pvc-plumber.io/manage-volsync=true"
  [[ "$(jp "{.metadata.labels.pvc-plumber\\.io/tier}" pvc "$PVC_NAME")" == "manual" ]] \
    || die "PVC tier is not 'manual' — refusing to drill an unexpected canary shape"

  kubectl get secret "$KOPIA_SECRET" -n "$NS" >/dev/null 2>&1 \
    || die "shared Kopia secret ${KOPIA_SECRET} not fanned out into ${NS}"

  [[ "$(jp '{.metadata.labels.app\.kubernetes\.io/managed-by}' replicationsource "$RS_NAME")" == "pvc-plumber" ]] \
    || die "ReplicationSource ${RS_NAME} missing or not managed-by=pvc-plumber"
  [[ "$(jp '{.metadata.labels.app\.kubernetes\.io/managed-by}' replicationdestination "$RD_NAME")" == "pvc-plumber" ]] \
    || die "ReplicationDestination ${RD_NAME} missing or not managed-by=pvc-plumber"

  local dsr
  dsr="$(jp '{.spec.dataSourceRef.name}' pvc "$PVC_NAME")"
  if [[ "$dsr" != "$RD_NAME" ]]; then
    if [[ "$BOOTSTRAP" -eq 1 ]]; then
      log "bootstrap mode: live PVC has no dataSourceRef yet (dsr='${dsr}'); Git render will install it on recreate"
      local repo_root
      repo_root="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
      grep -q "name: ${RD_NAME}" "${repo_root}/my-apps/system/restore-canary/pvc.yaml" \
        || die "bootstrap: Git pvc.yaml does not declare dataSourceRef ${RD_NAME}"
    else
      die "live PVC dataSourceRef is '${dsr}', expected '${RD_NAME}' (re-run with --bootstrap only for the first drill)"
    fi
  fi

  # Tolerate short operator reconcile lag (e.g. right after first deploy)
  # before requiring the contract verdict.
  wait_until 180 "/audit already-matches for ${NS}/${PVC_NAME}" audit_action_matches

  log "preflight: all contract gates passed"
}

print_status() {
  log "canary status:"
  log "  PVC uid:        $(jp '{.metadata.uid}' pvc "$PVC_NAME")  phase: $(jp '{.status.phase}' pvc "$PVC_NAME")"
  log "  dataSourceRef:  $(jp '{.spec.dataSourceRef.name}' pvc "$PVC_NAME")"
  log "  RS lastSync:    $(jp '{.status.lastSyncTime}' replicationsource "$RS_NAME")  result: $(jp '{.status.latestMoverStatus.result}' replicationsource "$RS_NAME")  manual: $(jp '{.spec.trigger.manual}' replicationsource "$RS_NAME")"
  log "  RD latestImage: $(jp '{.status.latestImage.name}' replicationdestination "$RD_NAME")"
  log "  /audit action:  $(audit_field action)  stale: $(audit_field stale)"
  log "  last drill:     $(jp "{.metadata.annotations.${ANNO_PREFIX//./\\.}/last-drill-time}" ns "$NS") result=$(jp "{.metadata.annotations.${ANNO_PREFIX//./\\.}/last-drill-result}" ns "$NS")"
  local pod
  pod="$(running_pod)"
  if [[ -n "$pod" ]]; then
    if kubectl exec -n "$NS" "$pod" -- test -f "$SENTINEL_PATH" 2>/dev/null; then
      log "  sentinel:       present ($(kubectl exec -n "$NS" "$pod" -- sha256sum "$SENTINEL_PATH" | awk '{print $1}'))"
    else
      log "  sentinel:       MISSING — run --seed"
    fi
  else
    log "  workload:       no Running pod"
  fi
}

seed() {
  wait_until 600 "canary pod Running" pod_ready
  write_sentinel
  local val
  val="seed-$(date -u +%Y%m%d-%H%M%S)"
  log "forcing backup: RS trigger.manual=${val}"
  bump_rs "$val"
  wait_until 900 "RS backup ${val} Successful" rs_synced_to "$val"
  log "backup Successful (lastSyncTime $(jp '{.status.lastSyncTime}' replicationsource "$RS_NAME"))"
  log "refreshing RD latestImage: RD trigger.manual=${val}"
  bump_rd "$val"
  wait_until 900 "RD sync ${val} complete with latestImage" rd_synced_to "$val"
  log "RD latestImage: $(jp '{.status.latestImage.name}' replicationdestination "$RD_NAME")"
  log "seed complete — sentinel is in the Kopia repo and the RD is restore-ready"
}

live_drill() {
  # -- lock --
  local marker
  marker="$(jp "{.metadata.annotations.${ANNO_PREFIX//./\\.}/drill-in-progress}" ns "$NS")"
  if [[ -n "$marker" ]]; then
    if [[ "$FORCE_UNLOCK" -eq 1 ]]; then
      log "clearing stale drill-in-progress marker (${marker})"
    else
      die "another drill appears in progress (marker ${marker}); use --force-unlock if stale"
    fi
  fi
  kubectl annotate ns "$NS" --overwrite \
    "${ANNO_PREFIX}/drill-in-progress=$(date -u +%Y-%m-%dT%H:%M:%SZ)" >/dev/null
  MARKER_SET=1

  # -- pin Git/Argo currency BEFORE anything destructive --
  local repo_root
  repo_root="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
  TARGET_SHA="$(git -C "$repo_root" ls-remote origin refs/heads/main | awk '{print $1}')"
  [[ -n "$TARGET_SHA" ]] || die "could not resolve origin/main SHA"
  log "target revision (origin/main): ${TARGET_SHA}"

  local fingerprint_before
  fingerprint_before="$(non_canary_pvc_fingerprint)"

  wait_until 600 "canary pod Running" pod_ready
  UID_BEFORE="$(jp '{.metadata.uid}' pvc "$PVC_NAME")"
  log "canary PVC uid before drill: ${UID_BEFORE}"

  # -- sentinel + backup + RD refresh --
  write_sentinel
  local ts val
  ts="$(date -u +%Y%m%d-%H%M%S)"
  val="drill-${ts}"
  log "forcing backup of sentinel: RS trigger.manual=${val}"
  bump_rs "$val"
  wait_until 900 "RS backup ${val} Successful" rs_synced_to "$val"
  log "backup Successful (lastSyncTime $(jp '{.status.lastSyncTime}' replicationsource "$RS_NAME"))"

  local latest_before
  latest_before="$(jp '{.status.latestImage.name}' replicationdestination "$RD_NAME")"
  log "refreshing RD latestImage (was: ${latest_before:-<none>}): RD trigger.manual=${val}"
  bump_rd "$val"
  wait_until 900 "RD sync ${val} complete with latestImage" rd_synced_to "$val"
  local latest_after
  latest_after="$(jp '{.status.latestImage.name}' replicationdestination "$RD_NAME")"
  [[ -n "$latest_after" && "$latest_after" != "$latest_before" ]] \
    || die "RD latestImage did not advance (${latest_before} -> ${latest_after}); restore would be stale"
  log "RD latestImage refreshed: ${latest_after}"

  # -- Argo stale-cache discipline: hard refresh, wait consumed, pin SHA --
  log "hard-refreshing Argo app ${APP} and pinning revision"
  kubectl annotate application "$APP" -n "$ARGO_NS" argocd.argoproj.io/refresh=hard --overwrite >/dev/null
  wait_until 300 "hard refresh consumed" refresh_consumed
  wait_until 300 "app reconciled at ${TARGET_SHA}" app_at_target_sha
  wait_until 300 "no Argo operation in progress" app_op_done

  # re-verify the live PVC contract immediately before deletion
  preflight

  # -- destructive phase (canary PVC ONLY) --
  [[ "$NS" == "restore-canary" && "$PVC_NAME" == "restore-canary-data" ]] \
    || die "identity constants corrupted — refusing destructive phase"
  DESTRUCTIVE_STARTED=1
  log "DELETING canary PVC ${NS}/${PVC_NAME} (uid ${UID_BEFORE})"
  kubectl delete pvc "$PVC_NAME" -n "$NS" --wait=false
  log "deleting canary pod so pvc-protection releases (replacement parks Pending)"
  kubectl delete pod -n "$NS" -l "$WORKLOAD_SELECTOR" --wait=false
  wait_until 600 "PVC fully deleted" pvc_absent
  log "PVC deleted; recreating from Git at ${TARGET_SHA}"

  # selfHeal may already be syncing the drift (PVC missing) — let any
  # in-flight operation finish, then issue the explicit SHA-pinned sync if
  # the PVC has not reappeared. The authoritative condition is the live
  # object (PVC present with correct dataSourceRef), never Argo op status.
  wait_until 300 "no Argo operation in progress" app_op_done
  if pvc_present; then
    log "selfHeal already recreated the PVC; skipping explicit sync"
  else
    kubectl patch application "$APP" -n "$ARGO_NS" --type merge -p \
      "{\"operation\":{\"initiatedBy\":{\"username\":\"restore-canary-drill\"},\"sync\":{\"revision\":\"${TARGET_SHA}\",\"prune\":false,\"syncStrategy\":{\"apply\":{\"force\":false}}}}}" >/dev/null
  fi
  wait_until 300 "PVC recreated from Git" pvc_present
  UID_AFTER="$(jp '{.metadata.uid}' pvc "$PVC_NAME")"
  [[ -n "$UID_AFTER" && "$UID_AFTER" != "$UID_BEFORE" ]] \
    || die "recreated PVC uid did not change (${UID_BEFORE} -> ${UID_AFTER})"
  log "PVC recreated, new uid: ${UID_AFTER}"
  local dsr
  dsr="$(jp '{.spec.dataSourceRef.name}' pvc "$PVC_NAME")"
  [[ "$dsr" == "$RD_NAME" ]] \
    || die "recreated PVC dataSourceRef is '${dsr}', expected '${RD_NAME}' — Git render did not include the restore reference"

  log "waiting for VolSync populator restore (PVC Bound)"
  wait_until 1200 "PVC Bound via populator restore" pvc_bound
  log "waiting for canary pod to mount restored volume"
  wait_until 600 "canary pod Running on restored PVC" pod_ready

  # -- verification --
  verify_sentinel
  log "waiting for fresh /audit already-matches"
  wait_until 600 "/audit already-matches (fresh)" audit_already_matches_fresh

  # -- restore canonical triggers; the change itself proves backup resumes --
  log "resetting RS trigger to canonical '${RS_TRIGGER_SEED}' (fires the post-restore backup)"
  bump_rs "$RS_TRIGGER_SEED"
  wait_until 900 "post-restore backup Successful" rs_synced_to "$RS_TRIGGER_SEED"
  log "post-restore backup Successful"
  log "resetting RD trigger to canonical '${RD_TRIGGER_SEED}' (refreshes latestImage post-drill)"
  bump_rd "$RD_TRIGGER_SEED"
  wait_until 900 "RD canonical sync complete" rd_synced_to "$RD_TRIGGER_SEED"

  # -- containment proof --
  local fingerprint_after
  fingerprint_after="$(non_canary_pvc_fingerprint)"
  [[ "$fingerprint_before" == "$fingerprint_after" ]] \
    || die "non-canary PVC inventory changed during the drill — investigate immediately"
  log "containment verified: non-canary PVC inventory unchanged"

  DRILL_PASSED=1
  log "==== RESTORE CANARY DRILL PASSED ===="
  log "  pvc uid:    ${UID_BEFORE} -> ${UID_AFTER}"
  log "  sentinel:   ${EXPECTED_SHA} (byte-correct after restore)"
  log "  revision:   ${TARGET_SHA}"
  log "  rd image:   $(jp '{.status.latestImage.name}' replicationdestination "$RD_NAME")"
}

case "$MODE" in
  status)
    preflight
    print_status
    ;;
  seed)
    preflight
    seed
    ;;
  live)
    preflight
    live_drill
    ;;
esac
