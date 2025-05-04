packer {
  required_plugins {
    proxmox = {
      version = ">= 1.2.2"
      source  = "github.com/hashicorp/proxmox"
    }
  }
}

source "proxmox-iso" "talos" {
  proxmox_url              = var.proxmox_api_url
  username                 = var.proxmox_api_token_id
  token                    = var.proxmox_api_token_secret
  node                     = var.proxmox_node
  insecure_skip_tls_verify = true

  boot_iso {
    iso_file     = var.base_iso_file
    iso_checksum = "none" # Assuming no checksum needed, adjust if necessary
    unmount     = true
  }
  scsi_controller = "virtio-scsi-single"
  network_adapters {
    bridge = "vmbr0"
    model  = "virtio"
  }
  disks {
    type              = "scsi"
    storage_pool      = var.proxmox_storage
    format            = "raw"
    disk_size         = "4000M"
    io_thread         = true
    cache_mode        = "writethrough"
  }

  memory               = 2048
  vm_id                = "9701"
  cores                = var.cores
  cpu_type             = var.cpu_type
  sockets              = "1"
  ssh_username         = "root"
  ssh_password         = "packer"
  ssh_timeout          = "15m"

  cloud_init              = true
  cloud_init_storage_pool = var.cloudinit_storage_pool

  template_name        = "talos-${var.talos_version}-cloud-init-template"
  template_description = "Talos ${var.talos_version} cloud-init, built on ${formatdate("YYYY-MM-DD hh:mm:ss ZZZ", timestamp())}"

  boot_wait = "25s"
  boot_command = [
    "<enter><wait1m>",
    "passwd<enter><wait>packer<enter><wait>packer<enter>"
  ]
}

build {
  sources = ["source.proxmox-iso.talos"]

  provisioner "shell" {
    inline = [
      "curl -s -L ${local.image} -o /tmp/talos.raw.zst",
      "zstd -d -c /tmp/talos.raw.zst | dd of=/dev/sda && sync",
    ]
  }
}