# Commit + push ONLY if the privacy check is clean (CLAUDE.md rule 5). Created after a slip on 2026-11-17: a commit
# went out although the check printed matches, because the old one-line command did not stop on them.
#   powershell -ExecutionPolicy Bypass -File tools\dev\commit_checked.ps1 -MessageFile <file> [-NoPush]
param([Parameter(Mandatory = $true)][string]$MessageFile, [switch]$NoPush)
Set-Location (Join-Path $PSScriptRoot "..\..")
git add -A
$leaks = git grep --cached -i -n -e surya -e gmail | Select-String -NotMatch 'suryateja963'
if ($leaks) {
    Write-Output "PRIVACY CHECK FAILED - nothing committed:"
    $leaks | ForEach-Object { Write-Output $_.Line }
    exit 1
}
git commit -q -F $MessageFile
if (-not $?) { Write-Output "commit failed"; exit 1 }
if (-not $NoPush) {
    git push -q origin main
    if (-not $?) { Write-Output "push failed"; exit 1 }
}
git log --oneline -1
