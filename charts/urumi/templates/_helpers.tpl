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

{{/* WordPress ke env vars. WordPress pod aur wp-init Job dono use karte hain. Usage: include "urumi.wpEnv" . */}}
{{- define "urumi.wpEnv" -}}
- name: WORDPRESS_DB_HOST
  value: "{{ .Release.Name }}-mariadb:3306"
- name: WORDPRESS_DB_NAME
  value: {{ .Values.mariadb.database | quote }}
- name: WORDPRESS_DB_USER
  value: {{ .Values.mariadb.user | quote }}
- name: WORDPRESS_DB_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ .Release.Name }}-store-db
      key: mariadb-password
- name: WORDPRESS_CONFIG_EXTRA
  value: |
    define('WP_HOME', '{{ .Values.store.scheme }}://{{ .Values.store.host }}');
    define('WP_SITEURL', '{{ .Values.store.scheme }}://{{ .Values.store.host }}');
    if (isset($_SERVER['HTTP_X_FORWARDED_PROTO']) && $_SERVER['HTTP_X_FORWARDED_PROTO'] === 'https') { $_SERVER['HTTPS'] = 'on'; }
{{- end -}}