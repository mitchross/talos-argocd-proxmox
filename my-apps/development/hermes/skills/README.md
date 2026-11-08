# Skill recovery inventory

The seed restores missing library copies before importing the native snapshot.
Existing library and registry copies retain local edits. Pinned skills reinstall when their source SHA changes.
The snapshot records identifiers, not immutable content or secrets.
See [the operator guide](../../../../docs/domains/ai-gpu/hermes.md#skill-recovery) for fallback and login recovery.

## Native snapshot

9 registry entries have no existing external pin. All 105 existing pins stay pinned.
The snapshot excludes the 101 entries whose names are installed by external pins.

| Category | Snapshot names |
|---|---|
| autonomous-ai-agents | `opencode` |
| creative | `design-md` |
| media | `gif-search`, `songsee` |
| productivity | `box` |
| research | `llm-wiki` |
| software-development | `inspecting-hermes-desktop-dom`, `node-inspect-debugger`, `python-debugpy` |

## Commit-pinned skills

`external-skills.txt` preserves every pin from `origin/main`, including the four exceptions below.
The seed skips snapshot entries whose names are also installed by a pin.

| Source | Pinned entries | Installed names |
|---|---|---|
| DietrichGebert/ponytail | 6 | `ponytail`, `ponytail-audit`, `ponytail-debt`, `ponytail-gain`, `ponytail-help`, `ponytail-review` |
| ayghri/i-have-adhd | 1 | `i-have-adhd` |
| backnotprop/pstack | 55 | `architect`, `arena`, `automate-me`, `benchmark-checklist`, `blast-radius`, `bro`, `correct`, `create-formal-verification-skill`, `create-verification-skill`, `figure-it-out`, `how`, `in-your-own-words`, `interrogate`, `ketchup`, `ketchup-video`, `maintain-formal-verification-skill`, `maintain-verification-skill`, `no-comments`, `poteto-help`, `poteto-mode`, `principle-attack-the-premise`, `principle-boundary-discipline`, `principle-build-the-lever`, `principle-encode-lessons-in-structure`, `principle-exhaust-the-design-space`, `principle-experience-first`, `principle-explain-the-number`, `principle-fix-root-causes`, `principle-foundational-thinking`, `principle-guard-the-context-window`, `principle-laziness-protocol`, `principle-make-operations-idempotent`, `principle-migrate-callers-then-delete-legacy-apis`, `principle-minimize-reader-load`, `principle-model-the-domain`, `principle-never-block-on-the-human`, `principle-outcome-oriented-execution`, `principle-prove-it-works`, `principle-redesign-from-first-principles`, `principle-separate-before-serializing-shared-state`, `principle-sequence-verifiable-units`, `principle-subtract-before-you-add`, `principle-test-behavior-not-implementation`, `principle-type-system-discipline`, `recall`, `reflect`, `setup-pstack`, `sharpen`, `show-me-your-work`, `swarm`, `pstack-tdd`, `pstack-teach`, `technical-writing`, `unslop`, `why` |
| cloudflare/security-audit-skill | 1 | `security-audit` |
| expo/skills | 6 | `expo-router`, `expo-native-ui`, `expo-data-fetching`, `expo-dev-client`, `expo-animation`, `expo-module` |
| mattpocock/skills | 31 | `code-review`, `codebase-design`, `diagnosing-bugs`, `domain-modeling`, `grill-with-docs`, `implement`, `implement-spec`, `improve-codebase-architecture`, `pr`, `prototype`, `research`, `retro`, `tdd`, `to-spec`, `to-tickets`, `triage`, `wayfinder`, `grill-me`, `grilling`, `handoff`, `teach`, `to-questionnaire`, `wait-what`, `writing-for-agents`, `ask-matt`, `setup-matt-pocock-skills`, `wizard`, `git-guardrails-claude-code`, `migrate-to-shoehorn`, `scaffold-exercises`, `setup-pre-commit` |
| pbakaus/impeccable | 1 | `impeccable` |
| vercel-labs/agent-skills | 4 | `react-best-practices`, `react-native-skills`, `composition-patterns`, `web-design-guidelines` |

| Source | Skill | Why the snapshot cannot replace this pin |
|---|---|---|
| mattpocock/skills | `tdd`, `teach` | The native Hub lock is keyed by name; these collide with Pstack's two entries even in different categories |
| backnotprop/pstack | `create-verification-skill`, `why` | Native import reports stale registry paths; the pinned commit still installs |

## Library additions

The library contains 31 skill directories, including archived copies.
These 17 additions supplement the existing authored library. The six edited bundled skills include their supporting files.
`notion` is preserved here rather than dropped: its old registry entry cannot import after upstream split it into `notion-apps` and `notion-cli`.
Archived copies stay under `.archive` rather than being reactivated.

- `.archive/homelab-network-access`
- `.archive/node-hardware-triage`
- `.archive/public-traffic-analysis`
- `autonomous-ai-agents/claude-code`
- `autonomous-ai-agents/codex`
- `autonomous-ai-agents/hermes-agent`
- `media/video-transcribe`
- `productivity/airtable`
- `productivity/docx`
- `productivity/notion`
- `productivity/powerpoint`
- `productivity/xlsx`
- `software-development/dogfood`
- `software-development/github`
- `software-development/hermes-agent-skill-authoring`
- `software-development/radar-local-alerts`
- `web/blocked-page-recovery`
