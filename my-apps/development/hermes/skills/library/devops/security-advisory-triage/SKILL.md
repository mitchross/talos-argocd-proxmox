---
name: security-advisory-triage
description: "Use for 'am I affected' CVE checks or vuln dep fixes."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [security, cve, advisory, dependencies, audit, homelab, gitea, renovate]
    related_skills: [homelab-ops, github, fork-hotfix-release]
---

# Security advisory triage

Two jobs: (A) answer "am I affected?" for a published vulnerability across the user's homelab, and
(B) fix vulnerable dependencies in one of the user's repos and ship a PR. Lead the answer with
**yes/no**, then the evidence; keep it short.

## When to Use

- The user shares a CVE, advisory or news post and asks "am I affected?"
- "Fix the CVE/security issues" or "update and fix" in one of the user's app repos (GitHub or Gitea).
- A repo's CI audit step (`bun audit`, `npm audit`, `pip-audit`) starts failing.

For a broken app built from a fork (upstream regression, provider change), use
`fork-hotfix-release` instead.

## A. "Am I affected?"

1. **Get the facts.** The link is often an X post: `web_extract` returns its text in the title. Then
   `web_search` for the CVE IDs + "fixed versions" and read two independent write-ups (vendor advisory,
   a security firm). Note: component affected, deployment modes at risk, fixed versions, which branches
   get no fix.
2. **Enumerate what actually runs** (read-only kubectl), containers and init containers, deduped:
   ```bash
   kubectl get pods -A -o jsonpath='{range .items[*]}{range .spec.containers[*]}{.image}{"\n"}{end}{range .spec.initContainers[*]}{.image}{"\n"}{end}{end}' \
     | sed -E 's/@sha256:.*//; s/:[^:/]+$//' | sort -u
   ```
   Grep it for the component and the well-known apps built on it, **then read the whole list**: image
   names often hide the runtime (a `linuxserver/*` or private-registry image can embed the vulnerable
   component), so an empty grep is not proof.
3. **Name what you could not see**: hosts outside the cluster (NAS apps, the Pi, desktops, routers),
   with a one-line check command per host. Internet-exposed ones first.
4. Reply: verdict · one-paragraph what the bug is with fixed versions and sources · why the user is or
   isn't affected (group what runs by runtime) · what's unchecked + the command.

## B. Fix vulnerable dependencies in a repo

1. Clone, read root and per-area `AGENTS.md` (release/tag rules matter for the deploy step). Find the
   manifests: `package.json`/lockfile, `requirements*.txt`, `go.mod`, Dockerfiles.
2. **Audit every ecosystem**, not just the one in the headline: `bun audit` (or `npm audit`) +
   `bun outdated`; `pip-audit -r requirements.txt` in a throwaway venv and the latest PyPI version of
   each pin; base-image tags in Dockerfiles.
3. **Check when CI last ran on the default branch.** If the advisories were published after the last
   green run, the image in production is vulnerable *and* the next CI run will fail its audit step;
   say both. Gitea: `GET /api/v1/repos/<o>/<r>/actions/runs?branch=main` and
   `GET /api/v1/repos/<o>/<r>/commits/main/status`.
4. **Minimal, exact bumps** on a branch: the patched version (usually the newest patch of the same
   line, which is "fully upgraded" when the user asks), matching companions (react with next), and
   same-major dev tools. Leave majors (TypeScript, `@types/node` above the runtime's Node) and say why
   in the PR. Keep the repo's pinning style (`--exact`). Remove junk files only if asked or obvious
   (empty files from stray commits).
5. **Run the repo's CI steps locally** in the order its workflow runs them (audit → typecheck → unit
   tests → build → other services' tests). Browser/E2E suites that need system libraries can be left
   to CI; list them as "not run locally".
6. **Commit and push as separate calls**, then open the PR. Body: *Why* (an advisory table:
   ID · severity · what · affected range), *Changes* (including what was deliberately not bumped),
   *Verification* (each command and result, audit before/after), *After merge* (the deploy chain).
7. Wait for PR CI, then report: PR link, CI per job, and **what must still merge before the fix is
   live**. For this user's apps, merging builds a new `vX.Y.Z` image and Renovate opens the GitOps
   bump in talos-argocd-proxmox; the vulnerable pods keep running until that PR merges. Offer to merge
   and watch for it; don't merge without being asked.

## Gitea repos (self-hosted `gitea.vanillax.me`)

See `references/gitea-api.md` for clone/push with the env token, PR creation and status polling.

## Pitfalls

- Removing a workload that is the only thing in an Argo-discovered directory (e.g. an EOL admin UI)
  trips the repo's risk gate (an Application disappearing is a BLOCK). Delete the manifests but keep
  the directory with a namespace-only kustomization, and remove the Application in a later PR after
  checking live that the namespace is preserved. Also drop the workload's VPA entry elsewhere.
- A newer Renovate digest can supersede the one a CVE note names: compare the live image digest
  against `git log -S<digest>` on the manifest to confirm it is the same or newer before re-bumping.
- Without `pods/exec`, infer a pod's runtime version from image digest and repo history rather than
  `node -v`; say it is inferred.

- Fixing the app or framework does not fix a vulnerable runtime underneath it (language runtime,
  base image): check where the bug lives before choosing what to bump.
- Never echo a token: clone with it, then `git remote set-url origin <tokenless URL>` and pipe push
  output through `sed "s/$TOKEN/***/g"`.
- Tools installed under the scratch dir get pruned after a day idle; install reusable CLIs (bun,
  pip-audit venv) under a persistent tools dir instead.
