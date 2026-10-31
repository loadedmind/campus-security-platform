# A site (campus or core) is a YAML file. This stack turns that file into VMs.
# Onboarding a campus = add sites/<name>.yaml, merge, approve the apply.

locals {
  site  = yamldecode(file(var.site_file))
  hosts = { for h in local.site.hosts : h.name => h }

  # Guard rail: the file name and the site name must agree, so the state path
  # (derived from the file name in the pipeline) can never point at another site.
  file_stem = trimsuffix(basename(var.site_file), ".yaml")
}

resource "terraform_data" "site_guard" {
  input = local.site.name

  lifecycle {
    precondition {
      condition     = local.site.name == local.file_stem
      error_message = "Site name '${local.site.name}' does not match file name '${local.file_stem}.yaml'."
    }
  }
}

module "vm" {
  source   = "../../modules/hyperv-vm"
  for_each = local.hosts

  name            = each.key
  parent_vhd_path = "${var.image_root}\\${local.site.image}.vhdx"
  vm_root         = "${var.vm_root}\\${local.site.name}"
  switch_name     = var.switch_name
  cpu             = try(each.value.cpu, 2)
  memory_gb       = try(each.value.memory_gb, 2)
  notes           = "site=${local.site.name};role=${each.value.role};ring=${local.site.patch_ring};managed-by=campus-security-platform"

  depends_on = [terraform_data.site_guard]
}
