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
  image = "https://factory.talos.dev/image/13c36cf02fe4f488b14f055c5aff8526ec961a1150223aed1d4de259bd45be04/v1.9.5/nocloud-amd64.raw.xz"
}