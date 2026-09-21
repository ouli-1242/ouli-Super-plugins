# Audit a project's docs/ against its doc-index contract.
#
#   pwsh -NoProfile -File scripts/audit-docs.ps1 -ProjectRoot C:\path\to\project
#
# The doc-index skill declares "not done until on disk AND registered" with
# metrics targeting zero unregistered artifacts and zero stale registrations.
# This script makes those metrics executable:
#   * every .md in a known type dir must have a registration row in the index
#   * every registered path must exist on disk
#   * index-required structure present (当前进度 / 活跃入口 sections)
#
# Known type dirs and naming conventions come from shared/disciplines.yaml
# (single source). Type dirs listed there but absent on disk are fine.
#
# NOTE: keep this file pure ASCII - Windows PowerShell 5.1 misreads BOM-less UTF-8.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot,
    [string]$PackRoot = (Split-Path $PSScriptRoot -Parent)
)

$ErrorActionPreference = 'Stop'
$fail = @()
$warn = @()

$docsDir = Join-Path $ProjectRoot 'docs'
if (-not (Test-Path -LiteralPath $docsDir)) {
    Write-Output "No docs/ at $ProjectRoot - nothing to audit (doc-index not applicable)."
    exit 0
}

# ---------- load conventions from the single source ----------
$discFile = Join-Path $PackRoot 'shared\disciplines.yaml'
if (-not (Test-Path -LiteralPath $discFile)) { throw "shared/disciplines.yaml not found in $PackRoot" }
$disc = Get-Content -LiteralPath $discFile -Raw -Encoding UTF8

$typeDirs = @()
$inTypes = $false
foreach ($line in ($disc -split "`r?`n")) {
    if ($line -match '^artifact_types:') { $inTypes = $true; continue }
    if ($inTypes -and $line -match '^\S') { $inTypes = $false }
    if ($inTypes -and $line -match '^\s{2}(\S+):') { $typeDirs += $Matches[1] }
}
$rootDocsMatch = [regex]::Match($disc, '(?m)^root_docs:\s*\[(.*?)\]')
$rootDocs = @()
if ($rootDocsMatch.Success) { $rootDocs = @($rootDocsMatch.Groups[1].Value -split ',' | ForEach-Object { $_.Trim() }) }
$facadeMatch = [regex]::Match($disc, '(?m)^index_facade:\s*"([^"]+)"')
$indexRel = if ($facadeMatch.Success) { $facadeMatch.Groups[1].Value } else { 'docs/文档导航.md' }
$indexFile = Join-Path $ProjectRoot ($indexRel -replace '/', '\')

if ($typeDirs.Count -eq 0) { throw "no artifact_types parsed from $discFile" }

# ---------- index presence and structure ----------
$indexText = ''
$requiredSections = @()
$secMatch = [regex]::Match($disc, '(?m)^index_sections:\s*\[(.*?)\]')
if ($secMatch.Success) {
    $requiredSections = @($secMatch.Groups[1].Value -split ',' | ForEach-Object { $_.Trim().Trim('"') } | Where-Object { $_ })
}
if (-not (Test-Path -LiteralPath $indexFile)) {
    $fail += "INDEX-MISSING: $indexRel (docs/ exists but the facade does not)"
}
else {
    $indexText = [System.IO.File]::ReadAllText($indexFile)
    foreach ($section in $requiredSections) {
        if ($indexText.IndexOf($section) -lt 0) { $warn += "INDEX-SECTION-MISSING: '$section' not found in $indexRel" }
    }
}

# ---------- files on disk -> registered? ----------
$unregistered = 0
foreach ($typeDir in $typeDirs) {
    $dir = Join-Path $docsDir $typeDir
    if (-not (Test-Path -LiteralPath $dir)) { continue }
    foreach ($f in Get-ChildItem -LiteralPath $dir -File -Filter *.md) {
        if ($f.FullName -eq $indexFile) { continue }   # the facade is not its own artifact
        $rel = "docs/$typeDir/$($f.Name)"
        if ($indexText -and $indexText.IndexOf($f.Name) -lt 0) {
            $fail += "UNREGISTERED: $rel (on disk, no row in $indexRel)"
            $unregistered++
        }
    }
}

# ---------- registered paths -> exist? ----------
if ($indexText) {
    foreach ($m in [regex]::Matches($indexText, 'docs/[A-Za-z0-9_一-鿿/\-]+\.md')) {
        $p = Join-Path $ProjectRoot ($m.Value -replace '/', '\')
        if (-not (Test-Path -LiteralPath $p)) { $fail += "STALE-REGISTRATION: $($m.Value) (registered, not on disk)" }
    }
}

# ---------- root docs sanity (warn only: projects adopt their own layout) ----------
foreach ($rd in $rootDocs) {
    $p = Join-Path $docsDir $rd
    if (-not (Test-Path -LiteralPath $p)) { $warn += "ROOT-DOC-ABSENT: docs/$rd (declared default; fine if the index declares an override)" }
}

Write-Output "doc-index audit - $ProjectRoot"
Write-Output "  index: $indexRel $(if (Test-Path -LiteralPath $indexFile) { '(present)' } else { '(MISSING)' })"
foreach ($w in ($warn | Sort-Object -Unique)) { Write-Output "note: $w" }
if ($fail) {
    $fail | Sort-Object -Unique | ForEach-Object { Write-Output "FAIL: $_" }
    Write-Output "$($fail.Count) failure(s)"
    exit 1
}
Write-Output 'AUDIT PASSED'
exit 0
