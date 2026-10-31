# Consumed by scripts/render_inventory.py to build the Ansible inventory and the
# Prometheus file_sd targets. Shape is part of the contract; change both together.
output "site" {
  value = {
    name       = local.site.name
    kind       = local.site.kind
    patch_ring = local.site.patch_ring
    image      = local.site.image

    hosts = {
      for name, h in local.hosts : name => {
        role         = h.role
        ipv4_address = module.vm[name].ipv4_address
      }
    }
  }
}
