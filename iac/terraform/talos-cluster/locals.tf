locals {
  # Original Master Node configuration
  vm_master_nodes_original = {
    "0" = {
      vm_id          = 400
      node_name      = "talos-master-00"
      clone_target   = "talos-v1.10.4-cloud-init-template"
      node_cpu_cores = "6"
      node_memory    = 16000
      node_ipconfig  = "ip=192.168.10.100/24,gw=192.168.10.1"
      node_disk      = "48G"
    },
    "1" = {
      vm_id          = 401
      node_name      = "talos-master-01"
      clone_target   = "talos-v1.10.4-cloud-init-template"
      node_cpu_cores = "6"
      node_memory    = 16000
      node_ipconfig  = "ip=192.168.10.101/24,gw=192.168.10.1"
      node_disk      = "48G"
    },
    "2" = {
      vm_id          = 402
      node_name      = "talos-master-02"
      clone_target   = "talos-v1.10.4-cloud-init-template"
      node_cpu_cores = "6"
      node_memory    = 16000
      node_ipconfig  = "ip=192.168.10.102/24,gw=192.168.10.1"
      node_disk      = "48G"
    }
  }

  # Original Worker Node configuration
  vm_worker_nodes_original = {
    "0" = {
      vm_id                     = 410
      node_name                 = "talos-gpu-worker-00"
      clone_target              = "talos-gpu-v1.10.4-cloud-init-template"
      node_cpu_cores            = "8"
      node_memory               = 65000
      node_ipconfig             = "ip=192.168.10.200/24,gw=192.168.10.1"
      node_disk                 = "64G"
      additional_node_disk_size = "712G"
      additional_node_disk_storage = "datapool"
    },
    "1" = {
      vm_id                     = 411
      node_name                 = "talos-worker-01"
      clone_target              = "talos-v1.10.4-cloud-init-template"
      node_cpu_cores            = "8"
      node_memory               = 18000
      node_ipconfig             = "ip=192.168.10.201/24,gw=192.168.10.1"
      node_disk                 = "64G"
      additional_node_disk_size = "712G"
      additional_node_disk_storage = "datapool"
    },
    "2" = {
      vm_id                     = 412
      node_name                 = "talos-worker-02"
      clone_target              = "talos-v1.10.4-cloud-init-template"
      node_cpu_cores            = "8"
      node_memory               = 18000
      node_ipconfig             = "ip=192.168.10.203/24,gw=192.168.10.1"
      node_disk                 = "64G"
      additional_node_disk_size = "712G"
      additional_node_disk_storage = "datapool"
    }
  }

  # Common defaults that were missing
  common_node_config = {
    disk_storage   = "local-lvm"
    disk_type      = "disk"
    onboot         = true
    sockets        = 1
    os_type        = "cloud-init"
    network_bridge = "vmbr0"
    network_model  = "virtio"
  }

  # MAC Addresses for existing VMs
  node_mac_addresses = {
    "talos-master-00"     = "BC:24:11:A4:B2:97"
    "talos-master-01"     = "BC:24:11:ED:73:BF"
    "talos-master-02"     = "BC:24:11:98:6B:13"
    "talos-gpu-worker-00" = "BC:24:11:77:86:5F"
    "talos-worker-01"     = "BC:24:11:4C:99:A2"
    "talos-worker-02"     = "BC:24:11:AD:82:0D"
  }

  # Transformed Master Nodes
  transformed_master_nodes = {
    for k, v in local.vm_master_nodes_original : v.node_name => merge(local.common_node_config, {
      vmid                    = v.vm_id
      name                    = v.node_name
      template                = v.clone_target
      cores                   = tonumber(v.node_cpu_cores)
      memory                  = v.node_memory
      ipconfig0               = v.node_ipconfig
      disk_size               = v.node_disk
      mac_address             = local.node_mac_addresses[v.node_name]
      additional_disk_size    = null
      additional_disk_storage = null
    })
  }

  # Transformed Worker Nodes
  transformed_worker_nodes = {
    for k, v in local.vm_worker_nodes_original : v.node_name => merge(local.common_node_config, {
      vmid                    = v.vm_id
      name                    = v.node_name
      template                = v.clone_target
      cores                   = tonumber(v.node_cpu_cores)
      memory                  = v.node_memory
      ipconfig0               = v.node_ipconfig
      disk_size               = v.node_disk
      mac_address             = local.node_mac_addresses[v.node_name]
      additional_disk_size    = v.additional_node_disk_size
      additional_disk_storage = v.additional_node_disk_storage
    })
  }

  all_nodes_transformed = merge(local.transformed_master_nodes, local.transformed_worker_nodes)
}
