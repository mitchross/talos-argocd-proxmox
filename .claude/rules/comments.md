# Comment length

Root `CLAUDE.md` § "Comment Style" says *when* a comment is earned. This file caps *how long* it may be, because "earned" keeps getting used to justify paragraphs.

## The cap

**One line. Two if the second genuinely carries new information. Never three.**

If it needs more than two lines, the extra belongs somewhere else:

| Content | Goes to |
|---|---|
| Why this change, what broke, what was tried | commit message / PR body |
| Investigation, symptoms, root-cause theory | Mink note (`mink note --category resources`) |
| Procedure, runbook, architecture | `docs/` |
| The one thing a future editor must not break | the in-file comment |

The file comment answers **"what will bite me if I edit this line?"** — not "what happened last Tuesday."

## Don't

- Narrate forensics. No "this never took; ArgoCD reported success while the live field stayed X, and a hard refresh didn't clear it."
- Restate the YAML. `# port 8787` above `containerPort: 8787` is noise.
- Chain consequences. Pick the one that bites; drop "which is why…" clauses.
- Explain an upstream project's design at length. Link it or name it.
- Justify yourself. The comment is for the next editor, not a defense of the commit.

## Example — an actual violation

Written:

```yaml
# imputnet publishes no frontend image — this community image ships the
# cobalt sources and runs `svelte-kit build` on every container start,
# baking the two WEB_* vars below into the static bundle. So: the rootfs
# must stay writable, and a cold start is a full SvelteKit build (~1-2 min),
# which is what the startupProbe budget below is for.
```

Should have been:

```yaml
# Builds at container start, not image build: rootfs must stay writable, ~1-2 min cold start.
```

Everything else was commit-message and Mink-note material. It was already in both.
