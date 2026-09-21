# NB-skills contract/SKILL consistency guard.
#
#   pwsh -NoProfile -File scripts/validate-nb.ps1
#
# The NB variant keeps every rule twice: once as prose in SKILL.md, once as
# metadata in contract.yaml. Nothing enforces that by itself, so this script
# cross-checks the pair and fails on drift:
#   * every skill in bundle.json has NB-skills/<name>/SKILL.md AND contract.yaml
#   * contract id is exactly "NB-skills/<dir>", name matches the directory
#   * required metadata keys are present (risk_level, permissions, ...)
#   * fallback_variant points at an existing agents-skills/<skill>
#   * the L0 surface says what the L2 references say: every "references/x" path
#     named in SKILL.md exists on disk
#   * relative paths mentioned in contract.yaml dependencies.data exist
#   * dependencies.skills names resolve to skills shipped in bundle.json
#
# NOTE: keep this file pure ASCII - Windows PowerShell 5.1 misreads BOM-less UTF-8.
[CmdletBinding()]
param(
    [string]$Root = (Split-Path $PSScriptRoot -Parent)
)

$ErrorActionPreference = 'Stop'
$fail = @()

$nbDir = Join-Path $Root 'NB-skills'
if (-not (Test-Path -LiteralPath $nbDir)) { throw "NB-skills/ not found in $Root" }
$bundle = Get-Content -LiteralPath (Join-Path $Root 'bundle.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$bundleSkills = @($bundle.skills) + @($bundle.optional)

$requiredKeys = @(
    'id', 'name', 'version', 'owner', 'status', 'purpose',
    'when_to_use', 'when_not_to_use', 'required_capabilities', 'recommended_models',
    'fallback_variant', 'dependencies', 'permissions', 'data_scope', 'risk_level',
    'confirmation_required', 'input_contract', 'output_contract', 'constraints',
    'forbidden', 'acceptance_criteria', 'self_check', 'failure_and_escalation',
    'stop_conditions', 'cost_latency_budget', 'examples', 'evaluation',
    'observability', 'review_cycle', 'changelog'
)

function Get-TopKeys([string]$yamlText) {
    $keys = @()
    foreach ($line in ($yamlText -split "`r?`n")) {
        if ($line -match '^([A-Za-z_][A-Za-z0-9_]*):') { $keys += $Matches[1] }
    }
    return $keys
}

foreach ($skill in $bundleSkills) {
    $dir = Join-Path $nbDir $skill
    $id = "NB-skills/$skill"
    if (-not (Test-Path -LiteralPath $dir)) { $fail += "MISSING-DIR: $id"; continue }

    $skillFile = Join-Path $dir 'SKILL.md'
    $contractFile = Join-Path $dir 'contract.yaml'
    if (-not (Test-Path -LiteralPath $skillFile)) { $fail += "MISSING-SKILL.md: $id"; continue }
    if (-not (Test-Path -LiteralPath $contractFile)) { $fail += "MISSING-CONTRACT: $id"; continue }

    $skillRaw = [System.IO.File]::ReadAllText($skillFile)
    $contractRaw = [System.IO.File]::ReadAllText($contractFile)

    # id / name identity
    $idMatch = [regex]::Match($contractRaw, '(?m)^id:\s*"([^"]+)"')
    if (-not $idMatch.Success) { $fail += "NO-ID: $id" }
    elseif ($idMatch.Groups[1].Value -ne $id) { $fail += "ID-MISMATCH: contract id '$($idMatch.Groups[1].Value)' != dir '$id'" }
    $nameMatch = [regex]::Match($contractRaw, '(?m)^name:\s*"([^"]+)"')
    if (-not $nameMatch.Success) { $fail += "NO-CONTRACT-NAME: $id" }
    elseif ($nameMatch.Groups[1].Value -ne $skill) { $fail += "CONTRACT-NAME-MISMATCH: '$($nameMatch.Groups[1].Value)' != '$skill'" }

    # required metadata keys
    $topKeys = Get-TopKeys $contractRaw
    foreach ($k in $requiredKeys) {
        if ($topKeys -notcontains $k) { $fail += "CONTRACT-MISSING-KEY '$k': $id" }
    }

    # fallback_variant must point at an existing agents-skills skill
    $fbMatch = [regex]::Match($contractRaw, '(?m)^fallback_variant:\s*"' + [regex]::Escape($bundle.name) + '/([a-z0-9-]+)')
    if ($fbMatch.Success) {
        $fb = $fbMatch.Groups[1].Value
        if (-not (Test-Path -LiteralPath (Join-Path (Join-Path $Root 'agents-skills') "$fb\SKILL.md"))) {
            $fail += "DANGLING-FALLBACK '$($bundle.name)/$fb': $id"
        }
    }
    else { $fail += "NO-FALLBACK-VARIANT (or unexpected format): $id" }

    # SKILL.md reference paths exist on disk
    foreach ($m in [regex]::Matches($skillRaw, '`((?:references|scripts)/[^`\s]+)`')) {
        $rel = $m.Groups[1].Value
        if (-not (Test-Path -LiteralPath (Join-Path $dir $rel))) { $fail += "BROKEN-SKILL-REF '$rel': $id" }
    }

    # contract dependencies.data relative paths (this-skill files) exist; an
    # entry may hold several paths separated by " / " or ", " (comma parts may
    # omit the directory prefix) and may carry a trailing (annotation)
    foreach ($m in [regex]::Matches($contractRaw, '"((?:references|scripts)/[^"]+?)(?:\s+in this skill)?"')) {
        $entry = $m.Groups[1].Value -replace '\s+in this skill$', ''
        $entry = $entry -replace '\s*\([^)]*\)\s*$', ''
        $baseDir = $null
        foreach ($part in ($entry -split '\s+/\s+|,\s*')) {
            $rel = $part.Trim()
            if (-not $rel) { continue }
            if ($rel -notmatch '/') {
                if ($baseDir) { $rel = "$baseDir/$rel" }
            }
            else { $baseDir = ($rel -split '/')[0] }
            if (-not (Test-Path -LiteralPath (Join-Path $dir $rel))) { $fail += "BROKEN-CONTRACT-DATA-REF '$rel': $id" }
        }
    }

    # dependencies.skills resolve to shipped skills
    $depSection = [regex]::Match($contractRaw, '(?ms)^  skills:\s*\[(.*?)\]')
    if ($depSection.Success) {
        foreach ($dep in ($depSection.Groups[1].Value -split ',')) {
            $dep = $dep.Trim()
            if ($dep -and $bundleSkills -notcontains $dep) { $fail += "UNKNOWN-DEP-SKILL '$dep': $id" }
        }
    }

    # both files parse as clean UTF-8 (no mojibake / replacement chars)
    foreach ($pair in @(@($skillRaw, 'SKILL.md'), @($contractRaw, 'contract.yaml'))) {
        foreach ($c in @([char]0x9225, [char]0x922B, [char]0x922E, [char]0xFFFD)) {
            if ($pair[0].IndexOf($c) -ge 0) { $fail += "MOJIBAKE in $($pair[1]): $id"; break }
        }
    }
}

# ---------- semantic reconciliation: NB variant vs agents-skills source ----------
# The two variants are independent texts carrying the same disciplines; drift is
# inevitable without a mechanical check. These keyword families must appear on
# BOTH sides of a same-named skill pair (case-insensitive substring match; both
# variants may push depth into references/, so each side is body + references).
$ironLawRe = '(?i)IRON LAW'
# Per-skill scope: a rule family is only compared where it is expected to live.
# A skill that never had a rule on either side must not fail just because the
# word happens to appear elsewhere in the pack.
$ruleScope = @{
    'HARD-GATE'     = @('brainstorming')
    'WATCH-IT-FAIL' = @('tdd')
    'NEVER-ABORT'   = @('resolving-merge-conflicts')
    'TYPED-DISCARD' = @('finishing-a-development-branch')
}
$ruleFamilies = @(
    @{ id = 'HARD-GATE';     patterns = @('hard-gate', 'hard gate') },
    @{ id = 'WATCH-IT-FAIL'; patterns = @('watch it fail') },
    @{ id = 'NEVER-ABORT';   patterns = @('never `--abort`', 'never abort', '--abort` under any', 'aborts (target 0)') },
    @{ id = 'TYPED-DISCARD'; patterns = @('discard') }
)

foreach ($skill in $bundleSkills) {
    $nbFile = Join-Path $nbDir "$skill\SKILL.md"
    $srcFile = Join-Path (Join-Path $Root 'agents-skills') "$skill\SKILL.md"
    if (-not (Test-Path -LiteralPath $nbFile) -or -not (Test-Path -LiteralPath $srcFile)) { continue }
    $id = "NB-skills/$skill"
    $nbAll = [System.IO.File]::ReadAllText($nbFile)
    $srcAll = [System.IO.File]::ReadAllText($srcFile)
    $nbRefs = Join-Path $nbDir "$skill\references"
    if (Test-Path -LiteralPath $nbRefs) {
        foreach ($f in Get-ChildItem -LiteralPath $nbRefs -File -Filter *.md) { $nbAll += "`n" + [System.IO.File]::ReadAllText($f.FullName) }
    }
    $srcRefs = Join-Path (Join-Path $Root 'agents-skills') "$skill\references"
    if (Test-Path -LiteralPath $srcRefs) {
        foreach ($f in Get-ChildItem -LiteralPath $srcRefs -File -Filter *.md) { $srcAll += "`n" + [System.IO.File]::ReadAllText($f.FullName) }
    }

    # Iron Law block: must exist on both or neither
    $nbIron = [regex]::Matches($nbAll, $ironLawRe).Count
    $srcIron = [regex]::Matches($srcAll, $ironLawRe).Count
    if (($nbIron -eq 0) -ne ($srcIron -eq 0)) {
        $fail += "IRON-LAW-DRIFT: $id (NB mentions=$nbIron, source mentions=$srcIron)"
    }

    foreach ($fam in $ruleFamilies) {
        if ($ruleScope.ContainsKey($fam.id) -and $ruleScope[$fam.id] -notcontains $skill) { continue }
        $inNb = $false; $inSrc = $false
        foreach ($p in $fam.patterns) {
            if ($nbAll.IndexOf($p, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) { $inNb = $true }
            if ($srcAll.IndexOf($p, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) { $inSrc = $true }
        }
        if ($inNb -ne $inSrc) {
            $where = if ($inNb) { 'only in NB variant' } else { 'only in agents-skills (NB dropped it?)' }
            $fail += "RULE-DRIFT $($fam.id): $id - present $where"
        }
    }

    # automatic drift checks: material that must survive the variant rewrite
    if ($srcAll -match '(?i)rationaliz' -and $nbAll -notmatch '(?i)rationaliz') {
        $fail += "RATIONALE-DRIFT: $id (source carries rationalization material; NB variant dropped it)"
    }
    if ($srcAll -match '(?i)red flag' -and $nbAll -notmatch '(?i)red flag') {
        $fail += "REDFLAG-DRIFT: $id (source carries a red-flag list; NB variant dropped it)"
    }
}


Write-Output "NB-skills consistency check - $($bundleSkills.Count) skill(s)"
if ($fail) {
    $fail | ForEach-Object { Write-Output "FAIL: $_" }
    Write-Output "$($fail.Count) failure(s)"
    exit 1
}
Write-Output 'ALL NB CHECKS PASSED'
exit 0
