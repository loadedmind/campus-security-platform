$ErrorActionPreference = 'Stop'

$toolsDir   = Split-Path -Parent $MyInvocation.MyCommand.Definition
$serviceExe = Join-Path $toolsDir 'CampusSecSim.exe'
$configFile = Join-Path $env:ProgramData 'CampusSecSim\config.yaml'

foreach ($required in 'campus-sec-sim.exe', 'CampusSecSim.exe', 'CampusSecSim.xml') {
    if (-not (Test-Path (Join-Path $toolsDir $required))) {
        throw "Package is missing $required"
    }
}

New-Item -ItemType Directory -Path (Join-Path $env:ProgramData 'CampusSecSim\logs') -Force | Out-Null

# Do not register a service that cannot start: Ansible writes the config first.
if (-not (Test-Path $configFile)) {
    throw "Missing $configFile. Deploy configuration (Ansible role campus_sec_sim) before installing."
}

if (Get-Service -Name CampusSecSim -ErrorAction SilentlyContinue) {
    & $serviceExe uninstall
}
& $serviceExe install
if ($LASTEXITCODE -ne 0) { throw "WinSW install failed with exit code $LASTEXITCODE" }

& $serviceExe start
if ($LASTEXITCODE -ne 0) { throw "WinSW start failed with exit code $LASTEXITCODE" }
