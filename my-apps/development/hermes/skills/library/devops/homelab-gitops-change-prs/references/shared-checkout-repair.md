# Repairing a shared checkout with empty or corrupt objects

Symptom: `git fetch` fails with `object file .git/objects/xx/... is empty` or `fatal: cannot read existing object info`, and `git fsck` shows `invalid sha1 pointer` on `refs/remotes/...`. A killed fetch or pod restart is the likely cause, but treat that as a hypothesis. Many worktrees share this `.git`, so check what's at stake before changing anything.

## 1. Inventory, read-only
- For every worktree in `git worktree list --porcelain`, check: is it dirty (`git -C <wt> status --porcelain`), how many commits are unpushed (`git -C <wt> rev-list --count @{u}..HEAD`), and whether it's on a detached HEAD.
- List the empty objects (`find .git/objects -type f -empty`), and for each one the refs pointing at it (`git for-each-ref --points-at <sha>`). Repair is safe only when those refs are all `refs/remotes/*`. A local branch on a broken object needs its commit re-fetched or rebuilt first.
- A branch with no upstream isn't automatically lost work. Check `gh pr list --head <branch> --state all`. A squash-merged PR leaves the local commits looking unpushed, so compare the files to the merge commit (`git diff --quiet HEAD <merge sha> -- <file>`). Files that differ only because of later PRs are fine.

## 2. Repair (needs the user's yes, then about a minute)
1. Move the empty files, don't delete them: `mkdir -p .git/corrupt-backup-<date>` and `mv` each one to the same relative path under it.
2. Drop the broken remote-tracking refs with `git update-ref -d refs/remotes/origin/<name>`. They're only cached copies of the remote. If `update-ref` says "reference broken", the loose ref file can't be resolved; fetch that branch explicitly (`git fetch origin <branch>:refs/remotes/origin/<branch>`) to overwrite it.
3. Run `git fetch origin`, then `git remote set-head origin -a`.
4. Run `git fsck --no-dangling`. It should exit 0 with no output. Re-check that every worktree is still clean.

Never run `git gc --prune` or delete the backup during repair, because the moved files are the only record of what was broken.
