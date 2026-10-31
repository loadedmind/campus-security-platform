# Golden image: Windows Server 2025 Standard (Server Core), patched, with
# Chocolatey and the pinned DSC modules baked in, then sysprepped.
#
# Runs ON the Hyper-V host (hyperv-iso cannot build remotely). Invoke through
# scripts/build-golden-image.ps1, which versions and publishes the VHDX.

packer {
  required_plugins {
    hyperv = {
      source  = "github.com/hashicorp/hyperv"
      version = ">= 1.1.5"
    }
  }
}

variable "iso_path" {
  type        = string
  description = "Local path to the Windows Server 2025 evaluation ISO."
}

variable "iso_sha256" {
  type        = string
  description = "SHA-256 of the ISO (Get-FileHash -Algorithm SHA256)."
}

variable "image_index" {
  type        = number
  default     = 1
  description = "install.wim index for Standard (Server Core). Verify with: Get-WindowsImage -ImagePath <mount>\\sources\\install.wim"
}

variable "admin_password" {
  type      = string
  sensitive = true

  # Injected verbatim into XML answer files, so XML metacharacters are refused.
  validation {
    condition     = length(var.admin_password) >= 14 && !can(regex("[<>&\"']", var.admin_password))
    error_message = "admin_password must be >= 14 chars and must not contain < > & \" or '."
  }
}

variable "switch_name" {
  type    = string
  default = "campus-ext"
}

variable "output_directory" {
  type    = string
  default = "C:\\campus-lab\\packer-output"
}

locals {
  unattend_vars = {
    admin_password = var.admin_password
    image_index    = var.image_index
  }
}

source "hyperv-iso" "ws2025_core" {
  iso_url      = var.iso_path
  iso_checksum = "sha256:${var.iso_sha256}"

  vm_name              = "packer-ws2025-core"
  generation           = 2
  enable_secure_boot   = true
  secure_boot_template = "MicrosoftWindows"
  cpus                 = 4
  memory               = 4096
  disk_size            = 61440
  switch_name          = var.switch_name
  output_directory     = var.output_directory
  headless             = true

  # autounattend.xml must be on removable media at first boot; Gen2 VMs have no
  # floppy, so it ships on a secondary CD (needs oscdimg on the build host).
  cd_label = "UNATTEND"

  cd_content = {
    "autounattend.xml" = templatefile("${path.root}/files/autounattend.xml.pkrtpl", local.unattend_vars)
    "enable-winrm.ps1" = file("${path.root}/scripts/enable-winrm-build.ps1")
  }

  boot_wait    = "2s"
  boot_command = ["<spacebar><wait1><spacebar><wait1><spacebar>"]

  communicator   = "winrm"
  winrm_username = "Administrator"
  winrm_password = var.admin_password
  winrm_timeout  = "2h"

  shutdown_command = "C:\\Windows\\System32\\Sysprep\\sysprep.exe /generalize /oobe /shutdown /quiet /unattend:C:\\campus\\unattend-oobe.xml"
  shutdown_timeout = "30m"
}

build {
  sources = ["source.hyperv-iso.ws2025_core"]

  provisioner "powershell" {
    inline = ["New-Item -ItemType Directory -Path C:\\campus -Force | Out-Null"]
  }

  provisioner "powershell" {
    script = "${path.root}/scripts/install-chocolatey.ps1"
  }

  provisioner "powershell" {
    script = "${path.root}/scripts/install-dsc-modules.ps1"
  }

  # Windows Update COM API refuses to download from a remote (WinRM) session;
  # elevated_* runs the script as a scheduled task under a local token instead.
  provisioner "powershell" {
    script            = "${path.root}/scripts/install-updates.ps1"
    elevated_user     = "Administrator"
    elevated_password = var.admin_password
  }

  provisioner "windows-restart" {
    restart_timeout = "45m"
  }

  provisioner "powershell" {
    script            = "${path.root}/scripts/install-updates.ps1"
    elevated_user     = "Administrator"
    elevated_password = var.admin_password
  }

  provisioner "windows-restart" {
    restart_timeout = "45m"
  }

  provisioner "file" {
    source      = "${path.root}/scripts/firstboot.ps1"
    destination = "C:\\campus\\firstboot.ps1"
  }

  provisioner "powershell" {
    inline = [
      "$ErrorActionPreference = 'Stop'",
      "Set-Content -Path C:\\campus\\unattend-oobe.xml -Encoding UTF8 -Value @'\n${templatefile("${path.root}/files/unattend-oobe.xml.pkrtpl", local.unattend_vars)}\n'@",
      "Set-Content -Path C:\\campus\\image-build.txt -Value (Get-Date -Format o)",
    ]
  }
}
