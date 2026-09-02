{{/*
Common labels applied to all ClearFlow resources.
*/}}
{{- define "clearflow.labels" -}}
app.kubernetes.io/part-of: clearflow
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end }}

{{/*
Selector labels for a specific service component.
Usage: include "clearflow.selectorLabels" (dict "service" "gateway")
*/}}
{{- define "clearflow.selectorLabels" -}}
app.kubernetes.io/name: clearflow-{{ .service }}
app.kubernetes.io/instance: {{ $.Release.Name }}
{{- end }}

{{/*
Full image reference for a service.
Usage: include "clearflow.image" (dict "root" . "service" "gateway")
*/}}
{{- define "clearflow.image" -}}
{{ .root.Values.global.image.registry }}/{{ .service }}:{{ .root.Values.global.image.tag }}
{{- end }}

{{/*
Standard environment variables injected into every service pod.
*/}}
{{- define "clearflow.commonEnv" -}}
- name: SPRING_PROFILES_ACTIVE
  value: {{ .Values.global.env.SPRING_PROFILES_ACTIVE | default "kubernetes" }}
- name: JAVA_TOOL_OPTIONS
  value: {{ .Values.global.javaOpts | quote }}
- name: KAFKA_BROKERS
  value: "{{ .Release.Name }}-kafka:9092"
- name: ARTEMIS_HOST
  value: "{{ .Release.Name }}-activemq"
- name: REDIS_HOST
  value: "{{ .Release.Name }}-redis-master"
- name: REDIS_PASSWORD
  valueFrom:
    secretKeyRef:
      name: clearflow-secrets
      key: redis-password
{{- end }}
