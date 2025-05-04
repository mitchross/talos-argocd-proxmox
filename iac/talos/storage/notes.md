kubectl label ns openebs \
  pod-security.kubernetes.io/audit=privileged \
  pod-security.kubernetes.io/enforce=privileged \
  pod-security.kubernetes.io/warn=privileged


https://www.talos.dev/v1.8/kubernetes-guides/configuration/replicated-local-storage-with-openebs/