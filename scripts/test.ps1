param([switch]$KeepArtifacts, [Parameter(ValueFromRemainingArguments=$true)][string[]]$TestArguments)
$taskRoot = Split-Path -Parent $PSScriptRoot
$testRunPath = Join-Path $taskRoot ('runtime\pytest\' + [guid]::NewGuid().ToString('N'))
if (-not $testRunPath.StartsWith($taskRoot + '\', [System.StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe test directory' }
[System.IO.Directory]::CreateDirectory((Split-Path -Parent $testRunPath)) | Out-Null
Push-Location -LiteralPath $taskRoot
try {
    python -m pytest --basetemp $testRunPath @TestArguments
    $testExitCode = $LASTEXITCODE
    if ($testExitCode -eq 0 -and -not $KeepArtifacts) {
        & (Join-Path $PSScriptRoot 'clean_workspace.ps1') -Apply -TestRun (Split-Path -Leaf $testRunPath)
    }
    exit $testExitCode
} finally {
    Pop-Location
}
