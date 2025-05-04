kubectl label ns openebs \
  pod-security.kubernetes.io/audit=privileged \
  pod-security.kubernetes.io/enforce=privileged \
  pod-security.kubernetes.io/warn=privileged


https://www.talos.dev/v1.8/kubernetes-guides/configuration/replicated-local-storage-with-openebs/


talosctl patch mc --nodes 192.168.10.100 --patch @patch-extensions-longhorn.yaml
talosctl patch mc --nodes 192.168.10.101 --patch @patch-extensions-longhorn.yaml
talosctl patch mc --nodes 192.168.10.102 --patch @patch-extensions-longhorn.yaml
talosctl patch mc --nodes 192.168.10.200 --patch @patch-extensions-longhorn.yaml
talosctl patch mc --nodes 192.168.10.201 --patch @patch-extensions-longhorn.yaml
talosctl patch mc --nodes 192.168.10.203 --patch @patch-extensions-longhorn.yaml


talosctl patch mc --nodes 192.168.10.100 --patch @patch-mounts-longhorn.yaml
talosctl patch mc --nodes 192.168.10.101 --patch @patch-mounts-longhorn.yaml
talosctl patch mc --nodes 192.168.10.102 --patch @patch-mounts-longhorn.yaml
talosctl patch mc --nodes 192.168.10.200 --patch @patch-mounts-longhorn.yaml
talosctl patch mc --nodes 192.168.10.201 --patch @patch-mounts-longhorn.yaml
talosctl patch mc --nodes 192.168.10.203 --patch @patch-mounts-longhorn.yaml