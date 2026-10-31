variable "site_file" {
  description = "Path to the site definition YAML (sites/<name>.yaml)."
  type        = string
}

variable "hyperv_host" {
  description = "Hyper-V host reachable over WinRM HTTPS."
  type        = string
}

variable "hyperv_insecure" {
  description = "Skip TLS verification of the Hyper-V host's WinRM certificate. Lab only (self-signed cert)."
  type        = bool
  default     = true
}

variable "image_root" {
  description = "Directory on the Hyper-V host holding golden images (<image>.vhdx)."
  type        = string
  default     = "C:\\campus-lab\\images"
}

variable "vm_root" {
  description = "Directory on the Hyper-V host under which per-site VM folders are created."
  type        = string
  default     = "C:\\campus-lab\\vms"
}

variable "switch_name" {
  description = "Pre-existing external virtual switch bridged to the LAN."
  type        = string
  default     = "campus-ext"
}
