<#
.SYNOPSIS
    One-time preparation of the Hyper-V host for the campus lab.

.DESCRIPTION
    Idempotent. Re-run safely after a failure or a reboot.
      1. Verifies the Windows edition can run Hyper-V and enables it.
      2. Creates C:\campus-lab\{images,vms,iso,packer-output}.
      3. Creates the external switch 'campus-ext' bound to the NIC that holds
         the default route (host networking drops for a few seconds).
      4. Creates a dedicated local automation account (Administrators +
         Hyper-V Administrators).
      5. Configures WinRM over HTTPS (5986) with a self-signed certificate and
         a firewall rule that only admits the automation host.

    Run on: the Hyper-V host (alien), elevated Windows PowerShell 5.1 or PowerShell 7.

.EXAMPLE
    .\scripts\bootstrap-hyperv-host.ps1 -AutomationHostIp 192.168.5.227
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [ValidatePattern('^\d{1,3}(\.\d{1,3}){3}$')] [string] $AutomationHostIp,
    [string] $SwitchName = 'campus-ext',
    [string] $AutomationUser = 'campus-automation',
    [string] $LabRoot = 'C:\campus-lab'
)

$ErrorActionPreference = 'Stop'

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script from an elevated PowerShell session.'
}

# --- 1. Hyper-V -------------------------------------------------------------
$edition = (Get-CimInstance Win32_OperatingSystem).Caption
Write-Output "Windows edition: $edition"
if ($edition -match 'Home') {
    throw 'Windows Home cannot run Hyper-V. Upgrade to Pro/Enterprise/Education first.'
}
$feature = Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V-All
if ($feature.State -ne 'Enabled') {
    Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V-All -All -NoRestart | Out-Null
    Write-Warning 'Hyper-V enabled. REBOOT NOW, then run this script again to finish.'
    return
}
Import-Module Hyper-V

# --- 2. Directories ------------------------------------------------------------
foreach ($dir in 'images', 'vms', 'iso', 'packer-output') {
    New-Item -ItemType Directory -Path (Join-Path $LabRoot $dir) -Force | Out-Null
}

# --- 3. External switch ---------------------------------------------------------
if (-not (Get-VMSwitch -Name $SwitchName -ErrorAction SilentlyContinue)) {
    $route = Get-NetRoute -DestinationPrefix '0.0.0.0/0' | Sort-Object RouteMetric | Select-Object -First 1
    $nic = Get-NetAdapter -InterfaceIndex $route.InterfaceIndex
    if ($nic.InterfaceDescription -match 'Hyper-V') { throw "Default route is already on a virtual adapter ($($nic.Name))." }
    Write-Warning "Binding '$SwitchName' to '$($nic.Name)' ($($nic.InterfaceDescription)). Network drops briefly."
    New-VMSwitch -Name $SwitchName -NetAdapterName $nic.Name -AllowManagementOS $true -Notes 'campus-security-platform' | Out-Null
}
Write-Output "Switch ready: $SwitchName"

# --- 4. Automation account ---------------------------------------------------------
if (-not (Get-LocalUser -Name $AutomationUser -ErrorAction SilentlyContinue)) {
    $password = Read-Host -AsSecureString "Password for local account '$AutomationUser' (store it as GitHub secret HYPERV_PASSWORD)"
    New-LocalUser -Name $AutomationUser -Password $password -PasswordNeverExpires `
        -Description 'campus-security-platform automation (Terraform/Ansible over WinRM)' | Out-Null
}
foreach ($group in 'Administrators', 'Hyper-V Administrators') {
    if (-not (Get-LocalGroupMember -Group $group -Member $AutomationUser -ErrorAction SilentlyContinue)) {
        Add-LocalGroupMember -Group $group -Member $AutomationUser
    }
}
# Remote NTLM logons by local (non-built-in) admins are UAC-filtered by default,
# which breaks Hyper-V cmdlets over WinRM. Lab trade-off; a domain account avoids it.
$policyKey = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System'
Set-ItemProperty -Path $policyKey -Name LocalAccountTokenFilterPolicy -Value 1 -Type DWord

# --- 5. WinRM over HTTPS ------------------------------------------------------------
Enable-PSRemoting -SkipNetworkProfileCheck -Force | Out-Null
Set-Item -Path WSMan:\localhost\MaxTimeoutms -Value 1800000
Set-Item -Path WSMan:\localhost\Shell\MaxMemoryPerShellMB -Value 1024
Set-Item -Path WSMan:\localhost\Service\Auth\Negotiate -Value $true
Set-Item -Path WSMan:\localhost\Service\AllowUnencrypted -Value $false

$httpsListener = Get-ChildItem WSMan:\localhost\Listener | Where-Object { $_.Keys -contains 'Transport=HTTPS' }
if (-not $httpsListener) {
    $ips = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '169.254.*' -and $_.IPAddress -ne '127.0.0.1' }).IPAddress
    $cert = New-SelfSignedCertificate -DnsName (@($env:COMPUTERNAME) + $ips) `
        -CertStoreLocation Cert:\LocalMachine\My -KeyExportPolicy NonExportable -NotAfter (Get-Date).AddYears(3)
    New-Item -Path WSMan:\localhost\Listener -Transport HTTPS -Address * -CertificateThumbPrint $cert.Thumbprint -Force | Out-Null
}

$ruleName = 'Campus-WinRM-HTTPS-AutomationHost'
Remove-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue
New-NetFirewallRule -Name $ruleName -DisplayName 'WinRM HTTPS from campus automation host' `
    -Direction Inbound -Protocol TCP -LocalPort 5986 -RemoteAddress $AutomationHostIp `
    -Action Allow -Profile Any | Out-Null
Restart-Service WinRM

Write-Output ''
Write-Output 'Hyper-V host ready.'
Write-Output "  Switch:      $SwitchName"
Write-Output "  Account:     $AutomationUser  (GitHub secrets HYPERV_USER / HYPERV_PASSWORD)"
Write-Output "  WinRM HTTPS: 5986, allowed from $AutomationHostIp only"
