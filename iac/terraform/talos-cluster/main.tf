# Dynamically create VMs.
module "compute_master" {
  source                   = "./compute-master"
  proxmox_api_url          = var.proxmox_api_url
  proxmox_api_token_id     = var.proxmox_api_token_id
  proxmox_api_token_secret = var.proxmox_api_token_secret
  proxmox_node             = var.proxmox_node
  nodes                    = local.vm_master_nodes
}
module "compute_worker" {
  source                   = "./compute-worker"
  proxmox_api_url          = var.proxmox_api_url
  proxmox_api_token_id     = var.proxmox_api_token_id
  proxmox_api_token_secret = var.proxmox_api_token_secret
  proxmox_node             = var.proxmox_node
  nodes                    = local.vm_worker_nodes
}

output "master_mac_addrs" {
  value = module.compute_master.mac_addrs
}

output "worker_mac_addrs" {
  value = module.compute_worker.mac_addrs
}