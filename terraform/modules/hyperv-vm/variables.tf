variable "name" {
  description = "VM name and Windows computer name (NetBIOS limit: 15 chars)."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9-]{3,15}$", var.name))
    error_message = "name must be 3-15 chars of lowercase letters, digits and hyphens."
  }
}

variable "parent_vhd_path" {
  description = "Absolute path on the Hyper-V host to the read-only golden image VHDX."
  type        = string
}

variable "vm_root" {
  description = "Absolute directory on the Hyper-V host that holds this VM's files."
  type        = string
}

variable "switch_name" {
  description = "Existing Hyper-V virtual switch to attach the VM to."
  type        = string
}

variable "cpu" {
  description = "Virtual processors."
  type        = number
  default     = 2
}

variable "memory_gb" {
  description = "Static memory in GiB."
  type        = number
  default     = 2
}

variable "notes" {
  description = "Free text stored on the VM (site, role, managed-by)."
  type        = string
  default     = ""
}

variable "wait_for_ips_timeout" {
  description = "Seconds to wait for the guest to report an IP address."
  type        = number
  default     = 900
}
