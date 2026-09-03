# Power & Cost Metering

Every always-on box in the homelab sits behind a TP-Link Tapo P115 smart plug.
Home Assistant reads watts from each plug, integrates them into kWh, prices that
against the live time-of-use electricity rate, and exposes the result to
Grafana. This page is the map of what is metered, what it costs, and how to add
a plug.

## What is metered

| Plug (HA device) | Entity prefix | What it powers |
|---|---|---|
| threadripper-gpus | `gpu_psu_*` | Threadripper X399 host (`192.168.10.14`) — GPU worker + general worker VMs, 1x RTX 3090 |
| Nas psu | `nas_psu_*` | The drive-shelf PSU for the NAS |
| Truenas Server | `truenas_server_*` | The TrueNAS/DL360 host itself (`192.168.10.133`) |
| HP SFF | `hp_sff_*` | **Two hosts on one outlet**: HP SFF (`.21`) and Dell Optiplex (`.16`) |
| Shed Lab | `shed_lab_*` | HP micro in the shed (`.20`), solar-fed, behind the Wi-Fi bridge |
| Gaming PC | `gaming_pc_*` | 7800X3D workstation with the second RTX 3090 — **not a cluster node** |
| *(none)* | `hp_elite_estimated_*` | HP Elite Mini 600 G9 (`.22`) — **no plug; a tunable assumed figure**, see below |

Two plugs exist but are deliberately outside the homelab accounting: the garage
fridge (which confusingly still carries the `basement_homelab_*` entity prefix
from an earlier name) and the household plugs. Both are filtered out in
`configuration.yaml`.

> **Entity prefixes are frozen.** `gpu_psu` is the Threadripper host and
> `basement_homelab` is a fridge. Renaming an entity prefix orphans every
> statistic recorded under it, so the real hardware is named in `friendly_name`
> (`customize.yaml`) instead.

### The two figures that are not measurements

**HP Elite is estimated, not metered.** It has no smart plug, so its draw is a
flat number from `input_number.hp_elite_estimated_watts` (default **30 W**).
That default is a working figure, not a reading: ServeTheHome measured the same
Elite Mini 600 G9 chassis at 4–5.5 W idle and 60–65 W under load, and this host
runs a Talos worker continuously rather than idling. Adjust the input to taste —
or better, fit a plug and delete the estimate. Its entities are deliberately
prefixed `hp_elite_estimated_*` so a future plug named "HP Elite" lands on a
clean `hp_elite_*` prefix without colliding.

**The shed costs nothing.** It runs off its own solar and battery bank, so
`shed_lab_cost_rate` is pinned to zero: the shed contributes watts and kWh to
the totals but never dollars. Everything priced in this system is based on
`sensor.homelab_grid_power` — total draw minus the solar-fed plugs — not on
`homelab_total_power`. What the shed's own supply is doing (MPPT yield, battery
bank voltage and state of charge) lives in the separate Grafana **Solar MPPT
Monitor** dashboard (`solar-mppt-monitor`).

## How cost is computed

```
device watts ──integration──▶ kWh ──utility_meter──▶ daily / weekly / monthly / yearly kWh
      │
      └──× current all-in rate──▶ USD/h ──integration──▶ USD ──utility_meter──▶ daily / … / yearly USD
                                   ▲
                          pinned to 0 for solar-fed devices
```

The all-in marginal rate is `(energy + delivery riders) × (1 + sales tax)`. The
energy component steps between three windows:

| Window | When | All-in rate |
|---|---|---|
| Summer on-peak | June–August, weekdays 14:00–19:00 | ~$0.289 |
| Summer off-peak | June–August, all other hours | ~$0.238 |
| Non-summer | September–May | ~$0.216 |

Rates live in `my-apps/home/home-assistant/configuration.yaml` under
`input_number:`. **Git is the source of truth** — the `initial:` values reset the
UI sliders on every Home Assistant restart, so a permanent rate change goes in
the file, not the dashboard.

Cost integrates a live USD/hour rate rather than applying a flat tariff after
the fact, so a workload that runs only during on-peak hours is priced at on-peak
rates.

### Last month, and other finished totals

The `*_monthly` sensors are month-to-date and reset on the 1st, so they are the
wrong thing to compare against a bill. Home Assistant's `utility_meter` keeps the
previous cycle in a `last_period` attribute, and template sensors surface it:

| Sensor | What it holds |
|---|---|
| `sensor.homelab_cost_last_month` | Last calendar month's finished total |
| `sensor.homelab_total_energy_last_month` | Last month's kWh |
| `sensor.homelab_cost_yesterday` | Yesterday's finished cost |
| `sensor.<prefix>_cost_last_month` | Per-device, last month |
| `sensor.<prefix>_energy_last_month` | Per-device, last month |

These stop moving once the cycle closes, which is what makes them comparable
month to month. The dashboards' *This Month vs Last* panel subtracts one from the
other — expect it to read negative early in the month, since a young month has
simply not accrued yet.

## Where to look

| Surface | What it is |
|---|---|
| Grafana **Homelab Power & Cost** (`homelab-power-cost`) | The main view: live and billable draw, cost today/month/year, hot-spot leaderboard, idle-floor analysis, and a "reading this dashboard" panel |
| Grafana **Tapo Power Monitor** (`tapo-power-monitor`) | Raw per-plug telemetry — watts, volts, amps, energy today |
| Grafana **Solar MPPT Monitor** (`solar-mppt-monitor`) | The shed's supply side: Epever MPPT yield and Daly BMS battery bank |
| Home Assistant **Homelab Power** dashboard | Same numbers inside HA, plus the editable rate inputs |
| HA **Energy** dashboard | Configured in the UI; add each `sensor.<prefix>_energy` as an Individual device |

### Reading the numbers

**The idle floor is the bill.** Peak draw is brief; the 24-hour minimum runs
8,760 hours a year. When the *Baseline Cost / Year* panel accounts for most of
*Cost This Year*, workload tuning will not move the number — only removing or
consolidating hardware does.

**Run-rate panels are what-ifs, not forecasts.** *Run-Rate / Year* and *Cost /
Year If Left At This Draw* annualise the current instant to answer "what does
leaving this on cost me?". Use *Cost This Month* for an actual bill estimate.

**The HP SFF plug cannot be attributed.** It feeds two hosts. Split the outlet
before concluding which of the two to retire.

**Total draw and billable draw are different numbers.** *Total Power Now*
includes the solar shed; *Billable Draw* does not, and every cost figure follows
the billable line.

## Safety: the power-off lockout

The `Homelab plug power-off lockout` automation turns any always-on plug back on
if it is switched off, and raises a persistent notification. It covers the
Threadripper, NAS PSU, TrueNAS, HP SFF and Shed plugs. The Gaming PC plug is
deliberately excluded — that machine is meant to be powered down.

Hiding a switch via `customize.yaml` is cosmetic only; the automation is the
real enforcement. **To intentionally power-cycle a plug, disable the automation
first.**

> The automation triggers on switch entity IDs (`switch.gpu_psu`,
> `switch.hp_sff`, …). A typo there fails silently — the automation loads fine
> and simply never fires. Verify a change against
> **Developer Tools → States** before trusting it.

## Adding a plug

1. Adopt the plug in the Tapo app, then add it to Home Assistant through the
   TP-Link integration. Note the entity prefix Home Assistant derives from the
   device name — that prefix is permanent.
2. In `my-apps/home/home-assistant/configuration.yaml`, add the prefix to
   `prometheus.filter.include_entity_globs`, then add its energy integration,
   cost integration, four energy `utility_meter`s, four cost `utility_meter`s,
   a `*_cost_rate` template, a `*_power_share` template, and a
   `*_energy_share_today` template. Add it to the `Homelab Total Power` and
   `Homelab Total Energy Today` sums.
3. Add `friendly_name` entries in `customize.yaml`, and the switch to the
   lockout automation if the device must stay on.
4. Add it to `lovelace-homelab-power.yaml` and to the device list in both
   Grafana dashboards under `monitoring/prometheus-stack/dashboards/`. Those are
   plain `.json` files assembled into ConfigMaps by `configMapGenerator`, not
   JSON embedded in YAML — edit the `.json`, never a rendered manifest.

> **The `name:` slug must equal the entity prefix.** Home Assistant derives the
> entity ID from `name:`, so `name: "HP SFF Energy"` produces
> `sensor.hp_sff_energy`. If the slug drifts, every template and dashboard
> reference silently reads nothing — no error, just empty panels.

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
as data accumulates — an empty panel on day one is expected, not a bug.

> **Every integration sensor needs `max_sub_interval`.** A Riemann-sum
> integration only steps when its source *changes state*. A source that holds a
> constant value emits no state changes, so its energy and cost integrate to
> zero forever while its live wattage looks perfectly healthy. That bites any
> device whose draw is a fixed number — the HP Elite estimate, and the shed's
> pinned-zero cost rate. `max_sub_interval: "00:05:00"` forces a time-based step
> every five minutes regardless.
