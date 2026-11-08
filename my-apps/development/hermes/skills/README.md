# Skill recovery inventory

The seed restores missing library copies before importing the native snapshot.
Existing volume copies retain local edits. The snapshot records identifiers, not immutable content or secrets.
See [the operator guide](../../../../docs/domains/ai-gpu/hermes.md#skill-recovery) for fallback and login recovery.

## Native snapshot

110 registry entries: the original 72 Hub records minus the broken `notion` entry,
plus 39 importable entries moved out of `external-skills.txt`.
Pstack `tdd` and `teach` are restored as `pstack-tdd` and `pstack-teach` after import.

| Category | Snapshot names |
|---|---|
| autonomous-ai-agents | `opencode` |
| creative | `design-md`, `impeccable` |
| devops | `security-audit` |
| matt-pocock | `ask-matt`, `git-guardrails-claude-code`, `migrate-to-shoehorn`, `scaffold-exercises`, `setup-matt-pocock-skills`, `setup-pre-commit`, `wizard` |
| media | `gif-search`, `songsee` |
| mobile | `expo-animation`, `expo-data-fetching`, `expo-dev-client`, `expo-module`, `expo-native-ui`, `expo-router` |
| productivity | `box`, `grill-me`, `grilling`, `handoff`, `i-have-adhd`, `to-questionnaire`, `wait-what`, `writing-for-agents` |
| pstack | `architect`, `arena`, `automate-me`, `benchmark-checklist`, `blast-radius`, `bro`, `correct`, `create-formal-verification-skill`, `figure-it-out`, `how`, `in-your-own-words`, `interrogate`, `ketchup`, `ketchup-video`, `maintain-formal-verification-skill`, `maintain-verification-skill`, `no-comments`, `poteto-help`, `poteto-mode`, `principle-attack-the-premise`, `principle-boundary-discipline`, `principle-build-the-lever`, `principle-encode-lessons-in-structure`, `principle-exhaust-the-design-space`, `principle-experience-first`, `principle-explain-the-number`, `principle-fix-root-causes`, `principle-foundational-thinking`, `principle-guard-the-context-window`, `principle-laziness-protocol`, `principle-make-operations-idempotent`, `principle-migrate-callers-then-delete-legacy-apis`, `principle-minimize-reader-load`, `principle-model-the-domain`, `principle-never-block-on-the-human`, `principle-outcome-oriented-execution`, `principle-prove-it-works`, `principle-redesign-from-first-principles`, `principle-separate-before-serializing-shared-state`, `principle-sequence-verifiable-units`, `principle-subtract-before-you-add`, `principle-test-behavior-not-implementation`, `principle-type-system-discipline`, `recall`, `reflect`, `setup-pstack`, `sharpen`, `show-me-your-work`, `swarm`, `tdd`, `teach`, `technical-writing`, `unslop` |
| research | `llm-wiki` |
| software-development | `code-review`, `codebase-design`, `composition-patterns`, `diagnosing-bugs`, `domain-modeling`, `grill-with-docs`, `implement`, `implement-spec`, `improve-codebase-architecture`, `inspecting-hermes-desktop-dom`, `node-inspect-debugger`, `ponytail`, `ponytail-audit`, `ponytail-debt`, `ponytail-gain`, `ponytail-help`, `ponytail-review`, `pr`, `prototype`, `python-debugpy`, `react-best-practices`, `react-native-skills`, `research`, `retro`, `to-spec`, `to-tickets`, `triage`, `wayfinder`, `web-design-guidelines` |

## Explicit pinned exceptions

`external-skills.txt` now contains only these four exceptions, not a second registry install list:

| Source | Skill | Why pinned |
|---|---|---|
| mattpocock/skills | `tdd`, `teach` | The native Hub lock is keyed by name; these collide with Pstack's two entries even when installed in different categories |
| backnotprop/pstack | `create-verification-skill`, `why` | Native import reports stale registry entries whose files no longer exist upstream; the pinned commit still installs |

## Library additions

These 17 directories supplement the existing authored library. The six edited bundled skills include their supporting files.
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
