# One Windows Server VM on Hyper-V, booted from a differencing disk whose parent
# is the versioned golden image. Changing the image version replaces the disk and
# the VM (immutable hosts); configuration is applied afterwards by Ansible + DSC.

locals {
  vhd_path = "${var.vm_root}\\${var.name}-os.vhdx"
}

# Anchors replacement on the golden image path. Used instead of relying on the
# provider's own ForceNew behaviour for parent_path, which is not documented.
resource "terraform_data" "image" {
  input = var.parent_vhd_path
}

resource "hyperv_vhd" "os" {
  path        = local.vhd_path
  parent_path = var.parent_vhd_path

  lifecycle {
    replace_triggered_by = [terraform_data.image]
  }
}

resource "hyperv_machine_instance" "this" {
  name                 = var.name
  generation           = 2
  processor_count      = var.cpu
  static_memory        = true
  memory_startup_bytes = var.memory_gb * 1024 * 1024 * 1024
  notes                = var.notes
  path                 = var.vm_root

  automatic_start_action = "StartIfRunning"
  automatic_stop_action  = "ShutDown"
  checkpoint_type        = "Production" # patch pipeline takes a checkpoint before each ring
  state                  = "Running"

  wait_for_ips_timeout       = var.wait_for_ips_timeout
  wait_for_ips_poll_period   = 10
  wait_for_state_timeout     = 300
  wait_for_state_poll_period = 5

  vm_firmware {
    enable_secure_boot   = "On"
    secure_boot_template = "MicrosoftWindows"

    boot_order {
      boot_type           = "HardDiskDrive"
      controller_number   = 0
      controller_location = 0
    }
  }

  integration_services = {
    "Guest Service Interface" = true
    "Heartbeat"               = true
    "Key-Value Pair Exchange" = true # required for the host to report guest IPs
    "Shutdown"                = true
    "Time Synchronization"    = true
    "VSS"                     = true
  }

  network_adaptors {
    name                = "lan"
    switch_name         = var.switch_name
    dynamic_mac_address = true
    wait_for_ips        = true
  }

  hard_disk_drives {
    controller_type     = "Scsi"
    controller_number   = 0
    controller_location = 0
    path                = hyperv_vhd.os.path
  }

  lifecycle {
    replace_triggered_by = [hyperv_vhd.os]
  }
}
