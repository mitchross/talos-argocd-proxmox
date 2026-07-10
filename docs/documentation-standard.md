# Documentation reader contract

This repository is both a running platform and a learning environment. Its
documentation should help a newcomer understand the design without pretending
that cluster operations are risk-free or universally portable.

## What every document should tell the reader

Start with the smallest useful context:

1. **Purpose:** what question this document answers.
2. **Status:** current truth, future plan, historical decision, or runbook.
3. **Scope:** what the procedure changes and what it deliberately leaves alone.
4. **Prerequisites:** access, tools, backups, and expected starting state.
5. **Action:** copyable steps with placeholders clearly marked.
6. **Expected result:** observable output after each risky or important step.
7. **Failure path:** when to stop, how to inspect the problem, and how to roll back.
8. **Source of truth:** links to the owning manifests and canonical deeper guide.

Do not assume that a reader knows Argo CD, Kustomize, Kubernetes controllers,
or repository-specific history. Define a term when misunderstanding it could
cause a bad change. Explain why a non-obvious setting exists next to the setting
itself, while keeping long background material in one canonical document.

## Choose the right document shape

| Reader need | Shape | Required evidence |
|---|---|---|
| Learn a concept | Guide with a small example and diagram where useful | Reader can explain the flow and locate its manifests |
| Perform an operation | Numbered runbook | Preconditions, commands, expected output, rollback |
| Diagnose a failure | Symptom → checks → causes → fixes | Each check distinguishes between at least two causes |
| Review architecture | Current-state document plus explicit limitations | Links to live configuration and known trade-offs |
| Consider a future change | Plan/PRD marked as not implemented | Adoption trigger, phases, acceptance checks, deferred items |
| Understand a decision | Short decision record | Context, choice, alternatives, consequences |

## Make guides interactive safely

Interactivity means the reader can confirm understanding and cluster state; it
does not mean every page needs JavaScript.

- Prefer read-only discovery commands before mutation commands.
- Put destructive commands behind a warning and a confirmation checkpoint.
- Follow commands with a representative result or a precise success condition.
- Use `<namespace>`, `<cluster-id>`, and similar obvious placeholders; never
  publish real credentials or silently reusable production identifiers.
- Add small exercises, render previews, diagrams, or simulators when they make
  controller ordering and failure behavior easier to understand.
- Provide a no-cluster path where practical, such as `kustomize build`, schema
  validation, or a sample object that lets the reader inspect the result.
- End operational guides with verification and rollback, not merely deployment.

## Keep one source of truth

Inline YAML comments explain local syntax and the reason a setting cannot be
removed casually. Domain documents explain the complete design. Runbooks own
procedures. Other pages should link to those sources instead of copying them.

When behavior changes, update in the same pull request:

- the manifest and its non-obvious inline comment;
- the canonical architecture or runbook page;
- the docs navigation/index if discoverability changes;
- validation commands, examples, and stated limitations;
- any future plan whose assumptions became current or stale.

## Review checklist

Before publishing a documentation change, verify:

- [ ] A new reader can tell current state from future intent.
- [ ] Commands identify where they run and which values must be replaced.
- [ ] Risky steps have a stop condition, expected result, and rollback.
- [ ] Links point to the canonical guide and live manifest rather than a second
      copy of the same explanation.
- [ ] Examples match rendered resources and current controller terminology.
- [ ] The page is reachable from the MkDocs navigation or a parent index.
- [ ] `mkdocs build --strict` succeeds.

Clarity is an operational control: if a setting cannot be explained, it is not
ready to become a hidden dependency of cluster recovery.
