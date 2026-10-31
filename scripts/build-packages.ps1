<#
.SYNOPSIS
    Builds the internal Chocolatey packages for one platform release.

.DESCRIPTION
    1. Freezes the simulator into a single exe (PyInstaller).
    2. Downloads pinned upstream binaries and verifies SHA-256 (packages/upstream.json).
    3. choco pack for campus-sec-sim (release version) and
       campus-windows-exporter (upstream version).
    4. Writes SHA256SUMS for everything in the output directory.

    Runs in CI on windows-latest (release workflow). Also runnable locally on any
    Windows machine with Python 3.12 and Chocolatey.

.EXAMPLE
    .\scripts\build-packages.ps1 -Version 1.2.0 -OutputDirectory dist
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [ValidatePattern('^\d+\.\d+\.\d+$')] [string] $Version,
    [string] $OutputDirectory = 'dist'
)

$ErrorActionPreference = 'Stop'
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$work     = Join-Path $repoRoot 'build'
$out      = New-Item -ItemType Directory -Path (Join-Path $repoRoot $OutputDirectory) -Force

if (Test-Path $work) { Remove-Item $work -Recurse -Force }
New-Item -ItemType Directory -Path $work | Out-Null

function Get-VerifiedFile {
    param([string] $Url, [string] $Sha256, [string] $Destination)
    Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $Destination
    $actual = (Get-FileHash -Path $Destination -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $Sha256.ToLowerInvariant()) {
        throw "Checksum mismatch for $Url`n expected $Sha256`n actual   $actual"
    }
}

$upstream = Get-Content (Join-Path $repoRoot 'packages\upstream.json') -Raw | ConvertFrom-Json

# --- 1. simulator executable -------------------------------------------------
$simSrc  = Join-Path $repoRoot 'simulator'
$initPy  = Join-Path $simSrc 'src\campus_sec_sim\__init__.py'
$initOld = Get-Content $initPy -Raw
try {
    ($initOld -replace '__version__ = ".*"', "__version__ = `"$Version`"") |
        Set-Content -Path $initPy -NoNewline -Encoding utf8
    python -m pip install --quiet -r (Join-Path $simSrc 'requirements.lock') pyinstaller==6.22.3
    if ($LASTEXITCODE -ne 0) { throw 'pip install failed' }
    python -m PyInstaller --noconfirm --onefile --name campus-sec-sim `
        --paths (Join-Path $simSrc 'src') `
        --distpath (Join-Path $work 'pyi-dist') --workpath (Join-Path $work 'pyi-build') `
        --specpath $work (Join-Path $simSrc 'launcher.py')
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }
}
finally {
    Set-Content -Path $initPy -Value $initOld -NoNewline -Encoding utf8
}

& (Join-Path $work 'pyi-dist\campus-sec-sim.exe') --version
if ($LASTEXITCODE -ne 0) { throw 'Frozen executable failed to start' }

# --- 2. campus-sec-sim package ----------------------------------------------
$simPkg = Join-Path $work 'campus-sec-sim'
Copy-Item -Path (Join-Path $repoRoot 'packages\campus-sec-sim') -Destination $simPkg -Recurse
Copy-Item -Path (Join-Path $work 'pyi-dist\campus-sec-sim.exe') -Destination (Join-Path $simPkg 'tools')
Get-VerifiedFile -Url $upstream.winsw.url -Sha256 $upstream.winsw.sha256 `
    -Destination (Join-Path $simPkg 'tools\CampusSecSim.exe')
# .ignore files stop Chocolatey from creating PATH shims for these executables.
New-Item -ItemType File -Path (Join-Path $simPkg 'tools\campus-sec-sim.exe.ignore') -Force | Out-Null
New-Item -ItemType File -Path (Join-Path $simPkg 'tools\CampusSecSim.exe.ignore') -Force | Out-Null

choco pack (Join-Path $simPkg 'campus-sec-sim.nuspec') --version $Version --outputdirectory $out.FullName
if ($LASTEXITCODE -ne 0) { throw 'choco pack campus-sec-sim failed' }

# --- 3. campus-windows-exporter package -------------------------------------
$weVersion = $upstream.windows_exporter.version
$wePkg = Join-Path $work 'campus-windows-exporter'
Copy-Item -Path (Join-Path $repoRoot 'packages\campus-windows-exporter') -Destination $wePkg -Recurse
Get-VerifiedFile -Url $upstream.windows_exporter.url -Sha256 $upstream.windows_exporter.sha256 `
    -Destination (Join-Path $wePkg "tools\$($upstream.windows_exporter.file)")

choco pack (Join-Path $wePkg 'campus-windows-exporter.nuspec') --version $weVersion --outputdirectory $out.FullName
if ($LASTEXITCODE -ne 0) { throw 'choco pack campus-windows-exporter failed' }

# --- 4. checksums -------------------------------------------------------------
Get-ChildItem -Path $out.FullName -Filter '*.nupkg' | Sort-Object Name | ForEach-Object {
    '{0}  {1}' -f (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant(), $_.Name
} | Set-Content -Path (Join-Path $out.FullName 'SHA256SUMS') -Encoding ascii

Get-Content (Join-Path $out.FullName 'SHA256SUMS')
