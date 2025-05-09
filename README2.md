talosctl apply-config --insecure --nodes 192.168.10.100 --file clusterconfig/proxmox-talos-cluster-talos-cluster-control-00.yaml
talosctl apply-config --insecure --nodes 192.168.10.101 --file clusterconfig/proxmox-talos-cluster-talos-cluster-control-01.yaml
talosctl apply-config --insecure --nodes 192.168.10.102 --file clusterconfig/proxmox-talos-cluster-talos-cluster-control-02.yaml
talosctl apply-config --insecure --nodes 192.168.10.200 --file clusterconfig/proxmox-talos-cluster-talos-cluster-gpu-worker-00.yaml
talosctl apply-config --insecure --nodes 192.168.10.201 --file clusterconfig/proxmox-talos-cluster-talos-cluster-worker-01.yaml
talosctl apply-config --insecure --nodes 192.168.10.203 --file clusterconfig/proxmox-talos-cluster-talos-cluster-worker-02.yaml
