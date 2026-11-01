# Retire one component's docs and replace them with its successor's

For "replace my X docs with Y setup" in a GitOps/homelab repo (e.g. a turned-off agent workspace
replaced by a new agent). One PR, docs only unless the user opts into config cleanup.

## Ask first (one clarify call, three independent questions)

1. Old pages: delete (history keeps them) / move to archive / shrink to a "retired, how to turn back on" stub.
2. Also write "Run Y on another cluster" in the same shape as X's guide?
3. Remove leftover config wiring that still points at X (fallbacks, secrets) in the same PR?

## Procedure

1. Inventory every mention: `grep -ril <x> --exclude-dir=.git .` — docs, `mkdocs.yml` nav, `llms.txt`,
   index pages, sibling guides, the X app's own README/CLAUDE.md, tests and CI that read X's files.
2. Read the successor's real manifests, config and seed scripts, and check live state read-only
   (Argo app health, PVC size, snapshots, an unauthenticated status endpoint). Existing successor docs
   drift fast (sizes, backup cadence, removed fallbacks); rewrite from the manifests, not the old page.
3. Rewrite Y's page in the old page's section shape: purpose/status header, what it is + mermaid,
   "how it is built" table (piece · where · notes), numbered steps each ending "It worked when…",
   Verify (commands + expected output), Change table, Troubleshooting table, Backups and rollback,
   Known limits.
4. Other-cluster guide (same shape as X's): coding-agent prompt, what you need, Compose, plain
   Kubernetes files, deploy, check table, connect/log in, security, update/back up/roll back. Fact-check:
   - image is public: `T=$(curl -s "https://ghcr.io/token?scope=repository:<owner>/<img>:pull" | jq -r .token)`
     then GET `/v2/<owner>/<img>/manifests/main` with that bearer → 200;
   - architectures from the build workflow's `platforms:`;
   - root vs non-root start (a root-starting s6 image needs Pod Security `baseline`, not `restricted`);
   - config syntax from a form the repo actually ran (`git log` / `git show <first-commit>:<config>`),
     not guessed from docs.
5. Delete the old pages with `git rm`. In X's leftover app dir, link the old guide by permalink
   (`blob/<base-sha>/docs/...`) so the dir stays understandable.
6. Update nav, index, `llms.txt`, sibling guides. Leave tests that read X's still-present config files alone;
   list deleting X's app dir (and those tests) as a follow-up. If the user keeps X's dir but drops the
   coupling: delete only the tests that compare X's copies (grep the test tree for X's config paths),
   run the edited test module (all remaining tests must pass), and mark X's copies "not CI-checked —
   compare before turning X back on" in the sibling guide, also removing any "CI-checked copy" wording.
7. Run the link checker on base and branch; the broken count must not rise. `kubectl kustomize` the
   successor's dir if any manifest changed. CI's `mkdocs build --strict` covers nav/anchors.
8. Before committing, re-fetch main and check open PRs for overlap (see SKILL.md, Finishing).

## Document the successor's image build (when asked for "the actual image build stuff")

Add a "The image" section to Y's page, sourced from files, not memory:

| Fact | Source |
|---|---|
| Layers and how each is pinned (base tag+digest, `ARG *_VERSION` + `*_SHA256`, npm versions) | image repo `Dockerfile` |
| Triggers, platforms, scheduled no-cache rebuild, tags pushed, where the digest is printed | build workflow; read its job `if:` (a `head.repo != repository` guard means only fork PRs build on `pull_request`) |
| What the test proves | the test/smoke script the workflow calls |
| Which updates Renovate opens and how they group | image repo `renovate.json` (`customManagers` regex on `# renovate:` comments, `packageRules` groups) |
| How the new digest reaches the cluster | GitOps repo Renovate: manager `managerFilePatterns` covering the app dir + the digest group rule |

Include: mermaid of Dockerfile → CI → test → registry → digest PR → Argo; a local build+test recipe
(flag it untested if no Docker); "check what the pod runs" (`.status.containerStatuses[0].imageID`
vs the manifest digest, tool `--version`s). Say the digest goes in **every** `image:` line (init
containers too). Link the Dockerfile for versions instead of copying numbers that go stale.

## Leave out

Steps you could not verify (e.g. a desktop-app login against a non-default auth provider). List them
as follow-ups and ask the user how they do it today, instead of documenting a guess.
