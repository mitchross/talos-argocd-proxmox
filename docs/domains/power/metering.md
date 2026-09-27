# Power & Cost Metering

Every always-on box and both office workstations sit behind a TP-Link Tapo P115
smart plug. Home Assistant reads watts from each plug, integrates them into kWh,
prices that against the live time-of-use electricity rate, and exposes the
result to Grafana. This page is the map of what is metered, how it is grouped,
what it costs, and how to add a plug.

## What is metered

| Plug (HA device) | Entity prefix | Group | What it powers |
|---|---|---|---|
| Threadripper Host | `threadripper_*` | homelab | Threadripper 2950X/X399 host (`192.168.10.14`): GPU worker + general worker VMs, 2× RTX 3090 |
| NAS Drive PSU | `nas_psu_*` | homelab | The drive-shelf PSU for the NAS |
| TrueNAS (DL360) | `truenas_*` | homelab | The TrueNAS/DL360 host itself (`192.168.10.133`) |
| HP SFF + Optiplex | `hp_sff_*` | homelab | **Two hosts on one outlet**: HP 8500 SFF (`.21`) and Dell Optiplex 8500 |
| HP Elite Mini G9 | `hp_elite_*` | homelab | HP Elite Mini 600 G9 (`.22`) |
| Gaming PC | `gaming_pc_*` | office | 7800X3D workstation. **Not a cluster node**; the two AI RTX 3090s are on Threadripper |
| MacBook + Monitor | `macbook_*` | office | Office desk |
| Shed Lab (solar) | `shed_lab_*` | none | HP micro in the shed (`.20`), solar-fed |

**Shed Lab** runs off the shed's own solar and battery bank, so it has watts and
kWh (with the daily/weekly/monthly/yearly meters) but no cost entities, and it is
not in any group or in the house-share numbers. Its supply side (MPPT yield,
battery bank voltage and state of charge) lives in the Grafana **Solar**
dashboard (`shed-solar`).

Household plugs (dryer, TV, office lamps, the garage fridge) exist in Home
Assistant but are outside this accounting: the Prometheus filter only exports
the prefixes above.

### Groups

| Group | Members | Use it for |
|---|---|---|
| `homelab_*` | The five always-on servers | The number to compare against the bill |
| `office_*` | Gaming PC + MacBook | Workstations. Metered and priced, but not locked on, so expected to swing to zero |
| `combined_*` | Everything | Total household draw from metered plugs |

Each group has `<group>_total_power`, `<group>_total_energy` (with
daily/weekly/monthly/yearly meters), `<group>_cost_rate`, `<group>_cost` (same
meters), and the finished-period sensors below.

## How cost is computed

```
device watts ──integration──▶ kWh ──utility_meter──▶ daily / weekly / monthly / yearly kWh
      │
      └──× current all-in rate──▶ USD/h ──integration──▶ USD ──utility_meter──▶ daily / … / yearly USD
```

The all-in marginal rate is `(energy + delivery riders) × (1 + sales tax)`. The
energy component steps between three windows:

| Window | When | All-in rate |
|---|---|---|
| Summer on-peak | June–August, weekdays 14:00–19:00 | ~$0.285 |
| Summer off-peak | June–August, all other hours | ~$0.235 |
| Non-summer | September–May | ~$0.213 |

Rates live in `my-apps/home/home-assistant/configuration.yaml` under
`input_number:`. **Git is the source of truth**: the `initial:` values reset the
UI sliders on every Home Assistant restart, so a permanent rate change goes in
the file, not the dashboard.

Cost integrates a live USD/hour rate rather than applying a flat tariff after
the fact, so a workload that runs only during on-peak hours is priced at on-peak
rates.

### Finished periods

The `*_monthly` sensors are month-to-date and reset on the 1st, so they are the
wrong thing to compare against a bill. Home Assistant's `utility_meter` keeps the
previous cycle in a `last_period` attribute, and template sensors surface it:

| Sensor | What it holds |
|---|---|
| `sensor.<group>_cost_last_month` | Last calendar month's finished total |
| `sensor.<group>_total_energy_last_month` | Last month's kWh |
| `sensor.<group>_cost_yesterday` | Yesterday's finished cost |
| `sensor.<prefix>_cost_last_month` | Per-device, last month |
| `sensor.<prefix>_energy_last_month` | Per-device, last month |

These stop moving once the cycle closes. Compare today-so-far with yesterday
only as partial versus complete totals. Missing previous-period data is shown
as unavailable. A smaller partial-day total does not establish a saving.

## Where to look

| Surface | What it is |
|---|---|
| Grafana **Power & Cost** (`homelab-power-cost`, folder Home & Energy) | Mirrors HA's Overview/Devices/House views: draw, cost today/month/year, per-device table, 14-day trends, and per-plug volts/amps in a collapsed row |
| Grafana **Gaming PC** (`gaming-pc`) and **Cooling** (`ac-cooling`) | Mirror HA's Gaming and Cooling views, with 14-day per-day history |
| Home Assistant **Homelab Power** dashboard | Overview, Daily spend, Bill breakdown, Rates & savings, Devices, House, Solar, Gaming, Cooling, and Settings |
| HA **Energy** dashboard | Configured in the UI; each `sensor.<prefix>_energy` is an Individual device |

### How Grafana names a plug

The dashboards do not carry a device list. Every query selects the entity IDs
for its group and derives the display name from the metric's `friendly_name`
label by stripping the trailing metric words (`Power`, `Energy`, `Cost`,
`Voltage`, `Current`, `Share`). That is why `customize.yaml` sets every
friendly name to `<Device> <Metric ...>`, and why a device display name must
not itself contain one of those words.

### Reading the numbers

**The idle floor is the bill.** Peak draw is brief; the 24-hour minimum runs
8,760 hours a year. When the *Baseline Cost / Year* panel accounts for most of
*Cost This Year*, workload tuning will not move the number. Only removing or
consolidating hardware does.

**Run-rate panels are what-ifs, not forecasts.** *Run-Rate / Year* and *Cost /
Year If Left At This Draw* annualise the current instant to answer "what does
leaving this on cost me?". Use *Cost This Month* or *Cost Last Month* for a bill
estimate.

**The HP SFF plug cannot be attributed.** It feeds two hosts. Split the outlet
before concluding which of the two to retire.

## House-level data from Consumers Energy

The plugs only see the homelab. The whole-house number comes from the utility:
a daily CronJob (`my-apps/home/consumers-energy-sync/`) drives a headless
Chromium through the Consumers Energy portal, downloads the *Share data → CSV*
export (one row per day, trailing 30 days, with CE's own cost), and pushes it
into Home Assistant. Source and image: `github.com/mitchross/consumers-energy-sync`.

| What lands | Where it shows |
|---|---|
| `consumers_energy:grid_kwh`, `consumers_energy:grid_cost` (long-term statistics) | HA Energy dashboard grid source with cost; `statistics-graph` cards |
| `sensor.consumers_energy_kwh_yesterday`, `_kwh_7d`, `_kwh_month`, `_kwh_last_month` and the `_cost_*` twins | Homelab Power dashboard, Grafana via the Prometheus exporter |
| `sensor.homelab_share_of_house`, `sensor.combined_share_of_house` | Homelab kWh yesterday as a share of the house |
| `sensor.consumers_energy_effective_rate` | CE cost / kWh yesterday, next to the modelled rate |

The importer sets nine live sensors through the REST API, including
`sensor.consumers_energy_last_reading`. Those states normally disappear on an
HA restart even though recorder history and statistics persist. The local
`consumers_energy_restore` integration restores the last recorded values after
HA starts. Its source lives in `scripts/consumers-energy-restore/` and the config
copier installs it under `/config/custom_components/consumers_energy_restore`.

Recovery reads the SQLite recorder in a worker thread and preserves the original
reading date. It requires all nine recorded states and skips recovery if a newer
import has already populated any of them. Missing or invalid history leaves the
comparisons unavailable until the next successful daily import at 13:17. Derived
rates and shares recompute from the restored inputs. This integration assumes
the current local SQLite recorder; revisit it if the recorder moves to another
database backend.

**Running it elsewhere.** The same image runs anywhere with the same env vars
(`CE_PORTAL_USERNAME`, `CE_PORTAL_PASSWORD`, `HASS_URL`, `HASS_TOKEN`):

```bash
# local checkout: node --env-file=.env index.mjs [--download-only|--import-only|--dry-run]
docker run --rm --user 1001:1001 --env-file .env -v ce-data:/data \
  ghcr.io/mitchross/consumers-energy-sync:v0.1.4
```

`/data` holds the Playwright cookie jar (a credential) and the CSVs; keep it
private. The first run logs in with the password; later runs reuse the cookie
jar. A failed run leaves a full-page screenshot in `/data`.

**Cumulative sums.** Each import bases its running total on what HA already
holds just before the export window, so overlapping trailing windows stay
consistent. Importing data *older* than what HA has breaks that: clear both
statistics first (`recorder.clear_statistics`) and import oldest-first.

**Releasing a new image.** Tag the sync repo (`git tag v0.x.y && git push --tags`);
the workflow publishes to GHCR. Bump the tag and digest in `cronjob.yaml`.
The base image version must equal the `playwright` version in `package.json`.

## Safety: the power-off lockout

The `Homelab plug power-off lockout` automation turns any homelab plug back on
if it is switched off and raises a persistent notification. It covers the five
homelab plugs. The office plugs are deliberately excluded: those machines are
meant to be powered down.

Hiding a switch via `customize.yaml` is cosmetic only; the automation is the
real enforcement. **To intentionally power-cycle a plug, disable the automation
first.**

> The automation triggers on switch entity IDs (`switch.threadripper`,
> `switch.hp_sff`, …). A typo there fails silently: the automation loads fine
> and simply never fires. Verify a change against
> **Developer Tools → States** before trusting it.

## Adding a plug

1. Adopt the plug in the Tapo app, then add it to Home Assistant through the
   TP-Link integration. Rename the device in HA to the display name you want,
   then rename its entities so they share one short prefix (`sensor.<prefix>_current_consumption`,
   `switch.<prefix>`, …). The prefix is permanent: renaming it later orphans
   every statistic recorded under it.
2. In `my-apps/home/home-assistant/configuration.yaml`, add
   `sensor.<prefix>_*` to `prometheus.filter.include_entity_globs`, then add its
   energy integration, cost integration, four energy `utility_meter`s, four cost
   `utility_meter`s, a `*_cost_rate` template, `*_cost_last_month` and
   `*_energy_last_month` templates, and a `*_power_share` template. Add it to
   the `Total Power` template of its group and of `combined`.
3. Add `friendly_name` entries in `customize.yaml` (`<Device> <Metric ...>`
   form), and the switch to the lockout automation if the device must stay on.
4. Add it to `lovelace-homelab-power.yaml`, and to the entity regex of the
   per-plug queries in both Grafana dashboards under
   `monitoring/prometheus-stack/dashboards/`. Those are plain `.json` files
   assembled into ConfigMaps by `configMapGenerator`; edit the `.json`, never a
   rendered manifest.
5. Add `sensor.<prefix>_energy` as an Individual device on the HA Energy dashboard.

> **The `name:` slug must equal the entity prefix.** Home Assistant derives the
> entity ID from `name:`, so `name: "HP SFF Energy"` produces
> `sensor.hp_sff_energy`. If the slug drifts, every template and dashboard
> reference silently reads nothing: no error, just empty panels.

Changes reach the pod through hashed ConfigMaps and an initContainer that
copies files onto the PVC. A merged PR changes the pod's ConfigMap references,
so ArgoCD automatically performs a `Recreate` rollout. This briefly interrupts
Home Assistant. Do not copy config into the live PVC or manually restart the
Deployment to publish changes. Revert dashboard/config changes through a PR.

Verify afterwards:

```bash
# the new sensors exist and are numeric
kubectl exec -n home-assistant deploy/home-assistant -c home-assistant -- \
  sh -c 'wget -q -O- http://127.0.0.1:8123/api/prometheus | grep <prefix>_energy_daily'
```

Newly created integrations and utility meters start at zero. Totals only fill in
as data accumulates; an empty panel on day one is expected, not a bug.

## Daily comparisons and bill allocation

**Daily spend** puts group and per-plug dollars and kWh beside yesterday's
completed totals. Previous-day values come from each daily utility meter's
`last_period`, checked against its local `last_reset` date. Segmented bars show
how the tracked loads contribute to cost; the Devices view does the same for
watts. The graph cards fill their sections on desktop and collapse on phones.

**Bill breakdown** separates energy share from estimated cost share. Its
non-overlapping buckets are homelab, office, modeled cooling, and the remainder.
Gaming is already in office. The solar shed is never included. Cost remainder
also contains the difference between the configured marginal rate and CE's
reported cost; it is not a measured appliance load. Negative remainders stay
visible so a model mismatch cannot masquerade as perfect attribution.

`power-insights.yaml` holds these derived sensors. House comparisons are only
available when `consumers_energy_last_reading` equals yesterday's local date
and both utility totals exist. A late report or missing recovery history produces
unavailable comparisons, not zero consumption. Startup recovery preserves the
report date, so an old report cannot pass the freshness check.

**Rates & savings** translates a constant load into dollars/day and dollars/30
days at the configured current rate. These are what-if calculations, not bill
forecasts or newly verified utility tariffs. Fixed monthly fees are excluded.
The three rate windows and permanent GitOps rate settings remain unchanged.

## September 24 statistics repair

The recorder contains a verified discontinuity: hourly power statistics stop
at **2026-09-24 14:00 UTC** and resume at **23:00 UTC** with their cumulative
`sum` near zero, while meter `state` values continue increasing. For example,
homelab energy goes from 247.005 to 252.296 kWh while its statistical sum drops
from 104.892 to 0.309. This explains the negative daily bars and understated
monthly graph. The first retained homelab cost statistic is September 16, so
even after repair its September chart covers less time than the monthly meter
tile. The dashboard labels this partial history. The available evidence
establishes the statistics discontinuity;
it does not establish which maintenance operation caused it.

The repo-owned `scripts/repair-power-statistics.py` initContainer runs while HA
is stopped under the Deployment's `Recreate` strategy. It only considers the
explicit power-entity pattern and the two exact hourly boundary timestamps.
The offset is `previous.sum + (next.state - previous.state) - next.sum`.
Both timestamps are on the same local day, with no daily, weekly, monthly or
yearly cycle boundary between them. It adds that offset to subsequent long-
and short-term sums; meter states, CE imports, and unrelated statistics stay
unchanged. Surviving cumulative readings recover the day's total across the
gap, but do not reconstruct when during those missing hours energy was used.

Before writing, it saves affected row IDs, timestamps and original sums in
`/config/statistics-repairs/power-2026-09-24.json`, then updates in one SQLite
transaction. Unexpected boundary data aborts the initContainer. A fresh
installation or repaired database is a no-op. The September 27 read-only
export yielded 130 repairable series; a local replay and repeat run verified
the offsets and idempotence. No production database was changed during review.

After merge, verify the GitOps rollout and init logs:

```bash
kubectl -n home-assistant rollout status deployment/home-assistant
kubectl -n home-assistant logs deployment/home-assistant -c repair-power-statistics
```

Expected: a repair list and saved journal on the first rollout, then an empty
repair list on later starts. Check the September 24 daily bars, monthly cost
graph, and new dashboard tabs. CE comparison sensors may remain unavailable
until the next successful utility import.

For a failure, retain the journal and inspect the init log. Do not delete the
recorder database or zero the meters. A code revert does not undo a committed
statistics repair. To undo, first use a PR to remove the repair initContainer
and stop HA through GitOps (`replicas: 0`). With the PVC mounted by an approved
maintenance workload and HA stopped, run the same repository script:

```bash
python /opt/repo-scripts/repair-power-statistics.py --apply --undo
```

This reverses the recorded offsets, including later rows that inherited the
corrected baseline. It restores the original graph discontinuity. Restore
`replicas: 1` through a PR after checking the result. The journal is retained
on the backed-up config PVC for inspection.

## Resetting the history

Home Assistant keeps three kinds of state, and a "start fresh" has to clear all
three or the old totals come back:

| State | Where | How to clear |
|---|---|---|
| Recorder history + long-term statistics | `/config/home-assistant_v2.db` (+ `-wal`, `-shm`) on the PVC | Delete the files with HA stopped; it creates a fresh DB on start |
| Running totals of every `integration` and `utility_meter` sensor | `/config/.storage/core.restore_state` | Delete the file with HA stopped. HA rewrites it on every clean shutdown, so a `kill -9` of the `homeassistant` process after deleting is what makes it stick |
| Grafana history | Prometheus, 15-day retention | Nothing to do; old series age out |

Renaming an entity prefix is the same operation from Home Assistant's point of
view: the new prefix starts at zero and the old one is orphaned.

## Shed solar

```
panels → EPEVER XTRA3210N MPPT → 12.8 V LiFePO4 bank (2 × 100 Ah) → LOAD → Anker SOLIX → HP micro (Tapo Shed Lab)
                    │
                    └─ Modbus RTU over USB serial → rpi4 (192.168.10.174) → `epsolar` service
```

The rpi4 is the only host with the serial link. Its `epsolar` service
(github.com/mitchross/epsolar, private) polls the controller every 5 s, runs
the guarded LOAD automation, and serves two feeds:

| Feed | Consumer |
|---|---|
| `:8080/metrics` (`epever_*`, `epsolar_*`, `solar_buffer_*`) | cluster Prometheus, job `epever-solar` (`monitoring/prometheus-stack/values.yaml`) |
| `:8080/api/v1/status` (JSON) | Home Assistant `rest:` sensors `sensor.solar_*` / `binary_sensor.solar_*` (30 s) |

Grafana: **Solar** (`dashboards/home-energy/shed-solar.json`), which mirrors
HA's Solar view and keeps the epsolar controller internals in a collapsed row.
Home Assistant: the **Solar** view of the
Homelab Power dashboard. kWh counters are the controller's own lifetime
totals.

The shed is off-grid, so keep it **out of the HA Energy dashboard**: that page
models one house where solar feeds "Home", so adding `solar_generated_total`
as a solar source or `shed_lab_energy` as a device inflates home consumption
and shows 100 % self-sufficiency. The Energy dashboard is grid-only; the shed
lives on the Solar view and the Grafana solar pages.

If the Pi is down every `solar_*` sensor goes unavailable and the Prometheus
target shows `up == 0`; nothing on the grid side is affected.

## Gaming sessions

`binary_sensor.gaming_pc_gaming` is on while the Gaming PC plug draws more than
`input_number.gaming_pc_active_threshold_w` (350 W; idle is ~200 W, gaming
gaming is 450–600 W) and turns off after five quiet minutes. Three template
feeds are integrated only while it is on:

| Sensor | Meaning |
|---|---|
| `sensor.gaming_pc_gaming_energy` / `_cost` (+ daily/weekly/monthly/yearly meters) | kWh and USD spent gaming |
| `sensor.gaming_pc_gaming_hours` (+ meters) | hours gamed, from integrating a 1/0 flag, so it does not depend on recorder retention |
| `sensor.gaming_pc_idle_cost_daily` / `_monthly` | the rest of the PC's cost: total minus gaming |

Grafana **Gaming PC** (`gaming-pc.json`) and the **Gaming** view of the Homelab
Power dashboard read these. The threshold is a slider so it can be tuned without
a deploy; a permanent change goes in `configuration.yaml`.

## AC cooling (modeled)

The central AC has no plug meter, so its cost is **modeled**, not measured:
`binary_sensor.ac_cooling` is on while the Google Nest (`climate.hallway_hallway`)
reports `hvac_action: cooling` (fan-only runs read `fan` and are not counted),
and the runtime is priced at `input_number.ac_cooling_wattage` (placeholder 3500 W)
× the live TOU rate — the same integration pipeline as the gaming sessions.

| Sensor | What it holds |
|---|---|
| `sensor.ac_cooling_energy` / `_cost` / `_hours` (+ daily/weekly/monthly/yearly meters) | Modeled AC kWh, USD, and cooling hours |
| `sensor.ac_cooling_cost_yesterday` / `_cost_last_month`, `_hours_*`, `_energy_last_month` | Finished periods, from `last_period` |
| `sensor.ac_cost_per_cooling_hour` | Month-to-date USD per cooling hour |
| `sensor.ac_share_of_house_yesterday` | AC cost as a % of the CE-billed house cost yesterday |
| `sensor.ac_implied_watts_yesterday` | **Calibration gauge**: (CE house kWh − metered plugs − `input_number.ac_house_baseline_kwh`) ÷ cooling hours |

**Calibration loop:** on 2–3 hot days with no dryer/oven/EV, compare
`ac_implied_watts_yesterday` to `ac_cooling_wattage`; nudge the slider toward the
median implied value, then commit it as `initial:` in `configuration.yaml`
(Git is source of truth; the UI slider resets on HA restart). Month-end check:
`ac_cooling_cost_last_month` + `combined_*` + baseline should land within ~10–15%
of the CE bill; the wattage is an estimate (±20 % on a variable-speed unit).
CE data is one day late, so every house comparison is yesterday-vs-yesterday.
Because the 3 min `delay_off` over-counts runtime on short cycles, implied watts
reads low on those days — calibrate from long, sustained cooling days.

Dashboards: the **Cooling** view of the Homelab Power dashboard and the AC tile
on its House view; `sensor.ac_*` / `binary_sensor.ac_cooling` are in the
Prometheus filter globs, so Grafana can read them.

## Rolling findings and hardware comparisons

The **Findings** view uses `sensor.power_spending_analysis`, a local integration
whose source is `scripts/power-analysis/`. It refreshes hourly after HA starts,
reads the SQLite recorder in an executor thread, and is excluded from recorder
history itself. The view is in `lovelace-power-findings.yaml`; the existing
Overview remains the landing page.

The analysis uses the preceding 14 local days, excludes today, and requires a
common set of complete hourly readings across the seven plug-energy series,
homelab/office groups, detected gaming energy, and cooling hours. It needs the
previous hourly boundary and matching CE daily energy/cost records. Missing
hours, nonfinite values, counter discontinuities, and impossible gaming/runtime
values exclude the day. Local-day length handles daylight saving transitions.
This establishes recorded coverage; it cannot prove every physical sensor was
accurate or responsive throughout the day.

Device ranking shows average watts and 720-hour projections at the current
configured rate. Neither is an idle-only measurement or a full-month bill.
Cooling correlation needs at least seven matched days and one hour of runtime
variation. A fit against house energy minus computer energy is shown for
investigation only. Its largest positive residual identifies a day to review;
it cannot identify an appliance. The report does not change assumed AC wattage.

Use the `power-analysis` agent skill (shared procedure:
`.claude/commands/power-analysis.md`) for repeatable analysis and safe accounting.
The CLI emits the same report read-only; omit `--rate` to leave projections
unpriced when the live configured rate is unknown.

### Reassessing Threadripper vs the spare DL360

The owner's confirmed arrangement retains both RTX 3090s, using an external
GPU PSU and PCIe risers with the DL360. Physical feasibility was established by
prior use. Mink's historical compute inventory lists two E5-2680 v4 CPUs and
conflicting RAM totals (736 GB, 724.24 GiB OS-visible, and approximately
768 GB physical claims); current installed CPUs and DIMMs still need verification. The separate NAS has one E5-2680 v4 and 384 GB, per the September
20 inspection. Do not substitute its power reading for the spare GPU server.

On September 27, a read-only trailing-24-hour Prometheus sample showed about
222.4 W at the Threadripper outlet (1,437 samples across HA pod changes) and
48.4 W combined GPU board power (5,760 samples per GPU). GPU utilization averaged
about 0.3% per GPU across those samples. These clocks and measurement boundaries
are close but different: the roughly 174 W difference includes CPU/RAM/drives,
other host work, fans, and PSU losses. It is not a measured CPU-only idle figure
or guaranteed removable overhead. The earlier 246.6 W average covers a different,
eight-day cohort.

The first local Mink search found only an empty comparison note. The owner
subsequently supplied historical chat extracts on September 27 with numerical
readings. These are owner-reported historical observations; raw meter exports
were not independently recovered. They support the earlier Threadripper move
for the old dual-CPU DL360 configuration. A changed single-CPU arrangement still
needs a new measurement. A matched comparison should include:

- the same two GPUs, power caps, model, context, concurrency, and completed work;
- all wall outlets including the external GPU supply;
- both idle energy and Wh per inference workload, with tokens/sec and latency;
- PCIe link width/speed under load and one-vs-two CPU memory/slot dependencies.

At $0.21328/kWh, saving 25/50/100 W continuously is $3.84/$7.68/$15.36 per 30 days.
A low-power single-Xeon trial is a plausible candidate, not an established winner.
More RAM helps when the workload needs it; the NAS has demonstrated ARC read
benefits, while sustained and durable writes remain bounded by storage/network
behavior. See [NAS measurements](../../nas-performance.md),
[HPE DL360 Gen9 platform features](https://support.hpe.com/hpesc/public/docDisplay?docId=c04442953&docLocale=en_US&page=GUID-A8ED5EBD-51AB-4EDC-AEAA-FA318CF1B483.html),
and [TrueNAS caching and write behavior](https://www.truenas.com/docs/references/zilandslog/).


### Historical power readings supplied by the owner

These records span different configurations and measurement boundaries. They
are reference observations, not new live entities or values to backfill into
recorder statistics.

| Period and measurement | Reported draw | Boundary / limitation |
|---|---|---|
| February whole-basement plug | ~571 W / 13.7 kWh/day | Earlier configuration and all equipment on that feed |
| April post-tuning whole-rack trend | ~620 → 520 → 484 W | Attributed in the old account to low-power settings and GPU limits; not a controlled isolation of each change |
| May whole-rack Tapo | 484 W mean/median; central 80% 472–498 W; p99 ~640 W | Both servers, external supplies, switches and fan; p99 is not maximum |
| May Proxmox DL360 iLO | 240 W average / 318 W peak | Excludes external GPU supply; do not compare iLO directly with AC plug readings |
| May NAS iLO | 85 W average / 139 W peak | Old E5-2640 v3 / 160 GB configuration; drive PSU separate |
| June owner-reported plug averages | DL360 host 259 W + GPU supply 66 W ≈ 325 W | Dual E5-2680 v4, large RAM configuration; llama-swap unloading models |
| June owner-reported Threadripper plug average | 246 W | 2950X, 128 GB and both 3090s on one plug |
| June NAS plus drive PSU | ~125–133 W | Other dated accounts give host 77–82 W plus supply 48–51 W |
| September 5 audit snapshots | Threadripper 182 W; NAS 114 W + drive PSU 43 W | Threadripper had one GPU then; NAS later E5-2680 v4 / 384 GB |
| September 6 historical baseline | Threadripper ~230–240 W, peak 764.7 W | Second 3090 restored; baseline and peak are different statistics |

The June host comparison is approximately **325 − 246 = 79 W** in favor of
Threadripper, or **$12.13 per 30 days / $147.60 per 365-day year** at the current
configured $0.21328/kWh. The old reported NAS-inclusive totals (~452 versus
~371 W) give about 81 W because their components were rounded. These savings
are repriced historical scenarios, not current utility-bill promises.

Another June 18 account reported host-only 334 W for DL360 and 135 W for
Threadripper, plus a separate GPU feed at ~60 W settled or 230–450 W active.
Adding those gives 394 versus 195 W settled, 564 versus 365 W at the lower GPU
load, and 784 versus 585 W at the higher load. These are calculated alternatives
for the SAME GPUs, not synchronized whole-system tests, and are not the same
observation as the later 259/66/246 W averages.

The May allocation (205 W host, 125 W GPUs/supply, 110 W NAS/drives, 30 W network,
15 W fan) approximately reconciles the 484 W rack meter. Those allocations do
not establish individually measured component watts or a universal 15% iLO
error. The external PSU's 1,000 W rating is capacity, not draw.

Old summaries calling Threadripper retired or inferring a return to DL360 from
stale August memory are superseded by the verified September Threadripper
configuration. Likewise, historical "unmeasured desktop/mini" labels do not
override their current HA plug readings. Keep the old NAS CPU/RAM configuration
separate from today's E5-2680 v4 / 384 GB evidence.
