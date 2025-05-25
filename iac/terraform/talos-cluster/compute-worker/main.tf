# Create a new VM from a clone

resource "proxmox_vm_qemu" "proxmox-talos" {

    # Dynamic provisioning of multiple nodes
    count = length(var.nodes)

    # VM General Settings
    target_node = var.proxmox_node
    name        = var.nodes[count.index].node_name
    vmid        = var.nodes[count.index].vm_id

    # VM Advanced General Settings
    onboot = true

    # VM OS Settings
    clone = var.nodes[count.index].clone_target # Name of the template to clone

    # VM System Settings
    agent = 1 # QEMU Guest Agent. Set to 1 if installed/needed.

    # VM CPU Settings
    cores   = var.nodes[count.index].node_cpu_cores
    sockets = 1
    # type = "host" # Uncomment if you need host CPU passthrough

    # VM Memory Settings
    memory = var.nodes[count.index].node_memory # In MB

    # VM Network Settings
    network {
        id     = 0
        model  = "virtio"
        bridge = "vmbr0" # Ensure this bridge exists on your target_node
    }

    # VM Disk Settings
    scsihw = "virtio-scsi-single" # SCSI controller type

    # Primary Disk (scsi0)
    disk {
        slot    = 0
        type    = "scsi"      # Bus type of the disk. Must match template's primary disk bus.
        storage = "local-lvm" # Storage pool for the primary disk.
        size    = var.nodes[count.index].node_disk # Size of the primary disk
        iothread = true
        backup   = false
    }

    # Additional Disk (scsi1) for Longhorn
    disk {
        slot    = 1
        type    = "scsi"      # Bus type for the additional disk
        storage = var.nodes[count.index].additional_node_disk_storage # Storage for additional disk
        size    = var.nodes[count.index].additional_node_disk_size    # Size for additional disk
        iothread = true
        backup   = false
    }

    # VM Cloud-Init Settings
    os_type = "cloud-init" # Necessary for Cloud-Init
    # cloudinit_cdrom_storage = "local-lvm" # Optional
    ipconfig0 = var.nodes[count.index].node_ipconfig

}

output "mac_addrs" {
    description = "MAC addresses of the created VMs' first network interface."
    value       = [for vm in proxmox_vm_qemu.proxmox-talos : lower(vm.network[0].macaddr)]
}