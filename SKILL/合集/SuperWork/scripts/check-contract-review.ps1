# Report NB-skills contracts whose review_cycle has elapsed since the last
# changelog entry. review_cycle is currently dead metadata; this makes it live.
#
#   pwsh -NoProfile -File scripts/check-contract-review.ps1            # report
#   pwsh -NoProfile -File scripts/check-contract-review.ps1 -FailOnDue  # exit 1 if any due
#
# "Last reviewed" = the date of the NEWEST changelog entry in contract.yaml.
# A contract with no dated changelog entry is always due.
#
# NOTE: keep this file pure ASCII - Windows PowerShell 5.1 misreads BOM-less UTF-8.
[CmdletBinding()]
param(
    [string]$Root = (Split-Path $PSScriptRoot -Parent),
    [switch]$FailOnDue
)

$ErrorActionPreference = 'Stop'
$nbDir = Join-Path $Root 'NB-skills'
if (-not (Test-Path -LiteralPath $nbDir)) { throw "NB-skills/ not found in $Root" }

$today = Get-Date -Format 'yyyy-MM-dd'
$due = @()
$rows = @()

foreach ($dir in (Get-ChildItem -LiteralPath $nbDir -Directory)) {
    $cf = Join-Path $dir.FullName 'contract.yaml'
    if (-not (Test-Path -LiteralPath $cf)) { continue }
    $raw = Get-Content -LiteralPath $cf -Raw -Encoding UTF8

    $cycleDays = 90
    $cycleMatch = [regex]::Match($raw, '(?m)^review_cycle:\s*"?(\d+)\s*days"?')
    if ($cycleMatch.Success) { $cycleDays = [int]$cycleMatch.Groups[1].Value }

    $dates = @([regex]::Matches($raw, '\((\d{4})-(\d{2})-(\d{2})\)') |
        ForEach-Object { $_.Groups[1].Value + '-' + $_.Groups[2].Value + '-' + $_.Groups[3].Value } | Sort-Object -Descending)
    $last = if ($dates) { [datetime]$dates[0] } else { $null }

    $dueDate = if ($last) { $last.AddDays($cycleDays) } else { $null }
    $isDue = (-not $last) -or ($dueDate -lt (Get-Date).Date)
    $rows += [pscustomobject]@{
        skill     = $dir.Name
        cycleDays = $cycleDays
        last      = if ($last) { $dates[0] } else { '(no dated changelog)' }
        dueBy     = if ($dueDate) { $dueDate.ToString('yyyy-MM-dd') } else { 'now' }
        status    = if ($isDue) { 'DUE' } else { 'ok' }
    }
    if ($isDue) { $due += $dir.Name }
}

$rows | Sort-Object status, dueBy | Format-Table -AutoSize | Out-String | Write-Output
Write-Output "today: $today; due: $($due.Count)/$($rows.Count)"
if ($due.Count -gt 0) {
    Write-Output "review due: $($due -join ', ')"
    if ($FailOnDue) { exit 1 }
}
exit 0
