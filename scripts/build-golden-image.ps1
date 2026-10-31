<#
.SYNOPSIS
    Builds and publishes a versioned golden image on the Hyper-V host.

.DESCRIPTION
    Runs Packer, then copies the resulting VHDX to
    <ImageRoot>\ws2025-core-<yyyy.MM>.vhdx and marks it read-only. The file is
    the parent of every differencing disk created by Terraform, so it must
    never be modified after publishing. Roll it out by changing `image:` in
    sites/<site>.yaml, ring by ring.

    Run on: the Hyper-V host (alien), elevated PowerShell, from the repo root.

.EXAMPLE
    $env:PKR_VAR_admin_password = '<lab admin password>'
    .\scripts\build-golden-image.ps1 -IsoPath C:\campus-lab\iso\ws2025-eval.iso
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $IsoPath,
    [string] $ImageRoot = 'C:\campus-lab\images',
    [string] $Version = (Get-Date -Format 'yyyy.MM'),
    [string] $OutputDirectory = 'C:\campus-lab\packer-output'
)

$ErrorActionPreference = 'Stop'

if (-not $env:PKR_VAR_admin_password) {
    throw 'Set $env:PKR_VAR_admin_password before running.'
}
if ($Version -notmatch '^\d{4}\.\d{2}$') { throw "Version must be yyyy.MM, got '$Version'" }

$imageName = "ws2025-core-$Version"
$target = Join-Path $ImageRoot "$imageName.vhdx"
if (Test-Path $target) {
    throw "$target already exists. Published images are immutable; pick a new -Version."
}

foreach ($tool in 'packer', 'oscdimg') {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { throw "$tool not found on PATH" }
}

$isoHash = (Get-FileHash -Path $IsoPath -Algorithm SHA256).Hash.ToLowerInvariant()
$template = Join-Path $PSScriptRoot '..\packer\ws2025-core.pkr.hcl'

if (Test-Path $OutputDirectory) { Remove-Item $OutputDirectory -Recurse -Force }

packer init $template
if ($LASTEXITCODE -ne 0) { throw 'packer init failed' }

packer build -force `
    -var "iso_path=$IsoPath" `
    -var "iso_sha256=$isoHash" `
    -var "output_directory=$OutputDirectory" `
    $template
if ($LASTEXITCODE -ne 0) { throw 'packer build failed' }

$vhdx = Get-ChildItem -Path (Join-Path $OutputDirectory 'Virtual Hard Disks') -Filter '*.vhdx' | Select-Object -First 1
if (-not $vhdx) { throw 'Packer output contains no VHDX' }

New-Item -ItemType Directory -Path $ImageRoot -Force | Out-Null
Copy-Item -Path $vhdx.FullName -Destination $target
Set-ItemProperty -Path $target -Name IsReadOnly -Value $true

$hash = (Get-FileHash -Path $target -Algorithm SHA256).Hash.ToLowerInvariant()
"$hash  $imageName.vhdx" | Set-Content -Path "$target.sha256"

Write-Output "Published $target"
Write-Output "Set 'image: $imageName' in sites/<site>.yaml to roll it out (canary ring first)."
