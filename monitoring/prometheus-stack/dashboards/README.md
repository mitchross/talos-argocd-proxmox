# Grafana dashboards

Every Grafana dashboard in this cluster is a JSON file in this directory tree.
Nothing is imported by hand and nothing is downloaded from grafana.com at
startup.

## How it works

Each subdirectory is one Grafana folder. Its `kustomization.yaml` turns every
JSON file into a ConfigMap and stamps two things on it:

- the label `grafana_dashboard: "1"`, which the Grafana sidecar watches in all
  namespaces;
- the annotation `grafana_folder: "<Folder>"`, which the sidecar uses as the
  folder name (`sidecar.dashboards.folderAnnotation` +
  `provider.foldersFromFilesStructure` in `../values.yaml`).

| Directory | Grafana folder | What lives there |
|-----------|----------------|------------------|
| `start-here/` | Start Here | Cockpit (Grafana home page), Why Is This App Slow, Capacity |
| `cluster/` | Cluster | etcd, Argo CD, Longhorn, VPA, hardware report (+ kopiur from its chart) |
| `ai/` | AI | GPU, vLLM, AI gateway (LiteLLM), Pi auto-routing |
| `apps/` | Apps | PostHog, radar-ng, radar-ng mobile, Frigate |
| `logs/` | Logs | Logs Explorer, node crash logs |
| `home-energy/` | Home & Energy | Power & cost, solar, gaming PC, cooling, AirCube |

The Grafana home page is read from
`/tmp/dashboards/Start Here/performance-cockpit.json` (`grafana.ini` in
`../values.yaml`). Renaming the Start Here folder or that file breaks the home
page.

## Add or change a dashboard

1. Build it in Grafana, then **Export → Export as JSON** (leave "export for
   sharing externally" off).
2. Save it as `<folder>/<name>.json` and add a generator entry to that
   folder's `kustomization.yaml`:
   ```yaml
     - name: <name>-dashboard
       files:
         - <name>.json
   ```
3. Before committing, make sure the JSON:
   - uses fixed datasource UIDs `prometheus`, `loki` or `tempo`. Don't use
     `${DS_*}` variables or `__inputs`; an unresolved variable blanks every
     panel;
   - keeps a stable, readable `uid`. Links and bookmarks use `/d/<uid>`;
   - sets `"id": null` and `"editable": false`.

   Edits made in the Grafana UI are lost on the next sync.

A Helm chart that ships its own dashboard only needs the same label and
annotation. See `monitoring.dashboards` in
`infrastructure/controllers/kopiur-operator/values.yaml`.

## Query gotchas

JSON can't hold comments, so the traps a future editor will hit are listed here.

- **Capacity:** 7d/15d peaks read the `workload:*:pod_max` recording rules in
  `../capacity-rules.yaml`. Raw per-pod `*_over_time` queries time out on
  short-lived pod churn (versioned radar workers, backup jobs).
- **etcd:** filter on `job="kube-etcd"`. DB size is `etcd_mvcc_db_total_size_in_bytes`,
  not `etcd_debugging_*`. API server → etcd latency comes from `job="apiserver"`.
- **VPA:** join requests to VPA metrics through
  `namespace_workload_pod:kube_pod_owner:relabel` (workload → `target_name`),
  never on `container` alone.
- **Argo CD:** `namespace` on `argocd_*` is Argo CD's own namespace. The app's
  namespace is `dest_namespace`.
- **Longhorn:** `longhorn_volume_robustness` and `longhorn_volume_state` are
  one-hot gauges. Filter `state="x" == 1`, never on the numeric value.
- **kopiur:** scraped without `honorLabels`, so the CR namespace is in
  `exported_namespace`. `namespace` is always `kopiur-system`.
- **GPU:** DCGM's `pod`/`namespace` are the exporter itself. Use
  `exported_pod`/`exported_namespace`. There is no power-limit or XID metric,
  and memory temperature reads 0 on 3090s.
- **vLLM:** one engine (`engine="0"`) spans both cards. Speculative-decoding
  metrics don't exist while MTP is off.
- **AI gateway / Pi routing:** LiteLLM traffic is sparse and every pod restart
  starts new series. Use `increase([$__range])` for window totals, not
  `max_over_time`. `requested_model` is what the app asked for;
  `litellm_model_name` is the backend that answered.
- **PostHog:** the `django_http_responses_*` per-view series only appear after
  real UI/API traffic, so they're empty when PostHog is idle.
- **radar-ng:** don't `clamp_min(denominator, 1)` on low-traffic ratios; it
  pushes them toward 0.
- **radar-ng mobile:** Tempo has no metrics-generator, so TraceQL `rate()` and
  `quantile_over_time` fail. Use trace search.
- **Frigate:** `frigate_cpu_usage_percent` and `frigate_mem_usage_percent` carry
  a pid-keyed `type="Other"` duplicate per process. Filter `type!="Other"`.
- **Power & Cost:** a plug's display name comes from its entity id via
  `label_replace`. A new plug means updating that regex and the per-device
  name and colour overrides.
- **Gaming PC:** HA `input_number` helpers don't export, so the 350 W session
  threshold is a constant line. Update it if HA's default moves.
- **Cooling / Gaming PC:** some energy entities also have a frozen
  `homeassistant_sensor_unit_kwh` series from HA startup. Name
  `homeassistant_sensor_energy_kwh` explicitly in range functions.
- **Energy per-day bars:** `[1d] offset -4h` with a 1-day step lines the bars up
  with Eastern days. They are one hour off in winter.
- **Solar:** per-day bars read HA's `solar_*_today` counters with
  `max_over_time`. Never take `max - min` of `solar_*_total`: HA exports 0 on
  startup, so the whole lifetime total lands on one day.
- **Logs:** Loki labels are OTEL-style (`k8s_namespace_name`, `service_name`,
  `detected_level`), not Promtail's `namespace`/`job`.
