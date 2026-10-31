terraform {
  required_version = ">= 1.6.0"

  required_providers {
    hyperv = {
      source  = "taliesins/hyperv"
      version = "~> 1.2.1"
    }
  }

  # Partial configuration: the pipeline passes a per-site state path, e.g.
  #   terraform init -backend-config="path=/var/lib/campus-platform/tfstate/hou-01.tfstate"
  # One state per site keeps the blast radius of any apply to a single site.
  backend "local" {}
}

# Credentials come from HYPERV_USER / HYPERV_PASSWORD in the runner environment,
# never from tfvars. WinRM over HTTPS (5986) to the Hyper-V host.
provider "hyperv" {
  host     = var.hyperv_host
  port     = 5986
  https    = true
  insecure = var.hyperv_insecure
  use_ntlm = true
  timeout  = "120s"
}
