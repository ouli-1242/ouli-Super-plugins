# Normalize SKILL.md files in this pack's canonical agents-skills/ folder:
#   frontmatter : `description` must be a single-line YAML double-quoted scalar
#                 (an unquoted value containing ": " makes strict YAML parsers drop
#                 the whole skill). Rewritten ONLY when it is not already canonical,
#                 so descriptions.json stays the source of truth for the text.
#   body        : exactly one H1 (added from the skill name when missing,
#                 duplicates after the first H1 demoted to H2)
#   encoding    : UTF-8 without BOM, the file's own LF/CRLF preserved
#
#   pwsh -NoProfile -File scripts/normalize-skills.ps1 -AuditOnly   # report only
#   pwsh -NoProfile -File scripts/normalize-skills.ps1              # write
#
# Idempotent: a second run reports 0 changes.
# NOTE: keep this file pure ASCII - Windows PowerShell 5.1 misreads BOM-less UTF-8.
[CmdletBinding()]
param(
    [string]$Root = (Split-Path $PSScriptRoot -Parent),
    [switch]$AuditOnly
)

$ErrorActionPreference = 'Stop'
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$skillsDir = Join-Path $Root 'agents-skills'
if (-not (Test-Path -LiteralPath $skillsDir)) { throw "agents-skills/ not found in $Root" }

$changes = @()

foreach ($skillDir in Get-ChildItem -LiteralPath $skillsDir -Directory) {
    $file = Join-Path $skillDir.FullName 'SKILL.md'
    if (-not (Test-Path -LiteralPath $file)) { continue }

    $raw = [System.IO.File]::ReadAllText($file)
    $eol = if ($raw -match "`r`n") { "`r`n" } else { "`n" }
    $lines = [System.Collections.Generic.List[string]]::new()
    foreach ($l in ($raw -split "\r?\n")) { $lines.Add($l) }

    # ---------- frontmatter: exactly one `---` block at the top ----------
    if ($lines.Count -lt 3 -or $lines[0] -ne '---') { $changes += "SKIP (no frontmatter): $($skillDir.Name)"; continue }
    $fmEnd = -1
    for ($i = 1; $i -lt $lines.Count; $i++) { if ($lines[$i] -eq '---') { $fmEnd = $i; break } }
    if ($fmEnd -lt 0) { $changes += "SKIP (unclosed frontmatter): $($skillDir.Name)"; continue }

    $descIndex = -1
    for ($i = 1; $i -lt $fmEnd; $i++) { if ($lines[$i] -match '^description\s*:') { $descIndex = $i; break } }
    if ($descIndex -lt 0) { $changes += "SKIP (no description): $($skillDir.Name)"; continue }

    # the value may be folded over several lines: join, then re-quote
    $end = $descIndex + 1
    while ($end -lt $fmEnd -and $lines[$end] -notmatch '^[A-Za-z][A-Za-z0-9_-]*\s*:') { $end++ }

    $parts = @(($lines[$descIndex] -replace '^description\s*:\s*', ''))
    for ($j = $descIndex + 1; $j -lt $end; $j++) { $parts += $lines[$j] }

    $value = ($parts -join ' ').Trim()
    $value = $value -replace '\\"', '"'          # unescape before stripping quotes
    $value = $value -replace '^"(.*)"$', '$1'
    $value = ($value -replace '\s+', ' ').Trim()
    $escaped = $value -replace '\\', '\\'        # escape backslashes first
    $escaped = $escaped -replace '"', '\"'       # then double quotes
    $canonical = 'description: "' + $escaped + '"'

    if ($end - $descIndex -ne 1 -or $lines[$descIndex] -ne $canonical) {
        $lines.RemoveRange($descIndex, $end - $descIndex)
        $lines.Insert($descIndex, $canonical)
        $changes += "REQUOTED   $($skillDir.Name)  desc=$($value.Length)"
    }

    # ---------- exactly one H1 ----------
    $h1 = @()
    for ($i = $fmEnd + 1; $i -lt $lines.Count; $i++) { if ($lines[$i] -match '^# ') { $h1 += $i } }

    if ($h1.Count -eq 0) {
        $insertAt = $fmEnd + 1
        while ($insertAt -lt $lines.Count -and $lines[$insertAt].Trim() -eq '') { $insertAt++ }
        $title = '# ' + (($skillDir.Name -split '-') | ForEach-Object {
                if ($_.Length -gt 0) { $_.Substring(0, 1).ToUpper() + $_.Substring(1) } else { $_ }
            }) -join ' '
        $lines.Insert($insertAt, $title)
        $lines.Insert($insertAt + 1, '')
        $changes += "H1-ADDED   $($skillDir.Name) -> $title"
    }
    elseif ($h1.Count -gt 1) {
        for ($n = 1; $n -lt $h1.Count; $n++) { $lines[$h1[$n]] = '## ' + $lines[$h1[$n]].Substring(2) }
        $changes += "H1-DEMOTED $($skillDir.Name) ($($h1.Count) -> 1)"
    }

    $final = ($lines -join $eol)
    if (-not $final.EndsWith($eol)) { $final += $eol }
    if ($final -ne $raw -and -not $AuditOnly) { [System.IO.File]::WriteAllText($file, $final, $utf8NoBom) }
}

$changes | ForEach-Object { Write-Output $_ }
$n = ($changes | Where-Object { $_ -like 'REQUOTED*' -or $_ -like 'H1-*' }).Count
Write-Output "--- $n file(s) $(if ($AuditOnly) { 'would change' } else { 'changed' }) in $(Split-Path $Root -Leaf)/agents-skills"
