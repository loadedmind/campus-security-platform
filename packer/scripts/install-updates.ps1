# Installs all applicable software updates through the Windows Update Agent COM
# API. Run twice with a restart between, because servicing-stack updates gate
# later cumulative updates. Must run elevated locally (Packer elevated_user).
$ErrorActionPreference = 'Stop'

$session  = New-Object -ComObject Microsoft.Update.Session
$searcher = $session.CreateUpdateSearcher()
Write-Output 'Searching for updates...'
$result = $searcher.Search("IsInstalled=0 and IsHidden=0 and Type='Software'")

if ($result.Updates.Count -eq 0) {
    Write-Output 'No applicable updates.'
    exit 0
}

$toInstall = New-Object -ComObject Microsoft.Update.UpdateColl
foreach ($update in $result.Updates) {
    if (-not $update.EulaAccepted) { $update.AcceptEula() }
    Write-Output ("Queued: {0}" -f $update.Title)
    [void]$toInstall.Add($update)
}

$downloader = $session.CreateUpdateDownloader()
$downloader.Updates = $toInstall
$dl = $downloader.Download()
Write-Output ("Download result code: {0}" -f $dl.ResultCode)

$installer = $session.CreateUpdateInstaller()
$installer.Updates = $toInstall
$install = $installer.Install()
Write-Output ("Install result code: {0}; reboot required: {1}" -f $install.ResultCode, $install.RebootRequired)

# 2 = succeeded, 3 = succeeded with errors
if ($install.ResultCode -notin 2, 3) {
    throw "Windows Update install failed with result code $($install.ResultCode)"
}
exit 0
