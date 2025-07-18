locals {
  # Base configuration values
  cluster_name     = "talos-cluster"
  cluster_endpoint = "https://192.168.10.199:6443"
  cni_name         = "cilium"
  talos_version    = "v1.10.5"
  gateway          = "192.168.10.1"
  network_bridge   = "vmbr0"
  disk_storage     = "local-lvm"
  additional_disk_storage = "datapool"
  
  template_vmids = {
    "controlplane" = 9706
    "worker"       = 9706
    "worker-gpu"   = 9705
  }

  # Talos Machine Configuration Templates
  talosconfig_templates = {
    controlplane = <<-EOT
      version: v1alpha1
      machine:
        install:
          image: ghcr.io/siderolabs/installer:${local.talos_version}
          bootloader: true
          extensions:
            - name: siderolabs/amd-ucode
            - name: siderolabs/gasket-driver
            - name: siderolabs/i915
            - name: siderolabs/iscsi-tools
            - name: siderolabs/qemu-guest-agent
            - name: siderolabs/util-linux-tools
      cluster:
        network:
          cni:
            name: ${local.cni_name}
        apiServer:
          certSANs:
            - ${local.cluster_endpoint}
        extraManifests: []
    EOT
    worker = <<-EOT
      version: v1alpha1
      machine:
        install:
          image: ghcr.io/siderolabs/installer:${local.talos_version}
          bootloader: true
          extensions:
            - name: siderolabs/amd-ucode
            - name: siderolabs/gasket-driver
            - name: siderolabs/i915
            - name: siderolabs/iscsi-tools
            - name: siderolabs/qemu-guest-agent
            - name: siderolabs/util-linux-tools
      cluster:
        network:
          cni:
            name: ${local.cni_name}
    EOT
    "worker-gpu" = <<-EOT
      version: v1alpha1
      machine:
        files:
          - op: create
            content: |
              [plugins]
                [plugins."io.containerd.cri.v1.runtime"]
                  [plugins."io.containerd.cri.v1.runtime".containerd]
                    default_runtime_name = "nvidia"
            path: /etc/cri/conf.d/20-customization.part
        install:
          image: ghcr.io/siderolabs/installer:${local.talos_version}
          bootloader: true
          extensions:
            - name: siderolabs/amd-ucode
            - name: siderolabs/gasket-driver
            - name: siderolabs/i915
            - name: siderolabs/iscsi-tools
            - name: siderolabs/qemu-guest-agent
            - name: siderolabs/util-linux-tools
            - name: siderolabs/nonfree-kmod-nvidia-production
            - name: siderolabs/nvidia-container-toolkit-production
      cluster:
        network:
          cni:
            name: ${local.cni_name}
    EOT
  }

  # Node definitions
  nodes = [
    { name = "talos-master-00", vmid = 400, role = "controlplane", ip = "192.168.10.100", cores = 6, memory = 16000, disk_size = "48G", mac_address = "BC:24:11:A4:B2:97" },
    { name = "talos-master-01", vmid = 401, role = "controlplane", ip = "192.168.10.101", cores = 6, memory = 16000, disk_size = "48G", mac_address = "BC:24:11:ED:73:BF" },
    { name = "talos-master-02", vmid = 402, role = "controlplane", ip = "192.168.10.102", cores = 6, memory = 16000, disk_size = "48G", mac_address = "BC:24:11:98:6B:13" },
    { name = "talos-gpu-worker-00", vmid = 410, role = "worker-gpu", ip = "192.168.10.200", cores = 8, memory = 65000, disk_size = "64G", additional_disk_size = "712G", mac_address = "BC:24:11:77:86:5F" },
    { name = "talos-worker-01", vmid = 411, role = "worker", ip = "192.168.10.201", cores = 8, memory = 18000, disk_size = "64G", additional_disk_size = "712G", mac_address = "BC:24:11:4C:99:A2" },
    { name = "talos-worker-02", vmid = 412, role = "worker", ip = "192.168.10.203", cores = 8, memory = 18000, disk_size = "64G", additional_disk_size = "712G", mac_address = "BC:24:11:AD:82:0D" },
  ]

  all_nodes_transformed = {
    for node in var.nodes : node.name => {
      vmid                    = node.vmid
      name                    = node.name
      template_vmid           = local.template_vmids[node.role]
      cores                   = node.cores
      memory                  = node.memory
      ip                      = node.ip
      gateway                 = local.gateway
      disk_size               = node.disk_size
      disk_storage            = local.disk_storage
      disk_type               = "scsi"
      onboot                  = true
      sockets                 = 1
      os_type                 = "cloud-init"
      network_bridge          = local.network_bridge
      network_model           = "virtio"
      mac_address             = node.mac_address
      tags                    = lookup(node, "tags", [node.role])
      additional_disk_size    = lookup(node, "additional_disk_size", null)
      additional_disk_storage = lookup(node, "additional_disk_size", null) != null ? local.additional_disk_storage : null
      role                    = node.role
      user_data               = local.talosconfig_templates[node.role]
    }
  }
}
