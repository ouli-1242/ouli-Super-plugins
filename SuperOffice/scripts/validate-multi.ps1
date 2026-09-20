# Multi-harness conformance validator for one skill pack.
#
#   pwsh -NoProfile -File scripts/validate-multi.ps1                 # canonical agents-skills/
#   pwsh -NoProfile -File scripts/validate-multi.ps1 -AllTargets     # + zcode-skills / codex-skills
#   pwsh -NoProfile -File scripts/validate-multi.ps1 -Target zcode-skills
#
# Enforces what every SKILL.md-reading harness needs together:
#   * frontmatter parses under strict YAML (an unquoted ": " drops the whole skill)
#   * exactly two keys: name + description (Claude Code rejects any other key)
#   * name is kebab-case, equals its directory name, and is unique in the pack
#   * description <= MaxDescription (1024 = the tightest published vendor cap)
#   * description carries a Chinese trigger anchor (the primary user language)
#   * a generated ZCode folder keeps its whole description, and a Chinese anchor,
#     inside ZCode's 250-char per-turn metadata window
#   * exactly one H1, no BOM, no over-size SKILL.md
#   * cross-pack name clashes are reported; only UNDECLARED ones fail
#
# NOTE: keep this file pure ASCII - Windows PowerShell 5.1 misreads BOM-less UTF-8.
[CmdletBinding()]
param(
    [string]$Root = (Split-Path $PSScriptRoot -Parent),
    [string]$Target = 'agents-skills',
    [switch]$AllTargets,
    [int]$MaxDescription = 1024,
    [int]$MaxSkillBytes = 8192,
    [int]$DescriptionWindow = 250,
    [switch]$Strict
)

$ErrorActionPreference = 'Stop'
$fail = @()
$checked = 0

$bundleFile = Join-Path $Root 'bundle.json'
if (-not (Test-Path -LiteralPath $bundleFile)) { throw "bundle.json not found in $Root" }
$bundle = Get-Content -LiteralPath $bundleFile -Raw -Encoding UTF8 | ConvertFrom-Json
$skillNames = @($bundle.skills) + @($bundle.optional)
$packName = Split-Path $Root -Leaf

function Test-Frontmatter([string]$Raw) {
    if ($Raw -notmatch '(?s)^---\r?\n(.*?)\r?\n---(\r?\n|$)') {
        return 'NO-FRONTMATTER (or unclosed frontmatter block)'
    }
    $fm = $Matches[1]
    $keys = @()
    $cur = $null
    foreach ($line in ($fm -split "\r?\n")) {
        if ($line -match '^([A-Za-z][A-Za-z0-9_-]*)\s*:') {
            $cur = $Matches[1]
            $keys += $cur
            $value = $line.Substring($line.IndexOf(':') + 1).Trim()
            if ($cur -eq 'description') {
                if ($value -notmatch '^".*"$') {
                    if ($value -match ': ') { return 'UNQUOTED-COLON-SPACE-IN-DESCRIPTION (quote the value)' }
                    if ($value -match ' #') { return 'UNQUOTED-HASH-IN-DESCRIPTION (quote the value)' }
                }
                else {
                    $inner = $value.Substring(1, $value.Length - 2)
                    if ($inner -match '(?<!\\)"') { return 'UNESCAPED-QUOTE-IN-DESCRIPTION' }
                    if ($inner -match '\\$') { return 'TRAILING-BACKSLASH-ESCAPES-CLOSING-QUOTE' }
                }
            }
        }
        elseif ($cur -and $line -match '^\s+\S') {
            return 'MULTI-LINE-FRONTMATTER-VALUE (keep every value on one line)'
        }
    }
    foreach ($k in $keys) { if ($k -ne 'name' -and $k -ne 'description') { return "EXTRA-FRONTMATTER-KEY '$k' (Claude Code rejects unknown keys)" } }
    return $null
}

# ---------- targets ----------
$folders = if ($AllTargets) {
    @('agents-skills', 'zcode-skills', 'codex-skills') | Where-Object { Test-Path -LiteralPath (Join-Path $Root $_) }
}
else { @($Target) }

# ---------- sibling packs (collision detection) ----------
$siblingNames = @{}
$declaredConflicts = @{}
$siblingRoot = Split-Path $Root -Parent
foreach ($sib in Get-ChildItem -LiteralPath $siblingRoot -Directory) {
    if ($sib.Name -eq $packName) { continue }
    $f = Join-Path $sib.FullName 'bundle.json'
    if (-not (Test-Path -LiteralPath $f)) { continue }
    try { $b = Get-Content -LiteralPath $f -Raw -Encoding UTF8 | ConvertFrom-Json } catch { continue }
    foreach ($n in (@($b.skills) + @($b.optional))) { if (-not $siblingNames.ContainsKey($n)) { $siblingNames[$n] = $sib.Name } }
    foreach ($c in @($b.conflictsWith)) { if ($c) { $declaredConflicts[$sib.Name] = $true } }
}
foreach ($c in @($bundle.conflictsWith)) { if ($c) { $declaredConflicts[$c] = $true } }

$notes = @()

foreach ($folder in $folders) {
    $dir = Join-Path $Root $folder
    if (-not (Test-Path -LiteralPath $dir)) { continue }
    $windowed = $folder -like '*zcode*'
    $id0 = if ($folder -eq 'agents-skills') { $packName } else { "$packName/$folder" }
    $seen = @{}

    foreach ($skillDir in Get-ChildItem -LiteralPath $dir -Directory) {
        $checked++
        $id = "$id0/$($skillDir.Name)"
        $file = Join-Path $skillDir.FullName 'SKILL.md'
        if (-not (Test-Path -LiteralPath $file)) { $fail += "MISSING-SKILL.md: $id"; continue }

        $bytes = [System.IO.File]::ReadAllBytes($file)
        if ($bytes.Length -gt 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) { $fail += "BOM: $id" }
        if ($bytes.Length -gt $MaxSkillBytes) { $fail += "OVER-SKILL-BYTES ($($bytes.Length) > $MaxSkillBytes): $id" }
        $raw = [System.IO.File]::ReadAllText($file)

        # mojibake signatures (UTF-8 read as GBK/CP936) plus the replacement char
        foreach ($c in @([char]0x9225, [char]0x922B, [char]0x922E, [char]0xFFFD)) {
            if ($raw.IndexOf($c) -ge 0) { $fail += "MOJIBAKE (broken UTF-8): $id"; break }
        }

        $err = Test-Frontmatter -Raw $raw
        if ($err) { $fail += "$err : $id" }

        $nameMatch = [regex]::Match($raw, '(?m)^name\s*:\s*(\S+)\s*$')
        if (-not $nameMatch.Success) { $fail += "NO-NAME: $id" }
        else {
            $nm = $nameMatch.Groups[1].Value
            if ($nm -ne $skillDir.Name) { $fail += "NAME-MISMATCH: dir '$($skillDir.Name)' vs frontmatter '$nm'" }
            if ($nm -notmatch '^[a-z0-9]+(?:-[a-z0-9]+)*$') { $fail += "BAD-NAME-GRAMMAR (kebab-case only): $id" }
            if ($nm.Length -gt 64) { $fail += "NAME-OVER-64 ($($nm.Length)): $id" }
            if ($nm -match '--') { $fail += "NAME-DOUBLE-HYPHEN: $id" }
            if ($seen.ContainsKey($nm)) { $fail += "DUPLICATE-SKILL-NAME: $id collides with $($seen[$nm])" }
            elseif ($siblingNames.ContainsKey($nm)) {
                $other = $siblingNames[$nm]
                if ($declaredConflicts.ContainsKey($other)) {
                    $notes += "$nm exists in both $packName and $other - declared in conflictsWith; install one, not both"
                }
                else { $fail += "CROSS-PACK-NAME-COLLISION: $id also exists in pack '$other' (never install both into one skills dir)" }
            }
            $seen[$nm] = $id
        }

        $descMatch = [regex]::Match($raw, '(?m)^description\s*:\s*"(.*)"\s*$')
        if ($descMatch.Success) {
            $norm = (($descMatch.Groups[1].Value -replace '\\"', '"') -replace '\s+', ' ').Trim()
            if ($norm.Length -gt $MaxDescription) { $fail += "DESCRIPTION-TOO-LONG ($($norm.Length) > $MaxDescription): $id" }
            if ($norm -notmatch '[\u4e00-\u9fff]') { $fail += "NO-CHINESE-TRIGGER: $id" }
            if ($norm -notmatch '(?i)use (when|before|while)') { $fail += "NO-TRIGGER-PHRASE ('Use when/BEFORE/while'): $id" }
            if ($windowed) {
                if ($norm.Length -gt $DescriptionWindow) { $fail += "OVER-DESCRIPTION-WINDOW ($($norm.Length) > $DescriptionWindow): $id" }
                $head = $norm.Substring(0, [Math]::Min($DescriptionWindow, $norm.Length))
                if ($head -notmatch '[\u4e00-\u9fff]') { $fail += "NO-CHINESE-IN-FIRST-${DescriptionWindow}: $id" }
            }
        }

        # DSH-specific: its model-facing catalog truncates every description at
        # catalogDescriptionMaxLength (default 500, keeping 497 + "..."), so a
        # longer description loses its tail on that harness - report, do not fail.
        if ($descMatch.Success -and $norm.Length -gt 500) {
            $notes += "DSH-TRUNCATED $($norm.Length) chars: $id (DSH catalog keeps the first 497)"
        }

        $h1 = ([regex]::Matches($raw, '(?m)^# ')).Count
        if ($h1 -ne 1) { $fail += "H1-COUNT=$h1 (want exactly 1): $id" }

        foreach ($m in [regex]::Matches($raw, '(?i)skill tool[^"]{0,60}"([a-z][a-z0-9-]+)"')) {
            $ref = $m.Groups[1].Value
            if (-not (Test-Path -LiteralPath (Join-Path (Join-Path $Root 'agents-skills') $ref))) {
                $fail += "DANGLING-SKILL-REF '$ref': $id"
            }
        }

        if ($Strict) {
            $projectSide = @('技术依据.md', '决策记录.md', '规范.md', '运行.md', '测试.md', '文档导航.md', 'README.md', 'AGENTS.md', 'CLAUDE.md', 'CONTRIBUTING.md')
            foreach ($m in [regex]::Matches($raw, '`([^`\s]+\.md)`')) {
                $rel = $m.Groups[1].Value
                if ($projectSide -contains (Split-Path $rel -Leaf)) { continue }
                if (-not (Test-Path -LiteralPath (Join-Path $skillDir.FullName $rel))) { $fail += "BROKEN-REF '$rel': $id" }
            }
        }
    }

    # every shipped resource file must still parse as UTF-8 text and stay small
    foreach ($f in Get-ChildItem -LiteralPath $dir -Recurse -File) {
        if ($f.Extension -notin @('.md', '.txt', '.yaml', '.yml')) { continue }
        $text = [System.IO.File]::ReadAllText($f.FullName)
        foreach ($c in @([char]0x9225, [char]0x922B, [char]0x922E, [char]0xFFFD)) {
            if ($text.IndexOf($c) -ge 0) { $fail += "MOJIBAKE (broken UTF-8) in $($f.Name): $id0/$($f.Directory.Name)"; break }
        }
    }
}

$notes | Sort-Object -Unique | ForEach-Object { Write-Output "note: $_" }
Write-Output "Multi-harness validation - $checked skill(s) in $($folders.Count) folder(s) of $packName; description cap $MaxDescription"
if ($fail) {
    $fail | ForEach-Object { Write-Output "FAIL: $_" }
    Write-Output "$($fail.Count) failure(s)"
    exit 1
}
Write-Output 'ALL CHECKS PASSED'
exit 0
