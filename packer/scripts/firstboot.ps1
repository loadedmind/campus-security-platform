# Runs once on every VM's first logon after sysprep.
#  - Replaces the build-time HTTP listener with WinRM over HTTPS only.
#  - Removes the answer file that contained the local admin password.
#  - Disables auto-logon.
$ErrorActionPreference = 'Stop'
Start-Transcript -Path C:\campus\firstboot.log -Append

Get-NetConnectionProfile | Where-Object NetworkCategory -eq 'Public' |
    Set-NetConnectionProfile -NetworkCategory Private

Enable-PSRemoting -SkipNetworkProfileCheck -Force

# Self-signed certificate for the lab. Production: enrol from the internal CA
# and validate it on the Ansible side (see docs/adr/0002).
$fqdn = [System.Net.Dns]::GetHostEntry('localhost').HostName
$cert = New-SelfSignedCertificate -DnsName $env:COMPUTERNAME, $fqdn `
    -CertStoreLocation Cert:\LocalMachine\My -KeyExportPolicy NonExportable `
    -NotAfter (Get-Date).AddYears(3)

Get-ChildItem WSMan:\localhost\Listener |
    Where-Object { $_.Keys -contains 'Transport=HTTPS' } |
    Remove-Item -Recurse -Force
New-Item -Path WSMan:\localhost\Listener -Transport HTTPS -Address * `
    -CertificateThumbPrint $cert.Thumbprint -Force | Out-Null

Get-ChildItem WSMan:\localhost\Listener |
    Where-Object { $_.Keys -contains 'Transport=HTTP' } |
    Remove-Item -Recurse -Force

Set-Item -Path WSMan:\localhost\Service\AllowUnencrypted -Value $false
Set-Item -Path WSMan:\localhost\Service\Auth\Basic -Value $false
Set-Item -Path WSMan:\localhost\Service\Auth\Negotiate -Value $true

Remove-NetFirewallRule -Name 'WinRM-HTTP-Build' -ErrorAction SilentlyContinue
if (-not (Get-NetFirewallRule -Name 'WinRM-HTTPS-In' -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -Name 'WinRM-HTTPS-In' -DisplayName 'WinRM HTTPS' -Direction Inbound `
        -Protocol TCP -LocalPort 5986 -Action Allow -Profile Any | Out-Null
}
Restart-Service -Name WinRM

# Remove secrets and disable auto-logon.
Remove-Item -Path C:\campus\unattend-oobe.xml -Force -ErrorAction SilentlyContinue
$winlogon = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon'
Set-ItemProperty -Path $winlogon -Name AutoAdminLogon -Value '0'
Remove-ItemProperty -Path $winlogon -Name DefaultPassword -ErrorAction SilentlyContinue

Set-Content -Path C:\campus\firstboot.done -Value (Get-Date -Format o)
Stop-Transcript
