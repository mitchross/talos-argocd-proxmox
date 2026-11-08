# CI build speed for compiled-language phases (Rust)

Use this when CI gets slow after a port, or the user asks about self-hosted runners.

## Decide
1. **Measure first:** `gh run view <id> --json jobs -q '.jobs[]|.name+" "+.startedAt+" "+.completedAt'`. Compare the compiled job with the rest.
2. **Recommend caching before self-hosted runners.** Caching is one PR and runs nothing in the cluster. Self-hosted runners (actions-runner-controller, a GitHub App key in 1Password, buildkit in the pod) compete with the apps for CPU and RAM, and they stop working while the cluster is down for a rebuild. Propose runners only if the cached release builds are still over about 5 minutes.

## Add the cache
- Pin actions by SHA. Look the SHA up, never guess it:
  `t=$(gh release view -R Swatinem/rust-cache --json tagName -q .tagName); gh api repos/Swatinem/rust-cache/commits/$t -q .sha`
  Do the same for `docker/setup-buildx-action` and `docker/build-push-action`. Children often skip the cache because they can't look up a SHA, so put the SHAs in the prompt.
- Cargo job: `Swatinem/rust-cache` after the toolchain step.
- Images: multi-stage Dockerfiles with cargo-chef (the dependency layer caches apart from the source), plus `cache-from/cache-to: type=gha,scope=<image>`, one scope per image. Build the images on PRs without pushing, and add a smoke run (`--version`, a dry run).
- **Free runner disk first on large Rust workspaces.** A debug build with every test binary can reach ~14 GB and fill the hosted runner. The job then fails with "No space left on device", often while rust-cache is saving, after every cargo step has passed. Make the first step delete the preinstalled toolchains you don't use (Android, .NET, GHC, CodeQL). That step changes no cargo env, so the cache key stays the same. When the default-branch CI fails, the release-on-merge tag never happens, so fix this before the cutover merges.
- **Put CI-file edits in one PR at a time.** Parallel phases that both edit `ci.yml` conflict when one merges first.

## Verify it works
- The first run on the default branch is cold and fills the cache. It can be slower than before.
- A PR that changes `Cargo.lock`, the toolchain or the workspace layout gets a new cache key, so it builds mostly cold even with a warm default-branch cache. Judge the cache on a PR that only changes source, and tell the user why a dependency-heavy PR was slow.
- A PR only restores the cache if its branch already contains the cache step. Branches cut before the cache PR merged still build cold, so judge by the next new PR.
- Check the stored caches: `gh cache list -R <repo> --limit 100 --json key,sizeInBytes,ref`. You want a `v0-rust-…` key on `refs/heads/<default>` (hundreds of MB) and buildkit blobs per image scope.
- Report the cold and warm times side by side in the PR.
