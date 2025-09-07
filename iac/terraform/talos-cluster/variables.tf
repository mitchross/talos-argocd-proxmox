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
    { name = "talos-master-00", vmid = 2000, role = "controlplane", ip = "192.168.10.101", cores = 6, memory = 16000, disk_size = "48G", mac_address = "BC:24:21:A4:B2:97", tags = ["talos", "controlplane"] },
    { name = "talos-worker-01", vmid = 3001, role = "worker", ip = "192.168.10.211", cores = 8, memory = 18000, disk_size = "64G", additional_disk_size = "112G", mac_address = "BC:24:21:4C:99:A2", tags = ["talos", "worker"] },
    { name = "talos-worker-02", vmid = 3002, role = "worker", ip = "192.168.10.213", cores = 8, memory = 18000, disk_size = "64G", additional_disk_size = "112G", mac_address = "BC:24:21:AD:82:0D", tags = ["talos", "worker"] },
  ]
}

variable "talos_iso_file" {
  description = "Default Proxmox storage reference to the uploaded Talos ISO for regular nodes, e.g. local:iso/talos-1.10.6.iso"
  type        = string
}

variable "talos_gpu_iso_file" {
  description = "Proxmox storage reference to the uploaded Talos GPU-enabled ISO, e.g. local:iso/talos-1.10.6-gpu.iso"
  type        = string
  default     = null
}

variable "disk_storage" {
  description = "Primary datastore ID for the main VM disk (e.g. local, local-zfs, zfs1)"
  type        = string
}

variable "additional_disk_storage" {
  description = "Datastore ID for any additional data disks (if nodes specify additional_disk_size)."
  type        = string
  default     = "local"
}

variable "network_bridge" {
  description = "Proxmox bridge to attach VM NICs to (e.g. vmbr0)."
  type        = string
  default     = "vmbr0"
}