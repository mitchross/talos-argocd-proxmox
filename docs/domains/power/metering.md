# Power & Cost Metering

Every always-on box and both office workstations sit behind a TP-Link Tapo P115
smart plug. Home Assistant reads watts from each plug, integrates them into kWh,
prices that against the live time-of-use electricity rate, and exposes the
result to Grafana. This page is the map of what is metered, how it is grouped,
what it costs, and how to add a plug.

## What is metered

| Plug (HA device) | Entity prefix | Group | What it powers |
|---|---|---|---|
| Threadripper Host | `threadripper_*` | homelab | Threadripper X399 host (`192.168.10.14`): GPU worker + general worker VMs, 1x RTX 3090 |
| NAS Drive PSU | `nas_psu_*` | homelab | The drive-shelf PSU for the NAS |
| TrueNAS (DL360) | `truenas_*` | homelab | The TrueNAS/DL360 host itself (`192.168.10.133`) |
| HP SFF + Optiplex | `hp_sff_*` | homelab | **Two hosts on one outlet**: HP 8500 SFF (`.21`) and Dell Optiplex 8500 |
| HP Elite Mini G9 | `hp_elite_*` | homelab | HP Elite Mini 600 G9 (`.22`) |
| Gaming PC | `gaming_pc_*` | office | 7800X3D workstation with the second RTX 3090. **Not a cluster node** |
| MacBook + Monitor | `macbook_*` | office | Office desk |
| Shed Lab (solar) | `shed_lab_*` | none | HP micro in the shed (`.20`), solar-fed |

**Shed Lab** runs off the shed's own solar and battery bank, so it has watts and
kWh (with the daily/weekly/monthly/yearly meters) but no cost entities, and it is
not in any group or in the house-share numbers. Its supply side (MPPT yield,
battery bank voltage and state of charge) lives in the separate Grafana
**Solar MPPT Monitor** dashboard (`solar-mppt-monitor`).

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

These stop moving once the cycle closes. The dashboards' *This Month vs Last*
panel subtracts one from the other; expect it to read negative early in the
month, since a young month has not accrued yet.

## Where to look

| Surface | What it is |
|---|---|
| Grafana **Homelab Power & Cost** (`homelab-power-cost`) | The main view: homelab and office draw, cost today/month/year, hot-spot leaderboard, idle-floor analysis, and a "reading this dashboard" panel |
| Grafana **Tapo Power Monitor** (`tapo-power-monitor`) | Raw per-plug telemetry: watts, volts, amps, energy today |
| Home Assistant **Homelab Power** dashboard | Same numbers inside HA, plus the editable rate inputs |
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

The live sensors are set through the REST API, so they vanish on an HA restart
until the next 13:17 run. The statistics persist.

**Running it elsewhere.** The same image runs anywhere with the same env vars
(`CE_PORTAL_USERNAME`, `CE_PORTAL_PASSWORD`, `HASS_URL`, `HASS_TOKEN`):

```bash
# local checkout: node --env-file=.env index.mjs [--download-only|--import-only|--dry-run]
docker run --rm --user 1001:1001 --env-file .env -v ce-data:/data \
  ghcr.io/mitchross/consumers-energy-sync:v0.1.1
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

Changes reach the pod through the `config` ConfigMap and an initContainer that
copies files onto the PVC, so **Home Assistant must restart** to pick them up:

```bash
kubectl rollout restart deployment/home-assistant -n home-assistant
```

Verify afterwards:

```bash
# the new sensors exist and are numeric
kubectl exec -n home-assistant deploy/home-assistant -c home-assistant -- \
  sh -c 'wget -q -O- http://127.0.0.1:8123/api/prometheus | grep <prefix>_energy_daily'
```

Newly created integrations and utility meters start at zero. Totals only fill in
as data accumulates; an empty panel on day one is expected, not a bug.

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

Grafana: **Shed Solar** (`shed-solar.json`, the overview page), **Solar Buffer
Control** (the author's detailed dashboard, copied from the epsolar repo), and
the older **Solar MPPT Monitor**. Home Assistant: the **Solar** view of the
Homelab Power dashboard. kWh counters are the controller's own lifetime
totals; `sensor.solar_generated_total` is the Energy dashboard's solar source.

If the Pi is down every `solar_*` sensor goes unavailable and the Prometheus
target shows `up == 0`; nothing on the grid side is affected.
