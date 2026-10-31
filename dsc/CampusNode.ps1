<#
.SYNOPSIS
    Desired state for every platform host (Windows PowerShell 5.1 DSC).

.DESCRIPTION
    One configuration per node, parameterised by role. Ansible copies this file
    to the host, compiles it locally and applies it with the LCM in
    ApplyAndAutoCorrect mode, so configuration drift is reverted every 15
    minutes by the host itself, without a pipeline run or a person.

    Roles:
      secapp  campus security application host (simulator + exporters)
      wsus    shared WSUS server; also hosts the ring target groups

    Modules are baked into the golden image (packer/scripts/install-dsc-modules.ps1).
#>
Configuration CampusNode {
    param(
        [Parameter(Mandatory)] [ValidateSet('secapp', 'wsus')] [string] $Role,
        [Parameter(Mandatory)] [string] $TimeZone,
        [Parameter(Mandatory)] [ValidatePattern('^http://[0-9.]+:8530$')] [string] $WsusUrl,
        [Parameter(Mandatory)] [ValidatePattern('^ring[0-2]$')] [string] $TargetGroup,
        [string] $WsusContentDir = 'C:\WSUS'
    )

    Import-DscResource -ModuleName PSDesiredStateConfiguration
    Import-DscResource -ModuleName ComputerManagementDsc -ModuleVersion 10.0.0
    Import-DscResource -ModuleName NetworkingDsc -ModuleVersion 9.1.0
    Import-DscResource -ModuleName UpdateServicesDsc -ModuleVersion 1.3.0

    Node 'localhost' {

        # ---------------------------------------------------------- baseline
        TimeZone Tz {
            IsSingleInstance = 'Yes'
            TimeZone         = $TimeZone
        }

        Firewall WinRmHttps {
            Name        = 'WinRM-HTTPS-In'
            DisplayName = 'WinRM HTTPS'
            Ensure      = 'Present'
            Enabled     = 'True'
            Action      = 'Allow'
            Direction   = 'Inbound'
            Protocol    = 'TCP'
            LocalPort   = '5986'
            Profile     = 'Any'
        }

        Firewall WindowsExporter {
            Name        = 'Campus-WindowsExporter-In'
            DisplayName = 'Prometheus windows_exporter'
            Ensure      = 'Present'
            Enabled     = 'True'
            Action      = 'Allow'
            Direction   = 'Inbound'
            Protocol    = 'TCP'
            LocalPort   = '9182'
            Profile     = 'Any'
        }

        # Running so windows_exporter's update collector can report pending
        # updates; NoAutoUpdate below keeps it from installing anything itself.
        Service WindowsUpdate {
            Name        = 'wuauserv'
            StartupType = 'Automatic'
            State       = 'Running'
        }

        # WSUS client policy (equivalent of the GPO). Automatic install is off:
        # the patch pipeline decides when a ring installs, never the host.
        $wuKey = 'HKEY_LOCAL_MACHINE\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate'
        $auKey = "$wuKey\AU"

        Registry WUServer {
            Key = $wuKey; ValueName = 'WUServer'; ValueType = 'String'; ValueData = $WsusUrl; Ensure = 'Present'
        }
        Registry WUStatusServer {
            Key = $wuKey; ValueName = 'WUStatusServer'; ValueType = 'String'; ValueData = $WsusUrl; Ensure = 'Present'
        }
        Registry TargetGroupEnabled {
            Key = $wuKey; ValueName = 'TargetGroupEnabled'; ValueType = 'Dword'; ValueData = '1'; Ensure = 'Present'
        }
        Registry TargetGroup {
            Key = $wuKey; ValueName = 'TargetGroup'; ValueType = 'String'; ValueData = $TargetGroup; Ensure = 'Present'
        }
        Registry UseWUServer {
            Key = $auKey; ValueName = 'UseWUServer'; ValueType = 'Dword'; ValueData = '1'; Ensure = 'Present'
        }
        Registry NoAutoUpdate {
            Key = $auKey; ValueName = 'NoAutoUpdate'; ValueType = 'Dword'; ValueData = '1'; Ensure = 'Present'
        }

        # ----------------------------------------------------------- secapp
        if ($Role -eq 'secapp') {
            Firewall CampusSecSim {
                Name        = 'Campus-SecSim-In'
                DisplayName = 'Campus security simulator API'
                Ensure      = 'Present'
                Enabled     = 'True'
                Action      = 'Allow'
                Direction   = 'Inbound'
                Protocol    = 'TCP'
                LocalPort   = '8080'
                Profile     = 'Any'
            }
        }

        # ------------------------------------------------------------- wsus
        if ($Role -eq 'wsus') {
            WindowsFeature UpdateServices {
                Name   = 'UpdateServices'
                Ensure = 'Present'
            }

            # PowerShell cmdlets (Get-WsusUpdate, Approve-WsusUpdate). The MMC
            # sub-feature is not installable on Server Core, so no IncludeAllSubFeature.
            WindowsFeature UpdateServicesApi {
                Name      = 'UpdateServices-API'
                Ensure    = 'Present'
                DependsOn = '[WindowsFeature]UpdateServices'
            }

            UpdateServicesServer Wsus {
                Ensure                            = 'Present'
                ContentDir                        = $WsusContentDir
                Languages                         = @('en')
                # '*' = all products. Narrow after the first sync with Get-WsusProduct.
                Products                          = @('*')
                Classifications                   = @(
                    'E6CF1350-C01B-414D-A61F-263D14D133B4'  # Critical Updates
                    '0FA1201D-4330-4FA8-8AE9-B877473B6441'  # Security Updates
                    '28BC880E-0592-4CBF-8F95-C79B17911D5F'  # Update Rollups
                )
                SynchronizeAutomatically          = $true
                SynchronizeAutomaticallyTimeOfDay = '04:00:00'
                SynchronizationsPerDay            = 1
                ClientTargetingMode               = 'Client'
                DependsOn                         = '[WindowsFeature]UpdateServicesApi'
            }

            foreach ($ring in 'ring0', 'ring1', 'ring2') {
                UpdateServicesComputerTargetGroup $ring {
                    Name      = $ring
                    Path      = 'All Computers'
                    Ensure    = 'Present'
                    DependsOn = '[UpdateServicesServer]Wsus'
                }
            }

            Firewall WsusHttp {
                Name        = 'Campus-WSUS-In'
                DisplayName = 'WSUS HTTP'
                Ensure      = 'Present'
                Enabled     = 'True'
                Action      = 'Allow'
                Direction   = 'Inbound'
                Protocol    = 'TCP'
                LocalPort   = '8530'
                Profile     = 'Any'
            }
        }
    }
}

[DscLocalConfigurationManager()]
Configuration CampusLcm {
    Node 'localhost' {
        Settings {
            RefreshMode                    = 'Push'
            ConfigurationMode              = 'ApplyAndAutoCorrect'
            ConfigurationModeFrequencyMins = 15
            RebootNodeIfNeeded             = $false   # reboots are owned by the patch pipeline
            ActionAfterReboot              = 'ContinueConfiguration'
        }
    }
}
