#Requires -RunAsAdministrator
$ErrorActionPreference = 'Stop'
$pilotRoot = Split-Path -Parent $PSScriptRoot
$pilotPython = (Resolve-Path -LiteralPath (Join-Path $pilotRoot '.venv-phone\Scripts\python.exe')).Path
$pilotRule = 'VoiceZeroTrust-PhonePilot-LocalSubnet-8765'
if (Get-NetFirewallRule -Name $pilotRule -ErrorAction SilentlyContinue) {
    Write-Host "Rule already exists: $pilotRule"
} else {
    New-NetFirewallRule -Name $pilotRule -DisplayName 'VoiceZeroTrust phone pilot (local subnet only)' `
        -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8765 `
        -RemoteAddress LocalSubnet -Program $pilotPython -Profile Any | Out-Null
    Write-Host "Enabled TCP 8765 for this Python executable from the local subnet only."
}
Write-Host "To remove later: Remove-NetFirewallRule -Name $pilotRule"
