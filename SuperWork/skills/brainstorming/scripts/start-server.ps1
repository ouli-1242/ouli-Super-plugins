# Start the brainstorm server and output connection info (PowerShell, Windows).
# Usage: .\start-server.ps1 [-ProjectDir <path>] [-Host <bind-host>] [-UrlHost <display-host>] [-IdleTimeoutMinutes <n>] [-Open] [-Foreground] [-Background]
#
# Starts server on a random high port, outputs JSON with URL.
# Each session gets its own directory to avoid conflicts.
# Native Windows port of start-server.sh — unlike bash, backgrounding survives
# because Start-Process creates a real Win32 process (no MSYS reaping).

param(
  [string]$ProjectDir = '',
  [string]$BindHost = '127.0.0.1',
  [string]$UrlHost = '',
  [int]$IdleTimeoutMinutes = 240,
  [switch]$Open,
  [switch]$Foreground,
  [switch]$Background
)

$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

$node = Get-Command node -ErrorAction SilentlyContinue
if (-not $node) {
  Write-Output '{"error": "node not found in PATH"}'
  exit 1
}

if (-not $UrlHost) {
  $UrlHost = if ($BindHost -in @('127.0.0.1', 'localhost')) { 'localhost' } else { $BindHost }
}
if ($IdleTimeoutMinutes -lt 1) {
  Write-Output '{"error": "--idle-timeout-minutes must be a positive integer"}'
  exit 1
}

$env:BRAINSTORM_OPEN = if ($Open) { '1' } else { '' }
$env:BRAINSTORM_IDLE_TIMEOUT_MS = $IdleTimeoutMinutes * 60000

# Session files embed the session key — keep session dirs owner-only on Windows.
$sessionId = "$PID-$(Get-Date -UFormat %s)"

if ($ProjectDir) {
  $brainstormDir = Join-Path $ProjectDir '.superpowers\brainstorm'
  $sessionDir = Join-Path $brainstormDir $sessionId
  $env:BRAINSTORM_PORT_FILE = Join-Path $brainstormDir '.last-port'
  $env:BRAINSTORM_TOKEN_FILE = Join-Path $brainstormDir '.last-token'
}
else {
  $sessionDir = Join-Path $env:TEMP "brainstorm-$sessionId"
}

$stateDir = Join-Path $sessionDir 'state'
$contentDir = Join-Path $sessionDir 'content'
$pidFile = Join-Path $stateDir 'server.pid'
$logFile = Join-Path $stateDir 'server.log'
$logErrFile = Join-Path $stateDir 'server.log.err'
$serverIdFile = Join-Path $stateDir 'server-instance-id'

New-Item -ItemType Directory -Path $contentDir, $stateDir -Force | Out-Null

$idChars = (48..57) + (97..102)
$serverId = -join (1..32 | ForEach-Object { [char]$idChars[(Get-Random -Maximum $idChars.Count)] })
Set-Content -LiteralPath $serverIdFile -Value $serverId -NoNewline

# Kill any existing server for this session
if (Test-Path -LiteralPath $pidFile) {
  $oldPid = Get-Content -LiteralPath $pidFile
  if ($oldPid -match '^\d+$') {
    Stop-Process -Id $oldPid -Force -ErrorAction SilentlyContinue
  }
  Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
}

$env:BRAINSTORM_DIR = $sessionDir
$env:BRAINSTORM_HOST = $BindHost
$env:BRAINSTORM_URL_HOST = $UrlHost
$env:BRAINSTORM_OWNER_PID = ''   # Windows: node cannot verify MSYS/win32 PIDs; watchdog disabled

if ($Foreground) {
  Push-Location $scriptDir
  try {
    & $node.Source 'server.cjs' "--brainstorm-server-id=$serverId"
    exit $LASTEXITCODE
  }
  finally { Pop-Location }
}

# Background mode: Start-Process creates a real Win32 process that survives.
Push-Location $scriptDir
try {
  $proc = Start-Process -FilePath $node.Source `
    -ArgumentList 'server.cjs', "--brainstorm-server-id=$serverId" `
    -WorkingDirectory $scriptDir `
    -RedirectStandardOutput $logFile `
    -RedirectStandardError $logErrFile `
    -WindowStyle Hidden `
    -PassThru
}
finally { Pop-Location }

Set-Content -LiteralPath $pidFile -Value $proc.Id -NoNewline

# Wait for server-started message (check log file)
for ($i = 0; $i -lt 50; $i++) {
  if (Test-Path -LiteralPath $logFile) {
    $started = Select-String -LiteralPath $logFile -Pattern 'server-started' -SimpleMatch | Select-Object -First 1
    if ($started) {
      if (-not $proc.HasExited) {
        Write-Output $started.Line
        exit 0
      }
      Write-Output '{"error": "Server started but was killed. Retry with -Foreground in a persistent terminal."}'
      exit 1
    }
  }
  Start-Sleep -Milliseconds 100
}

Write-Output '{"error": "Server failed to start within 5 seconds"}'
exit 1