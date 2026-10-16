# Offline knowledge library

Status: desired configuration; verify the rollout gates before retiring NOMAD.

Prerequisites: the existing SMB PVC, Argo CD access, and read access through `kubectl`.

Source of truth: [collections](collections.tsv), [download CronJob](cronjob-library-download.yaml), and [Deployment](deployment.yaml).

Kiwix serves the full English Wikipedia archive and NOMAD's English ZIM collections at `https://kiwix.vanillax.me`.
Maps remain at `https://maps.vanillax.me` through the separate VersaTiles Application.

## Content

The [NOMAD knowledge catalog](https://github.com/Crosstalk-Solutions/project-nomad/blob/54ee30a44902e5c252b477f8685c26ec3064ab72/collections/kiwix-categories.json) supplies the selection.
This configuration includes all six categories and all three tiers, with 59 selected archives plus full English Wikipedia, totaling 200.05 GiB.
The full Wikibooks archive replaces the duplicate no-picture edition. Full Wikipedia is also pinned so a fresh NAS library can rebuild all 60 archives.
Wikipedia Medicine and Bash use October 2026 releases because NOMAD's pinned URLs returned 404.
All archive URLs, sizes, and published SHA-256 checksums were verified on October 16, 2026 UTC.

The FDA drug dataset is not a ZIM archive. It requires a separate reader and is excluded.
NOMAD creator packs and its specialized remedies/conditions interfaces are not Kiwix libraries and are excluded.
This is a pinned library, not an automatic upstream update subscription.

## Download and serving

`collections.tsv` pins each archive URL, byte count, and SHA-256 checksum.
The CronJob checks for missing archives every 15 minutes and downloads into `.downloads/` on the existing `kiwix-data` SMB PVC.
`concurrencyPolicy: Forbid` prevents overlapping runs. Each run can last up to 48 hours.
Kubernetes creates the download Jobs independently of Argo CD’s 30-minute sync timeout.
Interrupted downloads resume. Only verified archives move into the top-level library directory.
Completed archives are skipped using their recorded checksum and file size.
After a replacement verifies, the Job removes older dated archives of the same series and their partial downloads.
Unrelated archives and newer local versions remain. A failed replacement preserves the previous archive.
File-size checks use metadata rather than reading entire archives.

The indexer scans completed archives every 60 seconds and atomically updates an XML catalog in a shared `emptyDir`.
Kiwix monitors this catalog and loads new archives without restarting for each download.
The server and indexer mount the archives read-only. Only the download Job writes archive data.
A failed index update preserves the previous catalog. A failed download leaves other completed archives available.

The first run starts at the next quarter-hour after sync. The initial download can take hours.
Argo CD completes sync without waiting for downloads. The existing library remains available while downloads run.
The Deployment uses `Recreate`, so applying its configuration causes a short restart.
A full download is not required for the existing Wikipedia archive to become ready.

## Verification

List download Jobs with `kubectl -n kiwix get jobs --sort-by=.metadata.creationTimestamp`.
Inspect the newest Job with `kubectl -n kiwix logs job/<job-name>`.
Expect a successful Job and 60 catalog entries: 60 pinned archives.
If a run fails, inspect its logs. The next scheduled run resumes partial downloads and skips verified archives.
Inspect catalog updates with `kubectl -n kiwix logs deployment/kiwix -c library-indexer`.
Check status with `kubectl -n kiwix get cronjobs,jobs,pods,pvc`.

## Updates and rollback

Update the pinned URLs, byte counts, and published checksums in `collections.tsv` through a PR.
The ConfigMap hash changes. New scheduled Jobs use the updated collection list after sync.
An active Job continues with its mounted configuration; the following run checks the updated list.
Old versions are removed only after a verified replacement is available. Rollback may require downloading the previous version again.
The SMB library is backup-exempt and can be downloaded again from these pinned sources while they remain available.

Revert the Kiwix runtime changes through a PR to return to serving top-level ZIM files directly.
Keep NOMAD's duplicate Kiwix route removed; restoring it reintroduces the failing backend.
Downloaded archives remain on SMB through a runtime rollback.
Do not restore the Sync hook: Argo CD terminates long downloads at its 30-minute operation timeout.

## Pinned archives

| Archive | GiB |
|---|---:|
| Medical Library | 0.065 |
| NHS Medicines A to Z | 0.016 |
| Military Medicine | 0.076 |
| CDC Health Information | 0.166 |
| MedlinePlus | 1.811 |
| Wikipedia Medicine | 1.736 |
| LibreTexts Medicine | 1.111 |
| LibrePathology | 0.089 |
| Water Treatment Library | 0.019 |
| Food for Preppers | 0.091 |
| A Library of Knots | 0.026 |
| Canadian Prepper: Winter Prepping | 1.249 |
| Canadian Prepper: Bug Out Roll | 0.819 |
| Ready.gov | 2.263 |
| The Great Outdoors Q&A | 0.132 |
| Amateur Radio Q&A | 0.071 |
| Canadian Prepper: Bug Out Concepts | 2.688 |
| Urban Prepper | 2.091 |
| Canadian Prepper: Prepping Food | 2.012 |
| Post Disaster Resource Library | 0.600 |
| Hundred Rabbits | 0.165 |
| Project Gutenberg: Military Science | 1.200 |
| CD3WD: Appropriate Technology Library | 0.541 |
| TED-Ed | 5.943 |
| Wikiversity | 2.290 |
| LibreTexts Mathematics | 0.774 |
| LibreTexts Physics | 0.521 |
| LibreTexts Chemistry | 2.033 |
| LibreTexts Biology | 2.087 |
| Wikibooks (With Images) | 5.754 |
| TED Conference | 16.890 |
| LibreTexts Humanities | 4.129 |
| LibreTexts Geosciences | 1.107 |
| LibreTexts Engineering | 0.632 |
| LibreTexts Business | 0.782 |
| Woodworking Q&A | 0.098 |
| Motor Vehicle Maintenance Q&A | 0.316 |
| DIY & Home Improvement Q&A | 1.921 |
| iFixit Repair Guides | 3.325 |
| FOSS Cooking | 0.023 |
| Based.Cooking | 0.015 |
| Gardening Q&A | 0.863 |
| Cooking Q&A | 0.221 |
| Learning Self-Reliance: Homesteading | 3.701 |
| Project Gutenberg: Agriculture | 4.221 |
| freeCodeCamp | 0.007 |
| Python Documentation | 0.004 |
| JavaScript Documentation | 0.002 |
| HTML Documentation | 0.002 |
| CSS Documentation | 0.003 |
| Arduino Q&A | 0.241 |
| Raspberry Pi Q&A | 0.278 |
| Node.js Documentation | 0.001 |
| React Documentation | 0.003 |
| Git Documentation | 0.001 |
| Electronics Q&A | 3.925 |
| Robotics Q&A | 0.227 |
| Docker Documentation | 0.002 |
| Linux Documentation | 0.001 |
| Full English Wikipedia | 118.667 |
