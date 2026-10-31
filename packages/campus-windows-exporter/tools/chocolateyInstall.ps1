$ErrorActionPreference = 'Stop'

$toolsDir   = Split-Path -Parent $MyInvocation.MyCommand.Definition
$configFile = Join-Path $env:ProgramData 'windows_exporter\config.yaml'
$msi        = Get-ChildItem -Path $toolsDir -Filter 'windows_exporter-*-amd64.msi' | Select-Object -First 1

if (-not $msi) { throw 'Embedded windows_exporter MSI not found in package' }
if (-not (Test-Path $configFile)) {
    throw "Missing $configFile. Ansible role windows_exporter writes it before install."
}

$packageArgs = @{
    PackageName    = $env:ChocolateyPackageName
    FileType       = 'msi'
    File64         = $msi.FullName
    SilentArgs     = "/qn /norestart CONFIG_FILE=`"$configFile`""
    ValidExitCodes = @(0, 3010, 1641)
}
Install-ChocolateyInstallPackage @packageArgs
