$ErrorActionPreference = 'Stop'

# chocolateyBeforeModify.ps1 already stopped and removed the service; this is a
# safety net for hosts where that script did not run.
$service = Get-Service -Name CampusSecSim -ErrorAction SilentlyContinue
if ($service) {
    Stop-Service -Name CampusSecSim -Force -ErrorAction SilentlyContinue
    sc.exe delete CampusSecSim | Out-Null
}
