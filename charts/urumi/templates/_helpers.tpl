{{/* Common labels. Usage: include "urumi.labels" (dict "root" . "name" "mariadb") */}}
{{- define "urumi.labels" -}}
app.kubernetes.io/name: {{ .name }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/part-of: urumi
app.kubernetes.io/managed-by: {{ .root.Release.Service }}
{{- end -}}

{{/* Selector labels (immutable rakhne hain) */}}
{{- define "urumi.selector" -}}
app.kubernetes.io/name: {{ .name }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
{{- end -}}