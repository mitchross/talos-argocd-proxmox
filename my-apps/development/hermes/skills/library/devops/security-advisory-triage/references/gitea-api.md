# Gitea API recipes (token in `$GITEA_TOKEN`)

Check access first; never guess credentials:
```bash
H="Authorization: token $GITEA_TOKEN"
curl -s -H "$H" https://gitea.vanillax.me/api/v1/user | jq -r .login
curl -s -H "$H" https://gitea.vanillax.me/api/v1/repos/<owner>/<repo> | jq '{default_branch,private,open_issues_count,open_pr_counter}'
```

Clone and push without leaving the token in `.git/config` or logs:
```bash
git clone -q "https://<user>:${GITEA_TOKEN}@gitea.vanillax.me/<owner>/<repo>.git" <dir> 2>&1 | sed "s/${GITEA_TOKEN}/***/g"
git -C <dir> remote set-url origin https://gitea.vanillax.me/<owner>/<repo>.git
git push -q "https://<user>:${GITEA_TOKEN}@gitea.vanillax.me/<owner>/<repo>.git" <branch> 2>&1 | sed "s/${GITEA_TOKEN}/***/g"
git ls-remote "https://<user>:${GITEA_TOKEN}@gitea.vanillax.me/<owner>/<repo>.git" <branch>   # confirm the push landed
```

Open a PR (body written to a file first, JSON-escaped with jq):
```bash
body=$(jq -Rs . < pr.md)
curl -s -X POST -H "$H" -H 'Content-Type: application/json' \
  https://gitea.vanillax.me/api/v1/repos/<owner>/<repo>/pulls \
  -d "{\"title\":\"...\",\"head\":\"<branch>\",\"base\":\"main\",\"body\":$body}" \
  | jq -r '"#\(.number) \(.html_url) mergeable=\(.mergeable)"'
```

CI status (Gitea Actions report commit statuses):
```bash
curl -s -H "$H" https://gitea.vanillax.me/api/v1/repos/<owner>/<repo>/commits/<sha>/status \
  | jq -r '.state, (.statuses[] | "\(.context): \(.status)")'
curl -s -H "$H" "https://gitea.vanillax.me/api/v1/repos/<owner>/<repo>/actions/runs?branch=main&limit=6" \
  | jq -r '.workflow_runs[] | "\(.head_sha[0:7]) \(.path) \(.status)/\(.conclusion) \(.started_at)"'
```
Poll the status endpoint every ~30 s until `state` leaves `pending`.
