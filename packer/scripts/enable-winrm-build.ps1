# Build-time only: WinRM over HTTP with Basic auth so Packer can connect.
# firstboot.ps1 replaces this with an HTTPS-only listener on every deployed VM.
$ErrorActionPreference = 'Stop'

Get-NetConnectionProfile | Where-Object NetworkCategory -eq 'Public' |
    Set-NetConnectionProfile -NetworkCategory Private

Enable-PSRemoting -SkipNetworkProfileCheck -Force
Set-Item -Path WSMan:\localhost\Service\AllowUnencrypted -Value $true
Set-Item -Path WSMan:\localhost\Service\Auth\Basic -Value $true
Set-Item -Path WSMan:\localhost\MaxTimeoutms -Value 1800000
Set-Item -Path WSMan:\localhost\Shell\MaxMemoryPerShellMB -Value 2048

New-NetFirewallRule -Name 'WinRM-HTTP-Build' -DisplayName 'WinRM HTTP (Packer build)' `
    -Direction Inbound -Protocol TCP -LocalPort 5985 -Action Allow -Profile Any | Out-Null

Restart-Service -Name WinRM
