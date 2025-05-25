variable "proxmox_api_url" {
  type        = string
  description = "The API URL for Proxmox VE (e.g., https://proxmox-server:8006/api2/json)."
}

variable "proxmox_api_token_id" {
  type        = string
  description = "The Proxmox API token ID (e.g., user@pam!tokenid)."
}

variable "proxmox_api_token_secret" {
  type        = string
  sensitive   = true
  description = "The Proxmox API token secret."
}

variable "proxmox_node" {
  type        = string
  description = "The target Proxmox VE node where VMs will be created (e.g., 'pve')."
}

variable "nodes" {
  type = map(object({
    vmid                    = number
    name                    = string
    template                = string
    cores                   = number
    memory                  = number # in MB
    ipconfig0               = string # e.g., "ip=192.168.1.100/24,gw=192.168.1.1"
    disk_size               = string # e.g., "32G"
    disk_storage            = string # Proxmox storage ID for the primary disk
    disk_type               = string
    onboot                  = bool
    sockets                 = number
    os_type                 = string
    network_bridge          = string # Proxmox network bridge, e.g., "vmbr0"
    network_model           = string
    mac_address             = string # MAC address for the network interface
    additional_disk_size    = string # e.g., "512G"
    additional_disk_storage = string # Proxmox storage ID for the additional disk
  }))
  description = "A map of virtual machine configurations. Each key is a unique identifier for the node, and the value is an object with its settings."
  default     = {}
}