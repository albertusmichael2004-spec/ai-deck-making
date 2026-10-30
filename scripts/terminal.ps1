# Explicitly restore the project after shell startup (paths may contain brackets).
$studioRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $studioRoot
$env:PYTHONUTF8 = '1'
$studioPaths = @("$studioRoot\src", "$studioRoot\runtime\python_packages")
if ($env:PYTHONPATH) { $studioPaths += $env:PYTHONPATH }
$env:PYTHONPATH = $studioPaths -join [IO.Path]::PathSeparator
$studioActivate = Join-Path $studioRoot '.venv\Scripts\Activate.ps1'
if (Test-Path -LiteralPath $studioActivate) { . $studioActivate }
