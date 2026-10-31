# Bakes pinned DSC resource modules into the image so hosts never pull from the
# PowerShell Gallery at deploy time. Versions = latest GitHub release tags,
# checked 2026-10-31. Bump here, rebuild the image, roll it out by ring.
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor 3072

$modules = [ordered]@{
    'ComputerManagementDsc' = '10.0.0'
    'NetworkingDsc'         = '9.1.0'
    'UpdateServicesDsc'     = '1.3.0'
}

Install-PackageProvider -Name NuGet -MinimumVersion 2.8.5.201 -Force -Scope AllUsers | Out-Null
Set-PSRepository -Name PSGallery -InstallationPolicy Trusted

foreach ($name in $modules.Keys) {
    Install-Module -Name $name -RequiredVersion $modules[$name] -Scope AllUsers -Force -AllowClobber
    $installed = Get-Module -ListAvailable -Name $name | Where-Object { $_.Version -eq [version]$modules[$name] }
    if (-not $installed) { throw "Module $name $($modules[$name]) did not install" }
}

Set-PSRepository -Name PSGallery -InstallationPolicy Untrusted
$modules.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" } |
    Set-Content -Path C:\campus\dsc-modules.txt
