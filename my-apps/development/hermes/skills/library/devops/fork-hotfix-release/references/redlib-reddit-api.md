# Redlib ↔ Reddit API notes

Redlib uses an anonymous Android-spoofed OAuth token (`MobileSpoofAuth` in `src/oauth.rs`): POST `https://www.reddit.com/auth/v2/oauth/access-token/loid`, Basic auth `base64("ohXpoqrZYub1kg:")`, JSON body `{"scopes":["*","email","pii"]}`, Android headers (`User-Agent: Reddit/Version …/Android 13`, `X-Reddit-Device-Id`, `client-vendor-id`, `x-reddit-*`). Requests go to `https://oauth.reddit.com`.

Symptom of a Reddit block: page shows `Failed to parse page JSON data: expected value at line 1 column 1`; logs show `invalid response … Status code: 403` / `non-JSON 403`. Token refresh does not help.

## Endpoint status (as last observed — re-probe, Reddit changes this)
| Route | Result |
|---|---|
| `/r/<sub>/hot.json`, user pages | 200 |
| `/r/<sub>/comments/<id>/…json`, `/comments/<id>.json` | 403 HTML |
| same with `%2F` encoded separator (upstream 0a3e9cd trick) | 403 HTML — dead |
| `/by_id/t3_<id>.json` | 200 (post metadata) |
| POST `https://gql-fed.reddit.com/` op `PostComments`, persisted hash `314f29c2494fd78c7844ef2c6b09acb4bef5b37ab50b4ddc01691d6d5c8433f8` | 200 with `data.postInfoById.commentForest.trees` |

GraphQL variables must be exactly `{id:"t3_<id>", sortType:"CONFIDENCE", count:200, maxDepth:10, includeConsistencyToken:false, includePremiumAvatarTreatment:false}` (+ optional `focusedCommentContext`, `after`). Unknown/extra `include*` vars → 400 `INVALID_INPUT`. Don't combine a nested `after` cursor with `focusedCommentContext` (→ `DEPENDENCY_FAILURE`).

Alternative upstream approach (if GraphQL dies): scrape `www.reddit.com/svc/shreddit/comments/r/<sub>/t3_<id>?sort=…` HTML fragments (`<shreddit-comment>`); returned 200 with a browser UA.

## Probe recipe (run from the Hermes pod = cluster egress IP)
```
python3 -m venv $TMPDIR/cffi && $TMPDIR/cffi/bin/pip -q install curl_cffi
```
Then in Python: `s=requests.Session(impersonate="chrome")`, get the token as above, copy `x-reddit-loid` from the token response into headers, add `Authorization: Bearer <tok>`, and hit each route in the table. Compare status + content-type; JSON = working, `text/html` 403 = blocked.
