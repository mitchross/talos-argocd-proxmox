variable "proxmox_api_url" {
  description = "The URL for the Proxmox API."
  type        = string
}

variable "proxmox_node" {
  description = "The Proxmox node to deploy to."
  type        = string
}

variable "proxmox_api_token" {
  description = "The Proxmox API token."
  type        = string
  sensitive   = true
}

variable "proxmox_pool" {
  description = "The Proxmox resource pool to deploy to."
  type        = string
}

variable "proxmox_ssh_user" {
  description = "The SSH user for the Proxmox node."
  type        = string
  default     = "root"
}

variable "proxmox_ssh_password" {
  description = "The SSH password for the Proxmox node."
  type        = string
  sensitive   = true
}

variable "nodes" {
  description = "A list of virtual machines to create."
  type = list(object({
    name                 = string
    vmid                 = number
    role                 = string
    ip                   = string
    cores                = number
    memory               = number
    disk_size            = string
    mac_address          = string
    tags                 = optional(list(string))
    additional_disk_size = optional(string)
    additional_disk_storage = optional(string, "datapool")
  }))
  default = [
    { name = "talos-master-00", vmid = 200, role = "controlplane", ip = "192.168.10.100", cores = 6, memory = 16000, disk_size = "48G", mac_address = "BC:24:11:A4:B2:97", tags = ["talos", "controlplane"] },
    { name = "talos-master-01", vmid = 201, role = "controlplane", ip = "192.168.10.101", cores = 6, memory = 16000, disk_size = "48G", mac_address = "BC:24:11:ED:73:BF", tags = ["talos", "controlplane"] },
    { name = "talos-master-02", vmid = 202, role = "controlplane", ip = "192.168.10.102", cores = 6, memory = 16000, disk_size = "48G", mac_address = "BC:24:11:98:6B:13", tags = ["talos", "controlplane"] },
    { name = "talos-worker-01", vmid = 301, role = "worker", ip = "192.168.10.201", cores = 8, memory = 18000, disk_size = "64G", additional_disk_size = "712G", mac_address = "BC:24:11:4C:99:A2", tags = ["talos", "worker"] },
    { name = "talos-worker-02", vmid = 303, role = "worker", ip = "192.168.10.203", cores = 8, memory = 18000, disk_size = "64G", additional_disk_size = "712G", mac_address = "BC:24:11:AD:82:0D", tags = ["talos", "worker"] },
    { name = "talos-gpu-worker-00", vmid = 300, role = "worker-gpu", ip = "192.168.10.200", cores = 8, memory = 65000, disk_size = "64G", additional_disk_size = "712G", mac_address = "BC:24:11:77:86:5F", tags = ["talos", "worker", "gpu"] }
  ]
}