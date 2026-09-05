# Wrapper for the Windows scheduled task that refreshes the public
# "EPGs Matched" badge. The task runs this; this runs the Python script and
# keeps a log, so a failed refresh leaves evidence rather than a badge that
# quietly stops moving.
#
# Register the task (run once, from an elevated PowerShell):
#   $action  = New-ScheduledTaskAction -Execute "powershell.exe" `
#       -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$PWD\scripts\update_epgs_matched_badge.ps1`""
#   $trigger = New-ScheduledTaskTrigger -Daily -At 10:00
#   Register-ScheduledTask -TaskName "EPG Janitor badge refresh" -Action $action -Trigger $trigger

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$logDir = Join-Path $root "dist"
$log = Join-Path $logDir "badge-update.log"

if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Force $logDir | Out-Null }

$stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content -Path $log -Value "[$stamp] refreshing the EPGs Matched badge" -Encoding utf8

try {
    Set-Location $root
    $output = & py -3 "scripts\update_epgs_matched_badge.py" 2>&1
    $exit = $LASTEXITCODE
    Add-Content -Path $log -Value $output -Encoding utf8
    Add-Content -Path $log -Value "[$stamp] exit code $exit" -Encoding utf8
    exit $exit
}
catch {
    Add-Content -Path $log -Value "[$stamp] FAILED: $_" -Encoding utf8
    exit 1
}
