param([switch]$SkipCheckpoint)
$ErrorActionPreference = 'Stop'
$workspaceRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$runtimeRoot = Join-Path $workspaceRoot 'runtime'
$ownedNames = @('cleanup_verification_20261024','cleanup_verification_final_20261024','cleanup_verification_privileged_20261024')
foreach ($name in $ownedNames) {
    $target = [IO.Path]::GetFullPath((Join-Path $runtimeRoot $name))
    if ([IO.Path]::GetDirectoryName($target) -ne $runtimeRoot -or -not $name.StartsWith('cleanup_verification')) { throw 'Unexpected verification folder' }
    if (-not (Test-Path -LiteralPath $target)) { continue }
    if ($null -ne ([IO.DirectoryInfo]::new($target)).LinkTarget) { throw 'Verification root is a link' }
    $linkReport = Join-Path $workspaceRoot ('implementation/PHASE_REPORTS/' + $name + '_links.json')
    & (Join-Path $workspaceRoot '.venv/Scripts/python.exe') (Join-Path $PSScriptRoot 'find_cleanup_links.py') --root $target --report $linkReport
    if ($LASTEXITCODE -ne 0) { throw 'Verification link inventory failed' }
    foreach ($link in (Get-Content -LiteralPath $linkReport -Raw | ConvertFrom-Json).links) {
        $linkPath = [IO.Path]::GetFullPath([string]$link.path)
        if (-not $linkPath.StartsWith($target + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Link outside verification root' }
        if ($link.directory) { ([IO.DirectoryInfo]::new($linkPath)).Delete() }
        else { [IO.File]::Delete($linkPath) }
    }
    Remove-Item -LiteralPath $target -Recurse -Force
}
if (-not $SkipCheckpoint) {
    $env:PYTHONPATH = Join-Path $workspaceRoot 'src'
    & (Join-Path $workspaceRoot '.venv/Scripts/python.exe') (Join-Path $workspaceRoot 'scripts/checkpoint_workspace_cleanup.py')
    if ($LASTEXITCODE -ne 0) { throw 'Cleanup verification/checkpoint failed' }
}
