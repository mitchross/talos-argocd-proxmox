# Analyze Home Assistant power

Use `docs/domains/power/metering.md` for entity ownership and accounting.
The maintained analyzer is
`my-apps/home/home-assistant/scripts/power-analysis/analysis.py`; HA installs it
at `/config/custom_components/power_analysis/analysis.py`.

## Obtain evidence

Prefer the live `sensor.power_spending_analysis` report (check `generated_at`
and availability) or run the installed analyzer read-only:

```sh
kubectl -n home-assistant exec deploy/home-assistant -c home-assistant -- \
  python /config/custom_components/power_analysis/analysis.py
```

The CLI defaults to the local recorder, America/Detroit, and a 14-day window.
Pass `--rate <current configured USD/kWh>` only after reading the live rate;
without it, energy is analyzed but monetary projections remain unpriced.
For an exported SQLite copy, use `--database <path>` and, for reproducibility,
`--today YYYY-MM-DD`. Do not copy the multi-GB production DB just to obtain this
small report. The query itself never changes recorder data.

The report requires complete hourly cumulative values, the preceding boundary,
and matched utility dates. It excludes current/partial days and counter resets,
and handles 23/25-hour local days. Include sample count, date window, exclusions,
and price basis when explaining results. At least seven matched days and one
hour of cooling-runtime spread are required for correlation/fitting. A day
excluded here can still appear in HA's raw historical charts.

## Interpret correctly

- Homelab + office are disjoint plug groups. Gaming is part of office. Cooling
  is an estimate from thermostat runtime; solar shed is outside grid accounting.
- Compare yesterday with yesterday. Label today as partial and rate-based
  30-day numbers as scenarios. Utility bill averages and modeled marginal
  pricing have different meanings; don't promise a tariff correction.
- The 350 W gaming threshold can miss games. Non-session energy is not proven
  idle energy. Describe sleep opportunities conditionally.
- Correlation is an association. The cooling residual fit also contains other
  appliances and thermostat lag; never automatically set AC wattage from it.
- The unusual-day residual is deviation from the fitted relationship after
  metered computers, not evidence naming an appliance or proving a fault.
- Read Mink hardware notes when comparing machines. The 2950X host has BOTH
  RTX 3090s; the spare DL360 GPU arrangement uses an external PSU and risers.
  Preserve the GPUs and workload in comparisons and include every power feed.
- The historical spare-host inventory lists 2× E5-2680 v4; RAM records
  conflict (736 GB, 724 GiB OS-visible, and ~768 GB claims), so do not infer
  a verified DIMM count. Reverify installed CPUs/DIMMs today. The NAS is a separate one-Xeon DL360
  with 384 GB RAM. Its outlet excludes the separately metered drive PSU.
- Owner-supplied historical June plug readings: old DL360 259 W plus GPU
  supply 66 W, versus Threadripper with both GPUs 246 W (~79 W lower).
  Different periods/workloads; evidence for the old migration, not a benchmark
  of a new single-Xeon setup. The May 484 W whole-rack figure includes NAS,
  network gear and fan; its component split was an allocation, not measurements.
  Do not treat the claimed 15% iLO scaling as a universal calibration. Older
  "Threadripper retired"/"DL360 current" summaries are superseded by live evidence.
- Sample GPU board telemetry and wall power over matching windows. Aggregate
  Prometheus sum/count across pod labels after restarts; do not average unequal
  segment averages. Board power excludes PSU losses and isn't wall power.
  Quantify coverage, and don't interpret sampled utilization as request duty cycle.
- Compare matched-workload wall Wh, tokens/sec, and service performance before
  endorsing a host swap. A one-CPU configuration can change memory/PCIe access.
- NAS ARC helps reads and has measured value. Cache occupancy does not prove
  required capacity; RAM doesn't remove sustained/durable-write bottlenecks.
  Use `docs/nas-performance.md` for the measured evidence, not a generic RAM rule.

Report the strongest findings and their practical limits. Save durable verified
findings in Mink. If the user requests dashboard changes, follow the repository's
branch/PR workflow; an analysis request alone does not authorize deployment.
