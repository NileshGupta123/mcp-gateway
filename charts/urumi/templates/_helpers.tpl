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

{{/* NetworkPolicy egress rule: public internet (80/443), private ranges aur cloud metadata ke bina.
     Usage: {{- include "urumi.publicEgress" . | nindent 4 }} */}}
{{- define "urumi.publicEgress" -}}
- to:
    - ipBlock:
        cidr: 0.0.0.0/0
        except:
          - 10.0.0.0/8
          - 172.16.0.0/12
          - 192.168.0.0/16
          - 169.254.0.0/16
          - 100.64.0.0/10
          - 127.0.0.0/8
  ports:
    - protocol: TCP
      port: 443
    - protocol: TCP
      port: 80
{{- end -}}