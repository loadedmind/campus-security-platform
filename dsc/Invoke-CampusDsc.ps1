<#
.SYNOPSIS
    Compiles and applies CampusNode on the local host. Called by Ansible.

.DESCRIPTION
    Idempotent. Emits a single JSON line on stdout:
      {"changed": <bool>, "in_desired_state": <bool>, "resources_not_in_desired_state": [...]}
    so the Ansible task can report changed/failed accurately.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $Role,
    [Parameter(Mandatory)] [string] $TimeZone,
    [Parameter(Mandatory)] [string] $WsusUrl,
    [Parameter(Mandatory)] [string] $TargetGroup
)

$ErrorActionPreference = 'Stop'
$root   = Join-Path $env:ProgramData 'CampusPlatform\dsc'
$mofDir = Join-Path $root 'mof'
$lcmDir = Join-Path $root 'lcm'

. (Join-Path $root 'CampusNode.ps1')

$null = CampusLcm -OutputPath $lcmDir
Set-DscLocalConfigurationManager -Path $lcmDir -Force

$null = CampusNode -OutputPath $mofDir -Role $Role -TimeZone $TimeZone -WsusUrl $WsusUrl -TargetGroup $TargetGroup

$before = Test-DscConfiguration -Path $mofDir -ErrorAction SilentlyContinue
$wasCompliant = [bool]($before -and $before.InDesiredState)

Start-DscConfiguration -Path $mofDir -Wait -Force -ErrorAction Stop

$after = Test-DscConfiguration -Detailed -ErrorAction Stop
$notInState = @($after.ResourcesNotInDesiredState | ForEach-Object { $_.ResourceId })

[pscustomobject]@{
    changed                        = -not $wasCompliant
    in_desired_state               = [bool]$after.InDesiredState
    resources_not_in_desired_state = $notInState
} | ConvertTo-Json -Compress
