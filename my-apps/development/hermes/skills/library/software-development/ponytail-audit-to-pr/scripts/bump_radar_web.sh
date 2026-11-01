#!/usr/bin/env bash
# Wait for a radar-ng ghcr-web run, then open the talos PR that bumps the web image.
# Usage: bump-radar-web.sh <ghcr-web run id> <merge sha> <PR number> <changes-markdown-file>
set -u
R=mitchross/radar-ng; T=mitchross/talos-argocd-proxmox
RUN=$1; SHA=$2; SRCPR=$3; NOTES=$4
gh run watch "$RUN" -R $R --interval 60 --exit-status >/dev/null 2>&1 || { echo "WEB RUN FAILED"; exit 1; }
REF=""
for j in $(gh api repos/$R/actions/runs/$RUN/jobs --jq '.jobs[].id'); do
  r=$(gh api repos/$R/check-runs/$j/annotations --jq '.[]|select(.title=="published")|.message' 2>/dev/null | grep radar-ng-web | head -1)
  [ -n "$r" ] && REF=$r
done
[ -n "$REF" ] || { echo "no published annotation"; exit 1; }
NEW=${REF#*:}; NEW=${NEW%%@*}; DIG=${REF#*@}
echo "NEW=$NEW $DIG"
ACCEPT="application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.list.v2+json,application/vnd.oci.image.manifest.v1+json"
tok=$(curl -fsS "https://ghcr.io/token?scope=repository:mitchross/radar-ng-web:pull" | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
got=$(curl -fsSI -H "Authorization: Bearer $tok" -H "Accept: $ACCEPT" "https://ghcr.io/v2/mitchross/radar-ng-web/manifests/$NEW" | tr -d '\r' | awk -F': ' 'tolower($1)=="docker-content-digest"{print $2}')
[ "$got" = "$DIG" ] && echo "registry ok" || { echo "MISMATCH $got"; exit 1; }
BR=chore/radar-ng-web-$NEW; WT=/opt/data/workspace/wt-radar-ng-web-$NEW
cd /opt/data/workspace/talos-argocd-proxmox && git fetch -q origin && git worktree add -q -b "$BR" "$WT" origin/main || exit 1
cd "$WT/my-apps/personal-projects/radar-ng" || exit 1
OLD=$(grep -ohE "radar-ng-web:v[0-9.]+" deployment-web.yaml | head -1); OLD=${OLD#*:}
sed -i -E "s#radar-ng-web:v[0-9.]+@sha256:[0-9a-f]{64}#radar-ng-web:$NEW@$DIG#g" deployment-web.yaml
OUT=$(kubectl kustomize .)
echo "web refs on $NEW: $(grep -c "radar-ng-web:$NEW@" <<<"$OUT"), others: $(grep "radar-ng-web:v" <<<"$OUT" | grep -vc ":$NEW@" || true)"
cd "$WT" || exit 1
BODY=${TMPDIR:-/opt/data/cache/scratch}/talos-radar-ng-web-$NEW-body.md
{ echo "Bumps the radar-ng web image from $OLD to $NEW (radar-ng ${SHA:0:7}, mitchross/radar-ng#$SRCPR)."; echo; echo "What ships to radar.vanillax.me:"; cat "$NOTES"; echo; echo "Checks: the \`tag@digest\` comes from the ghcr-web run's \`published\` annotation and matches the registry. \`kubectl kustomize\` renders one web ref, on $NEW."; echo; echo "Rollback: revert this PR."; } > "$BODY"
git commit -q --only my-apps/personal-projects/radar-ng -m "chore(radar-ng): bump web image to $NEW" && git show --stat HEAD | tail -1
git push -q -u origin "$BR" 2>&1 | tail -1
gh pr create -R $T --base main --head "$BR" --title "chore(radar-ng): bump web image to $NEW" --body-file "$BODY"
