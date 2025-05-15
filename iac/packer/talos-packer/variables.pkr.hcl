variable "proxmox_api_token_id" {
  type = string
}

variable "proxmox_api_token_secret" {
  type = string
}

variable "proxmox_api_url" {
  type = string
}

variable "proxmox_node" {
  type = string
}

variable "proxmox_storage" {
  type = string
}

variable "cpu_type" {
  type    = string
  default = "kvm64"
}

variable "cores" {
  type    = string
  default = "2"
}

variable "cloudinit_storage_pool" {
  type    = string
  default = "local-lvm"
}

variable "talos_version" {
  type    = string
  default = "v1.6.7"
}

variable "base_iso_file" {
  type    = string
}

locals {
  image = "https://factory.talos.dev/image/3113b4ce6a82b241c60e4f17ec74f0345690cdf94a08a06284337b8432f2b93b/v1.10.1/metal-amd64.raw.zst"
}