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
  default = "v1.10.4"
}

variable "talos_image_schematic_id" {
  type    = string
  description = "The schematic ID for the Talos factory image."
}

variable "vm_id" {
  type        = string
  description = "The Proxmox VM ID for the template."
}

variable "template_name_prefix" {
  type        = string
  description = "The prefix for the Proxmox template name."
  default     = "talos"
}

variable "base_iso_file" {
  type    = string
}

locals {
  # Construct the image URL dynamically
  talos_image_url = "https://factory.talos.dev/image/${var.talos_image_schematic_id}/${var.talos_version}/metal-amd64.raw.zst"
}