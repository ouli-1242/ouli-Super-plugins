# Human-in-the-loop reproduction loop (PowerShell, Windows).
# Copy this file, edit the steps below, and run it.
# The agent runs the script; the user follows prompts in their terminal.
#
# Usage:
#   .\hitl-loop.ps1
#
# Two helpers:
#   step "<instruction>"          -> show instruction, wait for Enter
#   capture VAR "<question>"      -> show question, read response into VAR
#
# At the end, captured values are printed as KEY=VALUE for the agent to parse.
#
# `capture` prints its value back to the terminal, where the agent reads it — so
# capture observations, and leave signing in to the user as a `step`.

function step([string]$Instruction) {
  Write-Host "`n>>> $Instruction"
  Read-Host "    [Enter when done]"
}

function capture([string]$VarName, [string]$Question) {
  Write-Host "`n>>> $Question"
  $answer = Read-Host "    > "
  Set-Variable -Name $VarName -Value $answer -Scope Script
  return $answer
}

# --- edit below ---------------------------------------------------------

step "Open the app at http://localhost:3000 and sign in."

$script:ERRORED = capture 'ERRORED' "Click the 'Export' button. Did it throw an error? (y/n)"

$script:ERROR_MSG = capture 'ERROR_MSG' "Paste the error message (or 'none'):"

# --- edit above ---------------------------------------------------------

Write-Host "`n--- Captured ---"
Write-Host "ERRORED=$($script:ERRORED)"
Write-Host "ERROR_MSG=$($script:ERROR_MSG)"