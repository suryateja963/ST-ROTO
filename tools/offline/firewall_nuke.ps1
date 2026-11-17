# T-087 / OQ-26 (approved by the owner 2026-11-17): temporary Windows Firewall rule that blocks ALL outbound traffic of
# Nuke 17.1, to test that Nuke + ST-ROTO work with no network. Needs an elevated PowerShell (UAC).
#   powershell -ExecutionPolicy Bypass -File tools\offline\firewall_nuke.ps1 -Action add|remove|status
# Writes the outcome to logs\offline\firewall_<action>.txt (logs\ is git-ignored) so a non-elevated caller can read it.
param(
    [ValidateSet("add", "remove", "status")] [string]$Action = "status",
    [string]$Program = "C:\Program Files\Nuke17.1v3\Nuke17.1.exe"
)
$name = "ST-ROTO offline test (block Nuke outbound)"
$logDir = Join-Path $PSScriptRoot "..\..\logs\offline"
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir ("firewall_{0}.txt" -f $Action)
try {
    if ($Action -eq "add") {
        Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue | Remove-NetFirewallRule
        New-NetFirewallRule -DisplayName $name -Direction Outbound -Program $Program -Action Block -Profile Any -Enabled True | Out-Null
    } elseif ($Action -eq "remove") {
        Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    }
    $r = Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue
    if ($r) { "rule present: enabled=$($r.Enabled) action=$($r.Action) direction=$($r.Direction)" | Out-File $log -Encoding utf8 }
    else { "rule absent" | Out-File $log -Encoding utf8 }
} catch {
    "error: $_" | Out-File $log -Encoding utf8
}
