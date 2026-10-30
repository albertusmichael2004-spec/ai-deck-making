param([Parameter(ValueFromRemainingArguments=$true)][string[]]$StudioArguments)
$taskRoot = Split-Path -Parent $PSScriptRoot
$previousPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = "$taskRoot\src;$taskRoot\runtime\python_packages"
    $studioPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $studioPython)) { $studioPython = 'python' }
    & $studioPython -m cli.main @StudioArguments
    exit $LASTEXITCODE
} finally {
    $env:PYTHONPATH = $previousPythonPath
}
