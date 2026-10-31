---
name: homelab-app-development
description: "Use when building features in Mitch's own apps."
version: 1.0.0
metadata:
  hermes:
    tags: [deal-scout, radar-ng, news-reader, features, llm, ui]
    related_skills: [claude-code, homelab-gitops-change-prs, diagnosing-bugs]
---

# Building features in Mitch's own apps

Applies to Mitch's self-hosted apps (deal-scout, radar-ng, news-reader and similar): features, UI bugs, LLM features. Coding goes to Claude Code via the `claude-code` hand-off recipe; this skill holds the product rules to put in the child's prompt.

## Procedure

1. Read the repo's AGENTS.md, README and dev docs, then the code you touch. Map the request onto existing endpoints and helpers first.
2. For a UI bug from a screenshot, trace each number on screen to the API field it comes from before you guess. Mismatched numbers usually mean two widgets read different endpoints or different rules.
3. Write the prompt with: verified cause or design, "reuse the existing pipeline, no second filter engine", the exact CI gates from docs, PR title, short plain PR body, never merge.
4. Dispatch in a worktree, report the PR link and gate results.

## LLM features (standing rules)

- Use only the local Qwen on vLLM through LiteLLM (model id currently `qwen3.8-27b`; check `talos-argocd-proxmox/my-apps/ai/README.md` for the live id). No DeepSeek, no `auto` router, no cloud model — Mitch wants it free and local.
- Enforce it in code: a config var with the Qwen default and a guard that refuses non-`qwen` model ids, falling back to the non-AI path. A config typo should never silently route to a paid model.
- Reuse the app's existing LLM client and env (`DIGEST_LLM_URL`, `LITELLM_API_KEY` in deal-scout) so no cluster change is needed.
- Split the work: LLM parses the question into strict JSON filters, validated against known catalogs; code runs the query and computes trends; LLM only narrates the given facts. Drop narrated sentences citing numbers not in the facts.
- Always ship a deterministic fallback (keyword parse, plain facts summary) so the feature works when vLLM is down or busy.
- Make GPU-costly endpoints operator-only and rate-limited, so public visitors cannot load the GPU.
- Keep the call fast (cap tokens, disable thinking only via the mechanism the repo already uses — don't guess request fields). The app must never feel slow or janky.

## deal-scout specifics

- Facebook scraping runs on Mitch's desktop runner with his own login. Never let public visitors trigger FB scrapes (account ban risk); visitor location features use stored data and the in-cluster geocoder (`geocoder-api.geocoder.svc:8000`).
- FB Marketplace `deliveryMethod` is `local_pick_up` or `shipping` (omit for both). Search-result payloads can omit SHIPPING, so trust the filtered URL.
- vLLM `qwen3.8-27b` accepts one image per prompt, so photo-reading features are possible. Run them in a background queue, never on the request path.
- When several feature branches run in parallel, tell each child which shared files (route table, index.html, today.js, find.js) others are editing and to keep its edits there additive.

## Filter and count UI

- Counts on filter chips must be faceted: each facet's count applies every active filter except its own dimension. Compute them in the same server pass that returns the filtered rows, not from a global dashboard summary — otherwise a pill says "1" and opens "0 listings".
- Count every chip row with the same inclusion rules (e.g. hidden/skip rows excluded in both), or the rows disagree with each other.
- Show a 0 count when facets are loaded, so an empty filter is visibly empty.
