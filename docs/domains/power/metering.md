# Power and cost metering

This page answers what each machine costs to run, where to read that number, and how
to add a plug. The later sections are reference detail for each part of the pipeline.

Every always-on machine and both office workstations sit behind a TP-Link Tapo P115
smart plug. Home Assistant reads watts from each plug and integrates them into kWh.
It prices the kWh against the live time-of-use electricity rate and exports the
result to Grafana.

## What is metered

| Plug (HA device) | Entity prefix | Group | What it powers |
|---|---|---|---|
| Threadripper Host | `threadripper_*` | homelab | Threadripper 2950X/X399 host (`192.168.10.14`): the GPU worker VM with 2× RTX 3090 |
| NAS Drive PSU | `nas_psu_*` | homelab | The drive-shelf PSU for the NAS |
| TrueNAS (DL360) | `truenas_*` | homelab | The TrueNAS/DL360 host itself (`192.168.10.133`) |
| HP SFF + Optiplex | `hp_sff_*` | homelab | HP 8500 SFF (`.21`). The plug name still says Optiplex, but that host is retired |
| HP Elite Mini G9 | `hp_elite_*` | homelab | HP Elite Mini 600 G9, the bare-metal worker `hp-elite-gen13` |
| Gaming PC | `gaming_pc_*` | office | 7800X3D workstation. **Not a cluster node.** The two AI RTX 3090s are on Threadripper |
| MacBook + Monitor | `macbook_*` | office | Office desk |
| Shed Lab (solar) | `shed_lab_*` | none | HP micro in the shed (`.20`), solar-fed |

Shed Lab runs off the shed's own solar panels and battery bank. It has watts and kWh,
with the daily, weekly, monthly and yearly meters, but no cost entities. It is not in
any group or in the house-share numbers. See [Shed solar](#shed-solar).

Household plugs (dryer, TV, office lamps, the garage fridge) exist in Home Assistant
but are outside this accounting. The Prometheus filter exports only the prefixes in
the table.

### Groups

| Group | Members | Use it for |
|---|---|---|
| `homelab_*` | The five always-on servers | The number to compare against the bill |
| `office_*` | Gaming PC + MacBook | Workstations. Metered and priced, but not locked on, so they can drop to zero |
| `combined_*` | Everything | Total household draw from metered plugs |

Each group has `<group>_total_power`, `<group>_total_energy` and `<group>_cost`,
each with daily, weekly, monthly and yearly meters. Each group also has
`<group>_cost_rate` and the [finished-period sensors](#finished-periods).

## Where to look

| Dashboard | What it shows |
|---|---|
| Grafana **Power & Cost** (`homelab-power-cost`, folder Home & Energy) | The same data as HA's Overview, Devices and House views: draw, cost today/month/year, per-device table, 14-day trends, and per-plug volts/amps in a collapsed row |
| Grafana **Gaming PC** (`gaming-pc`) and **Cooling** (`ac-cooling`) | The same data as HA's Gaming and Cooling views, with 14-day per-day history |
| Home Assistant **Homelab Power** dashboard | Overview, Daily spend, Bill breakdown, Rates & savings, Devices, House, Solar, Gaming, Cooling, and Settings |
| HA **Energy** dashboard | Configured in the UI. Each `sensor.<prefix>_energy` is an Individual device |

### How to read the numbers

**The idle floor is the bill.** Peak draw is brief, but the 24-hour minimum runs
8,760 hours a year. When the *Baseline Cost / Year* panel accounts for most of
*Cost This Year*, workload tuning does not move the number. Only removing or
consolidating hardware does.

**Run-rate panels are what-ifs, not forecasts.** *Run-Rate / Year* and *Cost / Year
If Left At This Draw* multiply the current instant to a full year. They answer "what
does it cost to leave this on?" Use *Cost This Month* or *Cost Last Month* for a bill
estimate.

**The HP SFF plug cannot be attributed.** It feeds two hosts. Split the outlet before
you decide which of the two to retire.

## How cost is computed

```
device watts ──integration──▶ kWh ──utility_meter──▶ daily / weekly / monthly / yearly kWh
      │
      └──× current all-in rate──▶ USD/h ──integration──▶ USD ──utility_meter──▶ daily / … / yearly USD
```

The all-in marginal rate is `(energy + delivery riders) × (1 + sales tax)`. The
energy part changes between three windows:

| Window | When | All-in rate |
|---|---|---|
| Summer on-peak | June–September, weekdays 14:00–19:00 | ~$0.285 |
| Summer off-peak | June–September, all other hours | ~$0.235 |
| Non-summer | October–May | ~$0.214 |

The October 2026 bill confirms the season boundary. It bills September 15–30 at
summer rates and October 1–14 at the non-summer rate. Per-kWh riders on that bill
total $0.122290, and sales tax is 4%.

Home Assistant integrates a live USD/hour rate. It does not apply a flat tariff
afterward. A workload that runs only during on-peak hours is therefore priced at
on-peak rates.

Rates are in `my-apps/home-automation/home-assistant/configuration.yaml` under
`input_number:`. **Git is the source of truth.** The `initial:` values reset the UI
sliders on every Home Assistant restart. Make a permanent rate change in the file,
not in the dashboard.

### Finished periods

The `*_monthly` sensors are month-to-date and reset on the 1st. Do not compare them
against a bill. Home Assistant's `utility_meter` keeps the previous cycle in a
`last_period` attribute, and template sensors expose it:

| Sensor | What it holds |
|---|---|
| `sensor.<group>_cost_last_month` | Last calendar month's finished total |
| `sensor.<group>_total_energy_last_month` | Last month's kWh |
| `sensor.<group>_cost_yesterday` | Yesterday's finished cost |
| `sensor.<prefix>_cost_last_month` | Per-device, last month |
| `sensor.<prefix>_energy_last_month` | Per-device, last month |

These values stop changing when the cycle closes. Today-so-far is a partial total
and yesterday is a complete one. A smaller partial-day total does not prove a
saving. Missing previous-period data shows as unavailable.

## Add a plug

This procedure adds one plug to Home Assistant, the cost pipeline, and the
dashboards. It restarts Home Assistant once, through the normal GitOps rollout.

### Before you start

Choose a short entity prefix, for example `hp_sff`. The prefix is permanent. If you
rename it later, every statistic recorded under the old prefix is orphaned and the
new prefix starts at zero.

Choose a device display name that does not contain `Power`, `Energy`, `Cost`,
`Voltage`, `Current` or `Share`. [How Grafana names a plug](#how-grafana-names-a-plug)
explains why.

### Steps

1. Adopt the plug in the Tapo app. Then add it to Home Assistant through the
   TP-Link integration.
2. Rename the device in HA to the display name. Then rename its entities so they
   share the prefix (`sensor.<prefix>_current_consumption`, `switch.<prefix>`, …).
3. In `my-apps/home-automation/home-assistant/configuration.yaml`, add
   `sensor.<prefix>_*` to `prometheus.filter.include_entity_globs`.
4. In the same file, add these entities for the plug:
    - its energy integration and its cost integration
    - four energy `utility_meter`s and four cost `utility_meter`s
    - a `*_cost_rate` template
    - `*_cost_last_month` and `*_energy_last_month` templates
    - a `*_power_share` template
5. Add the plug to the `Total Power` template of its group and of `combined`.
6. Add `friendly_name` entries in `customize.yaml`, in the form `<Device> <Metric ...>`.
7. If the device must stay on, add its switch to the lockout automation. See
   [The power-off lockout](#the-power-off-lockout).
8. Add the plug to `lovelace-homelab-power.yaml`.
9. Add the plug to the entity regex of the per-plug queries in both Grafana
   dashboards under `monitoring/metrics/prometheus-stack/dashboards/`. Those are
   plain `.json` files that `configMapGenerator` assembles into ConfigMaps. Edit the
   `.json`, never a rendered manifest.
10. Open a PR and wait for the merge and the rollout.
11. Add `sensor.<prefix>_energy` as an Individual device on the HA Energy dashboard.

!!! warning "The `name:` slug must equal the entity prefix"
    Home Assistant derives the entity ID from `name:`, so `name: "HP SFF Energy"`
    produces `sensor.hp_sff_energy`. If the slug differs from the prefix, every
    template and dashboard reference reads nothing. There is no error, only empty
    panels.

### How the change reaches the pod

The config files reach the pod through hashed ConfigMaps and an initContainer that
copies the files onto the PVC. A merged PR changes the ConfigMap references of the
pod, so Argo CD performs a `Recreate` rollout. This briefly interrupts Home
Assistant.

Do not copy config into the live PVC. Do not restart the Deployment by hand to
publish a change.

### Verify

```bash
# the new sensors exist and are numeric
kubectl exec -n home-assistant deploy/home-assistant -c home-assistant -- \
  sh -c 'wget -q -O- http://127.0.0.1:8123/api/prometheus | grep <prefix>_energy_daily'
```

Expected result: the command prints the daily energy metric for the prefix. Newly
created integrations and utility meters start at zero, and totals fill in as data
accumulates. An empty panel on the first day is expected.

### Roll back

Revert dashboard and config changes through a PR.

## The power-off lockout

The `Homelab plug power-off lockout` automation turns a homelab plug back on when
someone switches it off, and it raises a persistent notification. It covers the five
homelab plugs. It excludes the office plugs on purpose, because those machines are
meant to be powered down.

A hidden switch in `customize.yaml` is cosmetic only. The automation is the real
enforcement. **To power-cycle a plug on purpose, disable the automation first.**

The automation triggers on switch entity IDs (`switch.threadripper`,
`switch.hp_sff`, …). A typo there fails silently. The automation loads without an
error and never fires. Check a change against **Developer Tools → States** before
you trust it.

## How Grafana names a plug

The dashboards have no device list. Every query selects the entity IDs for its
group. It derives the display name from the `friendly_name` label of the metric by
removing the trailing metric words (`Power`, `Energy`, `Cost`, `Voltage`, `Current`,
`Share`).

For this reason `customize.yaml` sets every friendly name to `<Device> <Metric ...>`,
and a device display name must not contain one of those words.

## House-level data from Consumers Energy

The plugs see only the metered machines. The whole-house number comes from the
utility, Consumers Energy (CE).

A daily CronJob in `my-apps/home-automation/consumers-energy-sync/` drives a headless
Chromium through the CE portal. It downloads the *Share data → CSV* export, which has
one row per day for the trailing 30 days, with CE's own cost. It then pushes the data
into Home Assistant. The source and image are at `github.com/mitchross/consumers-energy-sync`.

| What the sync writes | Where it shows |
|---|---|
| `consumers_energy:grid_kwh`, `consumers_energy:grid_cost` (long-term statistics) | HA Energy dashboard grid source with cost; `statistics-graph` cards |
| `sensor.consumers_energy_kwh_yesterday`, `_kwh_7d`, `_kwh_month`, `_kwh_last_month` and the `_cost_*` twins | Homelab Power dashboard, Grafana via the Prometheus exporter |
| `sensor.homelab_share_of_house`, `sensor.combined_share_of_house` | Homelab kWh yesterday as a share of the house |
| `sensor.consumers_energy_effective_rate` | CE cost / kWh yesterday, next to the modelled rate |
| `sensor.*_last_ce_day` | Share and CE rate for the last matched day. Updates when `binary_sensor.power_bill_data_current` turns on, and holds between syncs |

CE data is one day late, so every house comparison is yesterday against yesterday.

### Cost adders

The CE portal export prices only energy plus Distribution. The sync CronJob adds the
other per-kWh charges and tax through `CE_COST_ADDER_PER_KWH` and
`CE_SALES_TAX_PCT`. Update them when a bill changes a rider. Imported cost excludes
fixed fees.

### Sensor values after a Home Assistant restart

The importer sets nine live sensors through the REST API, including
`sensor.consumers_energy_last_reading`. Those states normally disappear on an HA
restart, though recorder history and statistics persist.

The local `consumers_energy_restore` integration restores the last recorded values
after HA starts. Its source is in `scripts/consumers-energy-restore/`, and the config
copier installs it under `/config/custom_components/consumers_energy_restore`.

The integration works under these conditions:

- It reads the SQLite recorder in a worker thread and keeps the original reading date.
- It requires all nine recorded states.
- It skips recovery if a newer import has already populated any of them.
- Missing or invalid history leaves the comparisons unavailable until the next
  successful daily import at 13:17.
- Derived rates and shares recompute from the restored inputs.

This integration assumes the local SQLite recorder. Review it if the recorder moves
to another database backend.

### Run the sync elsewhere

The same image runs anywhere with the same env vars (`CE_PORTAL_USERNAME`,
`CE_PORTAL_PASSWORD`, `HASS_URL`, `HASS_TOKEN`):

```bash
# local checkout: node --env-file=.env index.mjs [--download-only|--import-only|--dry-run]
docker run --rm --user 1001:1001 --env-file .env -v ce-data:/data \
  ghcr.io/mitchross/consumers-energy-sync:v0.1.7
```

`/data` holds the Playwright cookie jar, which is a credential, and the CSVs. Keep
it private. The first run logs in with the password, and later runs reuse the cookie
jar. A failed run leaves a full-page screenshot in `/data`.

### Import older data

Each import bases its running total on what HA already holds just before the export
window. Overlapping trailing windows therefore stay consistent. An import of data
older than what HA has breaks the running total. Clear both statistics first
(`recorder.clear_statistics`), then import oldest-first.

### Release a new image

Tag the sync repo (`git tag v0.x.y && git push --tags`). The workflow publishes to
GHCR. Then change the tag and digest in `cronjob.yaml`. The base image version must
equal the `playwright` version in `package.json`.

## Home Assistant dashboard views

### Daily spend

**Daily spend** shows group and per-plug dollars and kWh beside yesterday's
completed totals. Previous-day values come from the `last_period` of each daily
utility meter, checked against its local `last_reset` date. Segmented bars show how
the tracked loads contribute to cost. The Devices view does the same for watts. The
graph cards fill their sections on desktop and collapse on phones.

### Bill breakdown

**Bill breakdown** separates energy share from estimated cost share. Its
non-overlapping buckets are homelab, office, modeled cooling, and the remainder.
Gaming is already in office. The solar shed is never included.

The cost remainder also contains the difference between the configured marginal rate
and CE's reported cost. It is not a measured appliance load. Negative remainders stay
visible, so a model mismatch cannot pass as perfect attribution.

`power-insights.yaml` holds these derived sensors. House comparisons exist only when
`consumers_energy_last_reading` equals yesterday's local date and both utility
totals exist. A late report or missing recovery history makes comparisons
unavailable, not zero. Startup recovery keeps the report date, so an old report
cannot pass the freshness check.

### Rates & savings

**Rates & savings** converts a constant load into dollars per day and dollars per 30
days at the configured current rate. These are what-if calculations. They are not
bill forecasts or verified utility tariffs. Fixed monthly fees are excluded.

This view also holds the long-term charts. The bill and repriced series are the
`consumers_energy:bill_*` and `consumers_energy:recalc_*` statistics. Import them
with `scripts/import-history.mjs` in `consumers-energy-sync`. The import does not
rewrite recorded `*_cost` meters.

`consumers_energy:recalc_*` ends October 30, 2026. Live `*_cost` statistics continue
the trend. `consumers_energy:grid_*` updates with each daily sync. Bill series update
only when you import bills.

### Rate charts in Grafana

Grafana **Power & Cost** has a *Rates and GPU cost* row with the live rate, burn
rate, GPU draw, and the same load priced at each rate. Gaming PC and Cooling have
rate and burn-rate charts. These charts cover 15 days, because Prometheus retains
all metrics for 15 days. GPU values use board power, not wall power.

### Findings

The **Findings** view uses `sensor.power_spending_analysis`, a local integration
whose source is `scripts/power-analysis/`. It refreshes hourly after HA starts and
reads the SQLite recorder in an executor thread. It is excluded from recorder
history. The view is in `lovelace-power-findings.yaml`. The Overview stays the
landing page.

The analysis uses the preceding 14 local days and excludes today. A day counts only
when all of these exist:

- a common set of complete hourly readings across the seven plug-energy series, the
  homelab and office groups, detected gaming energy, and cooling hours
- the previous hourly boundary
- matching CE daily energy and cost records

Missing hours, nonfinite values, counter discontinuities, and impossible gaming or
runtime values exclude the day. Local-day length accounts for daylight saving
transitions. The analysis shows recorded coverage. It cannot prove that every
physical sensor was accurate or responsive through the day.

Device ranking shows average watts and 720-hour projections at the configured rate.
Neither is an idle-only measurement or a full-month bill.

Cooling correlation needs at least seven matched days and one hour of runtime
variation. The report shows a fit against house energy minus computer energy, for
investigation only. Its largest positive residual marks a day to review. It cannot
identify an appliance, and it does not change the assumed AC wattage.

Use the `power-analysis` agent skill (shared procedure:
`.claude/commands/power-analysis.md`) for repeatable analysis and safe accounting.
The CLI prints the same report read-only. Omit `--rate` to leave projections
unpriced when the live configured rate is unknown.

### Local AI power brief

The Overview includes hourly AI summaries for today so far, yesterday, month to
date, and recent completed days. `sensor.power_ai_summary` sends only allowlisted
power meters and the read-only completed-day analysis to `qwen3.8-27b` on vLLM
through authenticated LiteLLM.

These summaries are generated interpretations. The measured tiles and the
deterministic Findings stay the source of truth. The model gets no HA actions or
equipment controls.

The implementation is `scripts/power-analysis/summary.py` plus `sensor.py` in the
Home Assistant app. It applies these data rules:

- Daily meter values require a local `last_reset` of today. Yesterday comes from the
  `last_period` of that meter.
- Month meters must belong to the current month. Missing data stays null.
- The sensor withholds CE yesterday values unless the reading date matches
  yesterday. Month figures keep their separate reporting cutoff.

`litellm-externalsecret.yaml` projects the 1Password `litellm/master_key` into an
optional, read-only Secret volume. The integration reads the file again each hour,
so a late secret creation or rotation needs no HA restart.

| State | Cause |
|---|---|
| `ready` | The summary generated |
| `not_configured` | The credential is missing. Inspect the ExternalSecret status |
| `error` | A timeout, an HTTP failure, or invalid model output. The old text is cleared. Check HA and LiteLLM logs and backend health |

Requests time out after 60 seconds and retry at the next hourly poll. The dashboard
hides a summary from a different local date or one more than two hours old. Summary
text is excluded from recorder history.

To verify after a change, check that the ExternalSecret is Ready and that
`sensor.power_ai_summary` becomes `ready` with the `today`, `yesterday`, `month`,
`trends`, `as_of`, and `generated_at` attributes. An unavailable recorder report
affects only the trend evidence. Live meter summaries can still generate. Never
print the Secret.

The model's response format follows the
[vLLM chat-completion API](https://docs.vllm.ai/en/latest/api/vllm/entrypoints/openai/chat_completion/protocol/).
To roll back, use a revert PR and the ConfigMap-driven rollout. No meter data or
statistics need to change.

## Gaming sessions

`binary_sensor.gaming_pc_gaming` is on while the Gaming PC plug draws more than
`input_number.gaming_pc_active_threshold_w`. The threshold is 350 W. Idle is about
200 W, and gaming is 450–600 W. The sensor turns off after five quiet minutes. Three
template feeds integrate only while it is on:

| Sensor | Meaning |
|---|---|
| `sensor.gaming_pc_gaming_energy` / `_cost` (+ daily/weekly/monthly/yearly meters) | kWh and USD spent gaming |
| `sensor.gaming_pc_gaming_hours` (+ meters) | hours gamed, from integrating a 1/0 flag, so it does not depend on recorder retention |
| `sensor.gaming_pc_idle_cost_daily` / `_monthly` | the rest of the PC's cost: total minus gaming |

Grafana **Gaming PC** (`gaming-pc.json`) and the **Gaming** view of the Homelab Power
dashboard read these sensors. The threshold is a slider, so you can tune it without
a deploy. Make a permanent change in `configuration.yaml`.

## AC cooling (modeled)

The central AC has no plug meter, so its cost is **modeled**, not measured.
`binary_sensor.ac_cooling` is on while the Google Nest (`climate.hallway_hallway`)
reports `hvac_action: cooling`. Fan-only runs read `fan` and are not counted.

The runtime is priced at `input_number.ac_cooling_wattage` (2000 W, calibrated
November 2026) × the live time-of-use rate. This uses the same integration pipeline
as the gaming sessions.

| Sensor | What it holds |
|---|---|
| `sensor.ac_cooling_energy` / `_cost` / `_hours` (+ daily/weekly/monthly/yearly meters) | Modeled AC kWh, USD, and cooling hours |
| `sensor.ac_cooling_cost_yesterday` / `_cost_last_month`, `_hours_*`, `_energy_last_month` | Finished periods, from `last_period` |
| `sensor.ac_cost_per_cooling_hour` | Month-to-date USD per cooling hour |
| `sensor.ac_share_of_house_yesterday` | AC cost as a % of the CE-billed house cost yesterday |
| `sensor.ac_implied_watts_yesterday` | The calibration gauge: (CE house kWh − metered plugs − `input_number.ac_house_baseline_kwh`) ÷ cooling hours |

The **Cooling** view of the Homelab Power dashboard and the AC tile on its House view
show these. `sensor.ac_*` and `binary_sensor.ac_cooling` are in the Prometheus filter
globs, so Grafana can read them.

### Calibrate the AC wattage

1. Pick 2–3 hot days with no dryer, oven or EV use. Use long, sustained cooling days.
2. Compare `ac_implied_watts_yesterday` to `ac_cooling_wattage`.
3. Move the slider toward the median implied value.
4. Commit that value as `initial:` in `configuration.yaml`. Git is the source of
   truth, and the UI slider resets on HA restart.
5. At month end, check that `ac_cooling_cost_last_month` + `combined_*` + baseline
   is within ~10–15% of the CE bill.

The wattage is an estimate, ±20 % on a variable-speed unit. The 3 min `delay_off`
over-counts runtime on short cycles, so implied watts read low on those days.

The November 2026 calibration used 11 no-cooling days (Oct 23–Nov 2), which gave a
baseline of 19.6 kWh/day (±1.8). Nov 3–4 had 3.7 cooling hours and 6.7 kWh above
that baseline, about 1.8 kW. Two days give about ±0.7 kW of uncertainty. Repeat the
check on hot days next summer.

## Shed solar

```
panels → EPEVER XTRA3210N MPPT → 12.8 V LiFePO4 bank (2 × 100 Ah) → LOAD → Anker SOLIX → HP micro (Tapo Shed Lab)
                    │
                    └─ Modbus RTU over USB serial → rpi4 (192.168.10.174) → `epsolar` service
```

The rpi4 is the only host with the serial link. Its `epsolar` service
(github.com/mitchross/epsolar, private) polls the controller every 5 s, runs the
guarded LOAD automation, and serves two feeds:

| Feed | Consumer |
|---|---|
| `:8080/metrics` (`epever_*`, `epsolar_*`, `solar_buffer_*`) | cluster Prometheus, job `epever-solar` (`monitoring/metrics/prometheus-stack/values.yaml`) |
| `:8080/api/v1/status` (JSON) | Home Assistant `rest:` sensors `sensor.solar_*` / `binary_sensor.solar_*` (30 s) |

The supply side (MPPT yield, battery bank voltage, and state of charge) is in the
Grafana **Solar** dashboard (`shed-solar`, file `dashboards/home-energy/shed-solar.json`).
It shows the same data as HA's Solar view and keeps the epsolar controller internals
in a collapsed row. Home Assistant has the **Solar** view of the Homelab Power
dashboard. The kWh counters are the controller's own lifetime totals.

The shed is off-grid, so keep it **out of the HA Energy dashboard**. That dashboard
models one house where solar feeds "Home". If you add `solar_generated_total` as a
solar source or `shed_lab_energy` as a device, the dashboard inflates home
consumption and shows 100 % self-sufficiency. The Energy dashboard is grid-only.

If the Pi is down, every `solar_*` sensor goes unavailable and the Prometheus target
shows `up == 0`. Nothing on the grid side is affected.

## Recorder statistics

Home Assistant stores history and long-term statistics in a SQLite recorder database
on the config PVC. Two init containers repair that database before Home Assistant
starts, and one procedure resets it. Both init containers run while HA is stopped,
under the Deployment's `Recreate` strategy.

**Never run either script in apply mode inside the running HA container. Do not
delete the recorder database or zero the meters to fix a failed repair.**

### The September 24 gap repair

The recorder has a discontinuity. Hourly power statistics stop at
**2026-09-24 14:00 UTC** and resume at **23:00 UTC** with their cumulative `sum` near
zero, while the meter `state` values keep increasing. For example, homelab energy
goes from 247.005 to 252.296 kWh while its statistical sum drops from 104.892 to
0.309. Without the repair, the daily bars go negative and the monthly graph reads
low. The evidence proves the discontinuity. It does not show which maintenance
operation caused it.

The first retained homelab cost statistic is September 16. The September chart
therefore covers less time than the monthly meter tile, even after the repair. The
dashboard labels this partial history.

The `repair-power-statistics` initContainer runs `scripts/repair-power-statistics.py`.
It works this way:

- It considers only the explicit power-entity pattern and the two exact hourly
  boundary timestamps.
- The offset is `previous.sum + (next.state - previous.state) - next.sum`. Both
  timestamps are on the same local day, with no daily, weekly, monthly or yearly
  cycle boundary between them.
- It adds that offset to the later long-term and short-term sums. Meter states, CE
  imports, and unrelated statistics stay unchanged.
- Before it writes, it saves the affected row IDs, timestamps and original sums in
  `/config/statistics-repairs/power-2026-09-24.json`. Then it updates in one SQLite
  transaction.
- Unexpected boundary data aborts the initContainer. A fresh installation or an
  already repaired database is a no-op.

The repair recovers the day's total across the gap from the surviving cumulative
readings. It cannot show when in those missing hours the energy was used. The
September 27 read-only export had 130 repairable series.

Check the rollout and the init log:

```bash
kubectl -n home-assistant rollout status deployment/home-assistant
kubectl -n home-assistant logs deployment/home-assistant -c repair-power-statistics
```

Expected result: the first rollout prints a repair list and a saved journal. Later
starts print an empty repair list. Check the September 24 daily bars and the
monthly cost graph. CE comparison sensors may stay unavailable until
the next successful utility import.

If the repair fails, keep the journal and read the init log. A code revert does not
undo a committed statistics repair. To undo it:

1. Open a PR that removes the repair initContainer and stops HA (`replicas: 0`).
2. With HA stopped, mount the PVC in an approved maintenance workload and run the
   same repository script:

    ```bash
    python /opt/repo-scripts/repair-power-statistics.py --apply --undo
    ```

3. Check the result. Then restore `replicas: 1` through a PR.

The undo reverses the recorded offsets, including later rows that inherited the
corrected baseline. It restores the original graph discontinuity. The journal stays
on the backed-up config PVC for inspection.

### Retired completed-period statistics

33 `*_yesterday` and `*_last_month` template sensors have no `state_class`, because
they show completed-period snapshots, not accumulating meters. Old recorder
statistics metadata for them caused 33 **"no longer has a state class"** repair
warnings.

The `retire-period-statistics` init container removes that metadata. It runs after
the configuration copy and the gap repair. Its source is
`my-apps/home-automation/home-assistant/scripts/retire-period-statistics.py`. It
works this way:

- It checks that the exact 33 templates still lack a state class.
- It archives their statistics metadata plus their long-term and short-term
  statistics to `/config/statistics-repairs/retired-period-summaries-2026-09-29.json`,
  on the kopiur-backed config PVC.
- It removes only those retired series, in one SQLite transaction. The archive must
  be durable before any deletion can commit.
- A missing database or an already completed cleanup is a no-op.
- Unexpected configuration, source, or archive content stops the init container
  without deleting data.

Raw recorder states, active power, energy and cost meters, CE statistics, and
current template values are unchanged. The September 29 read-only export had 8,877
long-term and 76,791 short-term rows, and the archive was about 9 MB.

Before a rollout that runs this cleanup for the first time, check that the config
PVC has a recent successful backup. Then check the rollout:

```bash
kubectl -n home-assistant logs deployment/home-assistant -c retire-period-statistics
kubectl -n home-assistant rollout status deployment/home-assistant
```

Expected result: the first run reports 33 metadata entries and the archived row
counts. Later starts report zero. After HA's statistics validation runs, the 33
state-class warnings disappear. The Homelab Power dashboard still shows current and
completed-period values. You need no live SQL and no manual dismissal of repairs.

If the init container fails, read its error and keep the archive. Do not overwrite
the archive to force a run.

To roll back, note that a revert of the deployment change stops future cleanup but
does not restore the archived statistics. To restore them:

1. Open a separate PR that changes the command of this init container to
   `["python", "/opt/repo-scripts/retire-period-statistics.py", "--apply", "--restore"]`.
2. Wait for the next `Recreate` rollout. It restores the archive with HA stopped and
   assigns new row IDs where necessary. It is idempotent, and it refuses schema
   changes or conflicting existing statistics.
3. Check its success log. Then remove the retirement init container in Git.

The original warnings return unless you also change the sensor configuration on
purpose.

### Reset the history

Home Assistant keeps three kinds of state. A fresh start must clear all three, or
the old totals come back:

| State | Where | How to clear |
|---|---|---|
| Recorder history + long-term statistics | `/config/home-assistant_v2.db` (+ `-wal`, `-shm`) on the PVC | Delete the files with HA stopped; it creates a fresh DB on start |
| Running totals of every `integration` and `utility_meter` sensor | `/config/.storage/core.restore_state` | Delete the file with HA stopped. HA rewrites it on every clean shutdown, so a `kill -9` of the `homeassistant` process after deleting is what makes it stick |
| Grafana history | Prometheus, 15-day retention | Nothing to do; old series age out |

A renamed entity prefix has the same effect. The renamed prefix starts at zero and
the old one is orphaned.

## Hardware comparison: Threadripper and the spare DL360

This section holds the measurements for one open question: would the two RTX 3090s
cost less to run in the spare DL360 than in the Threadripper host? The arrangement
under test keeps both RTX 3090s and uses an external GPU PSU and PCIe risers with
the DL360. Earlier use showed that this fits physically.

The installed CPUs and DIMMs of the spare DL360 still need verification. Records
list two E5-2680 v4 CPUs and conflicting RAM totals (736 GB, 724.24 GiB OS-visible,
and approximately 768 GB physical). The NAS is a separate DL360 with one E5-2680 v4
and 384 GB. Do not use its power reading for the spare GPU server.

### Measured on September 27

A read-only trailing-24-hour Prometheus sample showed about 222.4 W at the
Threadripper outlet (1,437 samples across HA pod changes) and 48.4 W combined GPU
board power (5,760 samples per GPU). GPU utilization averaged about 0.3% per GPU.

The two clocks and measurement boundaries are close but different. The roughly 174 W
difference includes CPU, RAM, drives, other host work, fans, and PSU losses. It is
not a measured CPU-only idle figure, and it is not guaranteed removable overhead.
A separate eight-day sample averaged 246.6 W.

### What a matched comparison needs

The readings below support keeping the GPUs in Threadripper against the dual-CPU
DL360 configuration. A single-CPU DL360 arrangement needs its own measurement. A
low-power single-Xeon trial is a plausible candidate, not an established winner. A
matched comparison includes:

- the same two GPUs, power caps, model, context, concurrency, and completed work;
- all wall outlets including the external GPU supply;
- both idle energy and Wh per inference workload, with tokens/sec and latency;
- PCIe link width and speed under load, and one-CPU versus two-CPU memory and slot dependencies.

At $0.21328/kWh, saving 25/50/100 W continuously is $3.84/$7.68/$15.36 per 30 days.

More RAM helps when the workload needs it. The NAS has shown ARC read benefits,
while storage and network behavior still limit sustained and durable writes. See
[NAS measurements](../../nas-performance.md),
[HPE DL360 Gen9 platform features](https://support.hpe.com/hpesc/public/docDisplay?docId=c04442953&docLocale=en_US&page=GUID-A8ED5EBD-51AB-4EDC-AEAA-FA318CF1B483.html),
and [TrueNAS caching and write behavior](https://www.truenas.com/docs/references/zilandslog/).

### Owner-reported readings

The owner reported these readings. The raw meter exports were not recovered. The
readings span different configurations and measurement boundaries. Use them as
reference observations. Do not treat them as live entities, and do not backfill them
into recorder statistics.

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
Threadripper. At the configured $0.21328/kWh, that is **$12.13 per 30 days / $147.60
per 365-day year**. The reported NAS-inclusive totals (~452 versus ~371 W) give
about 81 W because their components were rounded. These savings are repriced
historical scenarios, not utility-bill promises.

Another June 18 account reported host-only 334 W for the DL360 and 135 W for
Threadripper, plus a separate GPU feed at ~60 W settled or 230–450 W active. Adding
those gives 394 versus 195 W settled, 564 versus 365 W at the lower GPU load, and
784 versus 585 W at the higher load. These are calculated alternatives for the same
GPUs. They are not synchronized whole-system tests. They are also not the same
observation as the 259/66/246 W averages.

The May allocation (205 W host, 125 W GPUs/supply, 110 W NAS/drives, 30 W network,
15 W fan) approximately reconciles the 484 W rack meter. Those allocations are not
individually measured component watts, and they do not show a universal 15% iLO
error. The external PSU's 1,000 W rating is capacity, not draw.

Threadripper is the active GPU host. Ignore any older summary that calls it retired
or says the GPUs returned to the DL360. Machines that old notes label "unmeasured
desktop/mini" have HA plug readings, and those readings take precedence. Keep the
old NAS CPU/RAM configuration separate from the E5-2680 v4 / 384 GB evidence.
