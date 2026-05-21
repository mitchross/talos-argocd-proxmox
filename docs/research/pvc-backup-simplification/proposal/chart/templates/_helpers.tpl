{{- define "vb.pvc" -}}
{{- required "values.pvc is required" .Values.pvc -}}
{{- end -}}

{{- define "vb.namespace" -}}
{{- required "values.namespace is required" .Values.namespace -}}
{{- end -}}

{{/* Kopia repo + per-PVC secret name. MUST remain volsync-<pvc> for
     continuity with pvc-plumber-created lineages. */}}
{{- define "vb.repoName" -}}
{{- printf "%s%s" .Values.repositoryPrefix (include "vb.pvc" .) -}}
{{- end -}}

{{/* Object names — match mirceanton/home-ops components/volsync convention:
       RS metadata.name = <pvc>       (his replication-source.yaml)
       RD metadata.name = <pvc>-dst   (his replication-destination.yaml)
     Distinct from pvc-plumber's <pvc>-backup so chart-rendered RS does
     not collide with operator-rendered RS during per-PVC cutover.
     Kopia repo identity volsync-<pvc> stays unchanged (see vb.repoName). */}}
{{- define "vb.rsName" -}}
{{- include "vb.pvc" . -}}
{{- end -}}

{{- define "vb.rdName" -}}
{{- printf "%s-dst" (include "vb.pvc" .) -}}
{{- end -}}

{{/* Deterministic spread: adler32(ns/pvc) % 60 -> minute. */}}
{{- define "vb.schedule" -}}
{{- if .Values.schedule -}}
{{- .Values.schedule -}}
{{- else -}}
{{- $m := mod (atoi (adler32sum (printf "%s/%s" (include "vb.namespace" .) (include "vb.pvc" .)))) 60 -}}
{{- if eq .Values.frequency "hourly" -}}
{{- printf "%d * * * *" $m -}}
{{- else -}}
{{- printf "%d 2 * * *" $m -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "vb.commonLabels" -}}
app.kubernetes.io/managed-by: volsync-backup-chart
volsync.backup/pvc: {{ include "vb.pvc" . }}
{{- end -}}
