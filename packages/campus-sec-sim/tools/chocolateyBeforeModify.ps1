# Runs before upgrade or uninstall: stop and unregister the service so the
# binaries in this package folder are not locked.
$ErrorActionPreference = 'Stop'

$toolsDir   = Split-Path -Parent $MyInvocation.MyCommand.Definition
$serviceExe = Join-Path $toolsDir 'CampusSecSim.exe'

if (Get-Service -Name CampusSecSim -ErrorAction SilentlyContinue) {
    & $serviceExe stop
    & $serviceExe uninstall
}
