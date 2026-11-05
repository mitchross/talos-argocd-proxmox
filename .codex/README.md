# Repository hooks

The branch guard runs on `PreToolUse` / `Bash` (including Codex `exec_command`).
Its command resolves the current worktree root, so sessions started in a
subdirectory use that worktree's guard. Claude and Codex shell entrypoints call
one deny-only implementation in `scripts/agent-git-guard.py`.

Enable hooks in the installed Codex version (`features.hooks = true`) and review
new or changed hook definitions in `/hooks`. Codex skips untrusted hooks, so a
checked-in configuration alone does not prove enforcement. After pulling this
change, verify the guard appears in `/hooks`. See the
[official hook configuration and trust documentation](https://learn.chatgpt.com/docs/hooks).

The guard checks literal git commit/push commands, quoted `-C` paths, global
`-c` options, obvious default-branch refspecs and compound invocations. It emits
only a denial or no decision, so feature commands keep normal permissions. It
is not a shell interpreter. Aliases, scripts, variable expansion, dynamic
branch switching, unsupported shell/heredoc syntax and GitHub API writes need
normal agent policy and server-side branch protection. This hook grants no
permission to merge.

Run `python3 -m unittest discover -s scripts/tests -p test_agent_git_guard.py -v`
to test both entrypoints without executing payload commands.
