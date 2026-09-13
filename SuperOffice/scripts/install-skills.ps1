# Generic multi-agent skill installer - SELF-CONTAINED: this pack carries its own
# agents.json next to the script, so the pack can be moved or copied alone.
#
#   pwsh -NoProfile -File scripts/install-skills.ps1 -Agent claude -DryRun
#   pwsh -NoProfile -File scripts/install-skills.ps1 -Agent dsh,claude
#   pwsh -NoProfile -File scripts/install-skills.ps1 -Agent all -IncludeOptional
#   pwsh -NoProfile -File scripts/install-skills.ps1 -Agent codex -Copy
#
# Why this exists: agents discover skills by <targetPath>/<name>/SKILL.md. Copying
# by hand created drifting snapshots of the same pack; the default -Link mode makes
# this repo the single source instead (junction/symlink), so an edit is live.
#
# Safety: a real (non-reparse) directory at a target name is never overwritten.
# Two packs installed side by side with the same skill name are reported as a
# conflict, because every harness resolves duplicate names silently.
#
# NOTE: keep this file pure ASCII - Windows PowerShell 5.1 misreads BOM-less UTF-8.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string[]]$Agent,
    [string]$PackRoot = (Split-Path $PSScriptRoot -Parent),
    [string]$AgentsFile,
    [switch]$Link,
    [switch]$Copy,
    [switch]$IncludeOptional,
    [switch]$DryRun,
    [switch]$VerifyPaths,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'

# agents.json ships inside the pack (next to scripts/); -AgentsFile overrides it.
if (-not $AgentsFile) { $AgentsFile = Join-Path $PackRoot 'agents.json' }
if (-not (Test-Path -LiteralPath $AgentsFile)) {
    throw "agents.json not found at $AgentsFile; pass -AgentsFile <path>"
}

if (-not $Link -and -not $Copy) { $Link = $true }   # linking is the drift-safe default
if ($Link -and $Copy) { throw '-Link and -Copy are mutually exclusive' }

function Expand-Target([string]$p) {
    return [regex]::Replace($p, '%([A-Za-z_]+)%', { param($m) [Environment]::GetEnvironmentVariable($m.Groups[1].Value) })
}

if (-not (Test-Path -LiteralPath $PackRoot)) { throw "PackRoot not found: $PackRoot" }

$cfg = Get-Content -LiteralPath $AgentsFile -Raw -Encoding UTF8 | ConvertFrom-Json
$bundlePath = Join-Path $PackRoot 'bundle.json'
if (-not (Test-Path -LiteralPath $bundlePath)) { throw "bundle.json not found in $PackRoot" }
$bundle = Get-Content -LiteralPath $bundlePath -Raw -Encoding UTF8 | ConvertFrom-Json

$srcRoot = Join-Path $PackRoot 'agents-skills'   # the canonical folder for name+description harnesses
if (-not (Test-Path -LiteralPath $srcRoot)) { throw "agents-skills/ not found in $PackRoot" }

$wanted = @()
foreach ($raw in $Agent) {
    foreach ($a in ($raw -split ',')) {
        $a = $a.Trim()
        if (-not $a) { continue }
        if ($a -eq 'all') { $wanted += $cfg.agents.PSObject.Properties.Name }
        else { $wanted += $a }
    }
}
$wanted = $wanted | Select-Object -Unique

foreach ($a in $wanted) {
    if (-not $cfg.agents.PSObject.Properties.Name.Contains($a)) {
        throw "unknown agent '$a' (known: $(($cfg.agents.PSObject.Properties.Name) -join ', '))"
    }
}

Write-Output "Pack        : $($bundle.name)  ($($bundle.skills.Count) core + $(@($bundle.optional).Count) optional)"
Write-Output "Source      : $srcRoot"
Write-Output "Mode        : $(if ($Link) { 'link (junction)' } else { 'copy' })$(if ($DryRun) { ' [DRY RUN]' })"
Write-Output ''

$globalIssues = @()

foreach ($a in $wanted) {
    $entry = $cfg.agents.$a
    if (-not $entry.verified -and -not $VerifyPaths) {
        Write-Output "SKIP  $a - path not verified ($($entry.source))"
        Write-Output '      re-run with -VerifyPaths once you have confirmed the directory'
        Write-Output ''
        continue
    }

    $target = Expand-Target $entry.path
    # Each agent names the folder inside this pack it should receive: agents-skills
    # (long text, shared default), codex-skills (adds agents/openai.yaml) or
    # zcode-skills (derived <=250-char descriptions).
    $agentSrc = Join-Path $PackRoot $entry.sourceFolder
    if (-not (Test-Path -LiteralPath $agentSrc)) { $agentSrc = $srcRoot }
    Write-Output "=== $a -> $target   [source: $(Split-Path $agentSrc -Leaf)] ==="

    if (-not (Test-Path -LiteralPath $target)) {
        if ($DryRun) { Write-Output '  would create target dir' }
        else { New-Item -ItemType Directory -Force -Path $target | Out-Null }
    }

    $install = @($bundle.skills)
    if ($IncludeOptional) { $install += @($bundle.optional) }

    foreach ($s in $install) {
        $src = Join-Path $agentSrc $s
        if (-not (Test-Path -LiteralPath (Join-Path $src 'SKILL.md'))) {
            $globalIssues += "MISSING-SOURCE: $a/$s"
            Write-Output "  MISSING-SOURCE  $s"
            continue
        }

        $dst = Join-Path $target $s

        # duplicate-name detection across whatever is already installed
        if (Test-Path -LiteralPath $dst) {
            $item = Get-Item -LiteralPath $dst -Force
            $isLink = [bool]($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint)
            $same = $false
            if ($isLink) {
                $t = @($item.Target)[0]
                $same = $t -and $t.Equals($src, [System.StringComparison]::OrdinalIgnoreCase)
            }
            if ($same) { Write-Output "  ok (already linked)  $s"; continue }
            if ($isLink) {
                if ($DryRun) { Write-Output "  would relink       $s" }
                else { Remove-Item -LiteralPath $dst -Force; }
            }
            elseif ($Force) {
                if ($DryRun) { Write-Output "  would overwrite    $s (existing copy)" }
                else { Remove-Item -LiteralPath $dst -Recurse -Force }
            }
            else {
                $other = if (Test-Path (Join-Path $dst 'SKILL.md')) { 'an existing skill copy' } else { 'a non-skill directory' }
                $globalIssues += "OCCUPIED: $a/$s (target holds $other; use -Force to replace, or -Link on a clean dir)"
                Write-Output "  OCCUPIED           $s  ($other)"
                continue
            }
        }

        $verb = if ($Link) { 'link' } else { 'copy' }
        if ($DryRun) { Write-Output "  would $verb        $s" }
        else {
            if ($Link) { New-Item -ItemType Junction -Path $dst -Target $src | Out-Null }
            else { Copy-Item -LiteralPath $src -Destination $dst -Recurse -Force }
            Write-Output "  $verb              $s"
        }
    }

    # cross-pack name collision report
    $existing = @()
    if (Test-Path -LiteralPath $target) {
        $existing = Get-ChildItem -LiteralPath $target -Directory -Force | Select-Object -ExpandProperty Name
    }
    $mine = @($install)
    $both = $existing | Where-Object { $mine -contains $_ }
    $foreign = @()
    foreach ($n in $both) {
        $p = Join-Path $target "$n\SKILL.md"
        if (Test-Path -LiteralPath $p) {
            $head = Get-Content -LiteralPath $p -TotalCount 6 -Encoding UTF8 | Out-String
            if ($head -notmatch [regex]::Escape($bundle.name)) { $foreign += $n }
        }
    }

    Write-Output "  verify with: $($entry.verify)"
    Write-Output ''
}

if ($globalIssues.Count -gt 0) {
    Write-Output '--- notes ---'
    $globalIssues | ForEach-Object { Write-Output "  $_" }
}

Write-Output 'Done.'
