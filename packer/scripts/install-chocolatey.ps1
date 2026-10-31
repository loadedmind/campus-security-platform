# Installs the Chocolatey client into the golden image, then removes the public
# community source. Deployed hosts only install packages that the release
# pipeline built and checksummed (see ansible/roles/chocolatey_client).
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor 3072

$installer = Join-Path $env:TEMP 'choco-install.ps1'
Invoke-WebRequest -UseBasicParsing -Uri 'https://community.chocolatey.org/install.ps1' -OutFile $installer
& $installer

$choco = Join-Path $env:ProgramData 'chocolatey\bin\choco.exe'
& $choco feature enable --name=usePackageExitCodes --limit-output
& $choco feature disable --name=showDownloadProgress --limit-output
& $choco source remove --name=chocolatey --limit-output

& $choco --version | Set-Content -Path C:\campus\chocolatey-version.txt
Remove-Item $installer -Force
