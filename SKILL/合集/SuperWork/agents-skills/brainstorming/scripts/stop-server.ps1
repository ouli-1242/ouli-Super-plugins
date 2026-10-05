# Stop the brainstorm server and clean up (PowerShell, Windows).
# Usage: .\stop-server.ps1 <session_dir>
#
# Kills the server process. Only deletes session directory if it's under
# $env:TEMP (ephemeral). Persistent directories (.superpowers/) are kept so
# mockups can be reviewed later. Native Windows port of stop-server.sh.

param(
  [Parameter(Mandatory = $true)]
  [string]$SessionDir
)

$ErrorActionPreference = 'Stop'

# Accept either the session dir or the JSON's state_dir (which already ends in \state)
$SessionDir = $SessionDir.TrimEnd('\')
if ($SessionDir.EndsWith('\state')) {
  $SessionDir = $SessionDir.Substring(0, $SessionDir.Length - 6)
}

$stateDir = Join-Path $SessionDir 'state'
$pidFile = Join-Path $stateDir 'server.pid'
$serverIdFile = Join-Path $stateDir 'server-instance-id'
$serverInfoFile = Join-Path $stateDir 'server-info'
$stoppedFile = Join-Path $stateDir 'server-stopped'

function Mark-Stopped([string]$reason) {
  Remove-Item -LiteralPath $serverInfoFile -Force -ErrorAction SilentlyContinue
  $json = '{"reason":"' + $reason + '","timestamp":' + [int][double]::Parse((Get-Date -UFormat %s)) + '}'
  Set-Content -LiteralPath $stoppedFile -Value $json -NoNewline
}

function Get-ExpectedServerId {
  if (-not (Test-Path -LiteralPath $serverIdFile)) { return $null }
  $id = (Get-Content -LiteralPath $serverIdFile -Raw).Trim()
  if ($id -notmatch '^[A-Za-z0-9_-]{32,64}$') { return $null }
  return $id
}

# Confirm a PID has this session's per-start instance id, not just a familiar
# process name. Ambiguous or legacy metadata fails closed as stale_pid.
function Test-IsBrainstormServer([int]$ProcessId) {
  try {
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction Stop
  }
  catch { return $false }
  if (-not $proc) { return $false }
  $expected = Get-ExpectedServerId
  if (-not $expected) { return $false }
  return $proc.CommandLine -like "*--brainstorm-server-id=$expected*"
}

if (Test-Path -LiteralPath $pidFile) {
  $rawPid = Get-Content -LiteralPath $pidFile -Raw
  if ($rawPid -notmatch '^\d+$') {
    Remove-Item -LiteralPath $pidFile, $serverIdFile -Force -ErrorAction SilentlyContinue
    Mark-Stopped 'stale_pid'
    Write-Output '{"status": "stale_pid"}'
    exit 0
  }
  $serverPid = [int]$rawPid

  # Refuse to signal a PID we can't prove is our server.
  if (-not (Test-IsBrainstormServer $serverPid)) {
    Remove-Item -LiteralPath $pidFile, $serverIdFile -Force -ErrorAction SilentlyContinue
    Mark-Stopped 'stale_pid'
    Write-Output '{"status": "stale_pid"}'
    exit 0
  }

  Stop-Process -Id $serverPid -ErrorAction SilentlyContinue

  # Wait for graceful shutdown (up to ~2s), then escalate to force
  for ($i = 0; $i -lt 20; $i++) {
    if (-not (Get-Process -Id $serverPid -ErrorAction SilentlyContinue)) { break }
    Start-Sleep -Milliseconds 100
  }
  if (Get-Process -Id $serverPid -ErrorAction SilentlyContinue) {
    Stop-Process -Id $serverPid -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 100
  }
  if (Get-Process -Id $serverPid -ErrorAction SilentlyContinue) {
    Write-Output '{"status": "failed", "error": "process still running"}'
    exit 1
  }

  Remove-Item -LiteralPath $pidFile, $serverIdFile -Force -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath (Join-Path $stateDir 'server.log'), (Join-Path $stateDir 'server.log.err') -Force -ErrorAction SilentlyContinue
  Mark-Stopped 'stop-server.ps1'

  # Only delete ephemeral TEMP directories
  $tempPrefix = $env:TEMP.TrimEnd('\')
  if ($SessionDir.StartsWith($tempPrefix + '\')) {
    Remove-Item -LiteralPath $SessionDir -Recurse -Force -ErrorAction SilentlyContinue
  }

  Write-Output '{"status": "stopped"}'
}
else {
  Write-Output '{"status": "not_running"}'
}