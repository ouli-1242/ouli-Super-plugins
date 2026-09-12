# SuperLite maintenance validator
# Static checks for every SKILL.md and plugin manifest. Run before committing any
# skill change:  powershell -NoProfile -ExecutionPolicy Bypass -File scripts/validate.ps1
# Exit code 0 = all checks passed; 1 = failures (listed below).
# NOTE: keep this file pure ASCII - Windows PowerShell 5.1 misreads BOM-less UTF-8.

param([string]$Root = (Split-Path $PSScriptRoot -Parent))

$fail = @()

# Project-side files that skills reference at runtime (in the USER's workspace),
# not files shipped inside the skill directory - never count these as broken refs.
$ProjectSideFiles = @('CONTEXT.md', 'CONTEXT-MAP.md', 'CODING_STANDARDS.md', 'CONTRIBUTING.md', 'README.md', 'AGENTS.md', 'CLAUDE.md')

# Mojibake sequences (UTF-8 em-dash / arrow / >= read as GBK) built from code
# points so this script stays pure ASCII.
$MojibakeChars = @([char]0x9225, [char]0x922B, [char]0x922E)

$manifestSkills = @()
Get-ChildItem (Join-Path $Root 'skills') -Directory | ForEach-Object {
    $skillDir = $_.FullName
    $skill = $_.Name
    $f = Join-Path $skillDir 'SKILL.md'
    if (-not (Test-Path $f)) { $fail += "MISSING SKILL.md: $skill"; return }
    $raw = Get-Content $f -Raw -Encoding UTF8
    $size = (Get-Item $f).Length
    $script:manifestSkills += $skill

    # frontmatter: name matches directory
    if ($raw -notmatch '(?s)^---\s*\r?\nname:\s*(\S+)[^\n]*\r?\n') {
        $fail += "BAD-FRONTMATTER (no name field): $skill"
    } elseif ($Matches[1] -ne $skill) {
        $fail += "NAME-MISMATCH: dir '$skill' vs frontmatter '$($Matches[1])'"
    }

    # description: present, <=1024 chars; auto-triggered skills must carry a
    # "Use when/BEFORE/while" trigger phrase (manual-trigger skills are exempt -
    # their description is human-facing by design).
    $isManual = $raw -match '(?m)^disable-model-invocation:\s*true'
    if ($raw -notmatch '(?s)^---.*?\r?\ndescription:\s*(.+?)\r?\n') {
        $fail += "NO-DESCRIPTION: $skill"
    } else {
        $desc = $Matches[1]
        if (-not $isManual -and $desc -notmatch 'Use (when|BEFORE|while)') {
            $fail += "NO-TRIGGER-PHRASE (want 'Use when/BEFORE/while'): $skill"
        }
        if ($desc.Length -gt 1024) { $fail += "DESCRIPTION-OVER-1024 ($($desc.Length)): $skill" }
    }

    if ($size -gt 8192) { $fail += "OVER-8KB ($size bytes, Codex truncation): $skill" }

    foreach ($c in $MojibakeChars) {
        if ($raw.IndexOf($c) -ge 0) { $fail += "MOJIBAKE (broken UTF-8): $skill"; break }
    }

    # local file references resolve: references/*.md always must exist;
    # bare *.md names must exist in the skill dir unless they are project-side files
    [regex]::Matches($raw, '`((?:references/)?[A-Za-z0-9._-]+\.md)`') | ForEach-Object {
        $rel = $_.Groups[1].Value
        $base = Split-Path $rel -Leaf
        if ($rel -like 'references/*') {
            if (-not (Test-Path (Join-Path $skillDir $rel))) { $fail += "BROKEN-REF: $skill -> $rel" }
        } elseif ($ProjectSideFiles -notcontains $base) {
            if (-not (Test-Path (Join-Path $skillDir $base))) { $fail += "BROKEN-REF: $skill -> $rel" }
        }
    }
}

# --- Claude plugin manifest lists exactly the skill directories ---
$claudeManifest = Join-Path $Root '.claude-plugin\plugin.json'
if (Test-Path $claudeManifest) {
    $json = Get-Content $claudeManifest -Raw -Encoding UTF8 | ConvertFrom-Json
    $listed = @($json.skills | ForEach-Object { ($_ -split '/')[-1] })
    foreach ($s in $manifestSkills) {
        if ($listed -notcontains $s) { $fail += "NOT-IN-CLAUDE-MANIFEST: $s" }
    }
    foreach ($s in $listed) {
        if ($manifestSkills -notcontains $s) { $fail += "MANIFEST-ENTRY-WITHOUT-DIR: $s" }
    }
}

# --- JSON manifests are optional (manual skills-copy model). When present, they must parse and versions agree. ---
$versions = @()
foreach ($m in @('.claude-plugin\plugin.json', '.claude-plugin\marketplace.json', '.codex-plugin\plugin.json', '.cursor-plugin\plugin.json')) {
    $p = Join-Path $Root $m
    if (-not (Test-Path $p)) { continue }
    try {
        $j = Get-Content $p -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($j.version) { $versions += $j.version }
        elseif ($j.plugins -and $j.plugins[0].version) { $versions += $j.plugins[0].version }
    } catch { $fail += "BAD-JSON: $m" }
}
if ($versions.Count -gt 0 -and (@($versions | Select-Object -Unique).Count -gt 1)) {
    $fail += "VERSION-MISMATCH across manifests: $($versions -join ', ')"
}

Write-Output "SuperLite validation - $($manifestSkills.Count) skills checked"
if ($fail) {
    $fail | ForEach-Object { Write-Output "FAIL: $_" }
    Write-Output "$($fail.Count) failure(s)"
    exit 1
} else {
    Write-Output "ALL CHECKS PASSED"
    exit 0
}
