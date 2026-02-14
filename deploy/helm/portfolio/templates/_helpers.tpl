{{- define "portfolio.appLabel" -}}
{{- default "portfolio" .Values.global.appLabel -}}
{{- end -}}

{{- define "portfolio.imageTag" -}}
{{- default "" .Values.global.imageTag -}}
{{- end -}}

{{- define "portfolio.imagePullPolicy" -}}
{{- default "" .Values.global.imagePullPolicy -}}
{{- end -}}
