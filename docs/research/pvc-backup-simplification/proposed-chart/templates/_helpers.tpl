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

{{- define "vb.resName" -}}
{{- printf "%s-backup" (include "vb.pvc" .) -}}
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
