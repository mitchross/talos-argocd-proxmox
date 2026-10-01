# Repository hooks

The branch guard runs on `PreToolUse` / `Bash` (including Codex `exec_command`).
Its command resolves the current worktree root, so sessions started in a
subdirectory use that worktree's guard. Claude and Codex shell entrypoints call
one deny-only implementation in `scripts/agent-git-guard.py`.

Enable hooks in the installed Codex version (`features.hooks = true`) and review
new or changed hook definitions in `/hooks`. Codex skips untrusted hooks; a
checked-in configuration alone does not prove enforcement. Verify the guard
appears in `/hooks` after pulling this change. See the
[official hook configuration and trust documentation](https://learn.chatgpt.com/docs/hooks).

The guard checks literal git commit/push commands, quoted `-C` paths, global
`-c` options, obvious default-branch refspecs and compound invocations. It emits
only a denial or no decision; feature commands retain normal permissions. It
is not a shell interpreter: aliases, scripts, variable expansion, dynamic
branch switching, unsupported shell/heredoc syntax and GitHub API writes require normal agent policy and
server-side branch protection. No permission to merge comes from this hook.

Run `python3 -m unittest discover -s scripts/tests -p test_agent_git_guard.py -v`
to test both entrypoints without executing payload commands.
