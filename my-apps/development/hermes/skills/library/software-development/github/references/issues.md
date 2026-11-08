# GitHub Issues Management

Create, search, triage, and manage GitHub issues. Each section shows `gh` first, then the `curl` fallback.

## Prerequisites

- Authenticated with GitHub (see `github-auth` skill)
- Inside a git repo with a GitHub remote, or specify the repo explicitly

### Setup

```bash
if command -v gh &>/dev/null && gh auth status &>/dev/null; then
  AUTH="gh"
else
  AUTH="git"
  if [ -z "$GITHUB_TOKEN" ]; then
    if _hermes_env="${HERMES_HOME:-$HOME/.hermes}/.env"; [ -f "$_hermes_env" ] && grep -q "^GITHUB_TOKEN=" "$_hermes_env"; then
      GITHUB_TOKEN=$(grep "^GITHUB_TOKEN=" "$_hermes_env" | head -1 | cut -d= -f2 | tr -d '\n\r')
    elif grep -q "github.com" ~/.git-credentials 2>/dev/null; then
      GITHUB_TOKEN=$(uv run python "${HERMES_HOME:-$HOME/.hermes}/skills/github/github-auth/scripts/git-credential-token.py")
    fi
  fi
fi

REMOTE_URL=$(git remote get-url origin)
OWNER_REPO=$(echo "$REMOTE_URL" | sed -E 's|.*github\.com[:/]||; s|\.git$||')
OWNER=$(echo "$OWNER_REPO" | cut -d/ -f1)
REPO=$(echo "$OWNER_REPO" | cut -d/ -f2)
```

---

## 1. Viewing Issues

**With gh:**

```bash
gh issue list
gh issue list --state open --label "bug"
gh issue list --assignee @me
gh issue list --search "authentication error" --state all
gh issue view 42
```

**With curl:**

```bash
# List open issues
curl -s \
  -H "Authorization: token $GITHUB_TOKEN" \
  "https://api.github.com/repos/$OWNER/$REPO/issues?state=open&per_page=20" \
  | python -c "
import sys, json
for i in json.load(sys.stdin):
    if 'pull_request' not in i:  # GitHub API returns PRs in /issues too
        labels = ', '.join(l['name'] for l in i['labels'])
        print(f\"#{i['number']:5}  {i['state']:6}  {labels:30}  {i['title']}\")"

# Filter by label
curl -s \
  -H "Authorization: token $GITHUB_TOKEN" \
  "https://api.github.com/repos/$OWNER/$REPO/issues?state=open&labels=bug&per_page=20" \
  | python -c "
import sys, json
for i in json.load(sys.stdin):
    if 'pull_request' not in i:
        print(f\"#{i['number']}  {i['title']}\")"

# View a specific issue
curl -s \
  -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/$OWNER/$REPO/issues/42 \
  | python -c "
import sys, json
i = json.load(sys.stdin)
labels = ', '.join(l['name'] for l in i['labels'])
assignees = ', '.join(a['login'] for a in i['assignees'])
print(f\"#{i['number']}: {i['title']}\")
print(f\"State: {i['state']}  Labels: {labels}  Assignees: {assignees}\")
print(f\"Author: {i['user']['login']}  Created: {i['created_at']}\")
print(f\"\n{i['body']}\")"

# Search issues
curl -s \
  -H "Authorization: token $GITHUB_TOKEN" \
  "https://api.github.com/search/issues?q=authentication+error+repo:$OWNER/$REPO" \
  | python -c "
import sys, json
for i in json.load(sys.stdin)['items']:
    print(f\"#{i['number']}  {i['state']:6}  {i['title']}\")"
```

## 2. Creating Issues

**With gh:**

```bash
gh issue create \
  --title "Login redirect ignores ?next= parameter" \
  --body "## Description
After logging in, users always land on /dashboard.

## Steps to Reproduce
1. Navigate to /settings while logged out
2. Get redirected to /login?next=/settings
3. Log in
4. Actual: redirected to /dashboard (should go to /settings)

## Expected Behavior
Respect the ?next= query parameter." \
  --label "bug,backend" \
  --assignee "username"
```

**With curl:**

```bash
curl -s -X POST \
  -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/$OWNER/$REPO/issues \
  -d '{
    "title": "Login redirect ignores ?next= parameter",
    "body": "## Description\nAfter logging in, users always land on /dashboard.\n\n## Steps to Reproduce\n1. Navigate to /settings while logged out\n2. Get redirected to /login?next=/settings\n3. Log in\n4. Actual: redirected to /dashboard\n\n## Expected Behavior\nRespect the ?next= query parameter.",
    "labels": ["bug", "backend"],
    "assignees": ["username"]
  }'
```

### Bug Report Template

```
## Bug Description
<What's happening>

## Steps to Reproduce
1. <step>
2. <step>

## Expected Behavior
<What should happen>

## Actual Behavior
<What actually happens>

## Environment
- OS: <os>
- Version: <version>
```

### Feature Request Template

```
## Feature Description
<What you want>

## Motivation
<Why this would be useful>

## Proposed Solution
<How it could work>

## Alternatives Considered
<Other approaches>
```

### Planning an initiative as issues (tracking issue + sub-issues)

When the user wants work "broken into tasks" or "a few issues":

1. **Ground every issue in repo evidence first.** Read the README/getting-started/agent files, then grep for concrete defects: stale defaults (date-stamped URLs in `.env.example`), hard-coded owner identifiers (bundle IDs, team IDs, personal domains, `ghcr.io/<owner>`), leftovers from a stack migration, personal tooling hooks in committed agent config. Cite file paths in the issue body, because an issue that only says "improve docs" can't be executed.
2. **One issue per independently-mergeable PR.** Body = Problem (with evidence) → Proposal → `- [ ]` task list → how to verify. Use existing labels (`gh label list`).
3. **Create a tracking issue** with the suggested order and dependencies (which ones can run in parallel), plus a "Done when" checklist.
4. **Link the children as real sub-issues** so the parent shows a progress bar:
   ```bash
   id=$(gh api repos/O/R/issues/<child_number> -q .id)        # numeric .id, NOT the issue number
   gh api -X POST repos/O/R/issues/<parent_number>/sub_issues -F sub_issue_id=$id
   gh api repos/O/R/issues/<parent_number>/sub_issues -q '.[].number'   # verify
   ```
   Take the parent number from `gh issue create`'s printed URL. `gh issue list --search` lags for a while after creation and returns nothing.
5. **Tell the user how execution works:** nothing runs on its own. Per issue: branch → PR whose body says `Closes #N` → CI → the user merges → the issue closes and the parent's progress bar moves. Offer the modes: one at a time in chat (default), parallel delegated children (one PR each), or unattended (kanban/cron). Note which issues can't be verified from the agent's host (no Docker, small disk) and where they should be tested instead.
6. Later scope additions go in as issue **comments** (or task-list edits), not new issues, unless they are a separate PR.

## 3. Managing Issues

### Add/Remove Labels

**With gh:**

```bash
gh issue edit 42 --add-label "priority:high,bug"
gh issue edit 42 --remove-label "needs-triage"
```

**With curl:**

```bash
# Add labels
curl -s -X POST \
  -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/$OWNER/$REPO/issues/42/labels \
  -d '{"labels": ["priority:high", "bug"]}'

# Remove a label
curl -s -X DELETE \
  -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/$OWNER/$REPO/issues/42/labels/needs-triage

# List available labels in the repo
curl -s \
  -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/$OWNER/$REPO/labels \
  | python -c "
import sys, json
for l in json.load(sys.stdin):
    print(f\"  {l['name']:30}  {l.get('description', '')}\")"
```

### Assignment

**With gh:**

```bash
gh issue edit 42 --add-assignee username
gh issue edit 42 --add-assignee @me
```

**With curl:**

```bash
curl -s -X POST \
  -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/$OWNER/$REPO/issues/42/assignees \
  -d '{"assignees": ["username"]}'
```

### Commenting

**With gh:**

```bash
gh issue comment 42 --body "Investigated — root cause is in auth middleware. Working on a fix."
```

**With curl:**

```bash
curl -s -X POST \
  -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/$OWNER/$REPO/issues/42/comments \
  -d '{"body": "Investigated — root cause is in auth middleware. Working on a fix."}'
```

### Closing and Reopening

**With gh:**

```bash
gh issue close 42
gh issue close 42 --reason "not planned"
gh issue reopen 42
```

**With curl:**

```bash
# Close
curl -s -X PATCH \
  -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/$OWNER/$REPO/issues/42 \
  -d '{"state": "closed", "state_reason": "completed"}'

# Reopen
curl -s -X PATCH \
  -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/$OWNER/$REPO/issues/42 \
  -d '{"state": "open"}'
```

### Linking Issues to PRs

Issues are automatically closed when a PR merges with the right keywords in the body:

```
Closes #42
Fixes #42
Resolves #42
```

To create a branch from an issue:

**With gh:**

```bash
gh issue develop 42 --checkout
```

**With git (manual equivalent):**

```bash
git checkout main && git pull origin main
git checkout -b fix/issue-42-login-redirect
```

## 4. Issue Triage Workflow

When asked to triage issues:

1. **List untriaged issues:**

```bash
# With gh
gh issue list --label "needs-triage" --state open

# With curl
curl -s \
  -H "Authorization: token $GITHUB_TOKEN" \
  "https://api.github.com/repos/$OWNER/$REPO/issues?labels=needs-triage&state=open" \
  | python -c "
import sys, json
for i in json.load(sys.stdin):
    if 'pull_request' not in i:
        print(f\"#{i['number']}  {i['title']}\")"
```

2. **Read and categorize** each issue (view details, understand the bug/feature)

3. **Apply labels and priority** (see Managing Issues above)

4. **Assign** if the owner is clear

5. **Comment with triage notes** if needed

## Open-issue status audit ("which are resolved, which are not?")

1. **Resolve repo slugs** by fuzzy-listing (`gh repo list mitchross --limit 300 --json name -q '.[].name' | grep -iE 'word1|word2'`). Missing on GitHub or issues disabled → check Gitea (below).
2. **List open issues** per repo: `gh issue list -R O/R --state open --limit 200 --json number,title,createdAt,labels,comments`.
3. **Read body AND comments** for each: `gh issue view N --json body -q .body` plus `gh issue view N --json comments -q '.comments[-1].body'` (latest status update usually wins). `--comments` alone omits the body.
4. **Check every referenced PR/issue state** in one loop (`gh pr view P --json state,title || gh issue view P --json state,title`), including cross-repo refs (`-R O/other`). Also list recent PRs (`gh pr list --state all --search "<keyword> sort:created-desc"`) — work often lands without `Closes #N`.
5. **Verify live state** for infra issues: a merged PR is not proof of rollout. Check `kubectl get applications -n argocd`, pod images/versions, node list, and whether the item the issue removes is still deployed (e.g. `kubectl get deploy -A | grep <name>`).
6. **Report** one table per repo: issue, verdict (Done / Mostly done / Partly done / Not started / Parked / Perpetual such as Renovate Dependency Dashboards), and the concrete remaining items. End with cleanup suggestions (close duplicates, tick finished checkboxes, trim lists) and ask before editing — don't close or edit issues unprompted.

### Gitea repos (self-hosted)

The API needs the token: unauthenticated requests return **404 even for repos that exist**, so a 404 isn't proof the repo is missing. `$GITEA_TOKEN` is set in the pod env.

```bash
B=https://gitea.vanillax.me/api/v1/repos/<owner>/<repo>; H="Authorization: token $GITEA_TOKEN"
curl -s -H "$H" $B            # open_issues_count, open_pr_counter, has_issues
curl -s -H "$H" "$B/issues?state=open&type=issues&limit=50"
curl -s -H "$H" "$B/pulls?state=open"
```

Pass `type=issues`, because Gitea's `/issues` also returns PRs otherwise. web_extract of a Gitea URL returns no content; use the API instead.

## 5. Bulk Operations

For batch operations, combine API calls with shell scripting:

**With gh:**

```bash
# Close all issues with a specific label
gh issue list --label "wontfix" --json number --jq '.[].number' | \
  xargs -I {} gh issue close {} --reason "not planned"
```

**With curl:**

```bash
# List issue numbers with a label, then close each
curl -s \
  -H "Authorization: token $GITHUB_TOKEN" \
  "https://api.github.com/repos/$OWNER/$REPO/issues?labels=wontfix&state=open" \
  | python -c "import sys,json; [print(i['number']) for i in json.load(sys.stdin)]" \
  | while read num; do
    curl -s -X PATCH \
      -H "Authorization: token $GITHUB_TOKEN" \
      https://api.github.com/repos/$OWNER/$REPO/issues/$num \
      -d '{"state": "closed", "state_reason": "not_planned"}'
    echo "Closed #$num"
  done
```

## Quick Reference Table

| Action | gh | curl endpoint |
|--------|-----|--------------|
| List issues | `gh issue list` | `GET /repos/{o}/{r}/issues` |
| View issue | `gh issue view N` | `GET /repos/{o}/{r}/issues/N` |
| Create issue | `gh issue create ...` | `POST /repos/{o}/{r}/issues` |
| Add labels | `gh issue edit N --add-label ...` | `POST /repos/{o}/{r}/issues/N/labels` |
| Assign | `gh issue edit N --add-assignee ...` | `POST /repos/{o}/{r}/issues/N/assignees` |
| Comment | `gh issue comment N --body ...` | `POST /repos/{o}/{r}/issues/N/comments` |
| Close | `gh issue close N` | `PATCH /repos/{o}/{r}/issues/N` |
| Search | `gh issue list --search "..."` | `GET /search/issues?q=...` |
