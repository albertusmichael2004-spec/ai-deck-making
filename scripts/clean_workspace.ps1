param([switch]$Apply, [switch]$UsePlan, [string]$TestRun)
$ErrorActionPreference = 'Stop'
$taskRoot = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$planPath = Join-Path $taskRoot 'implementation\CLEANUP_PLAN.json'
if ($TestRun) { $planPath = Join-Path $taskRoot ('runtime\cleanup_' + $TestRun + '.json') }
$plannerArguments = @((Join-Path $PSScriptRoot 'cleanup_inventory.py'), '--output', $planPath)
if ($TestRun) { $plannerArguments += @('--test-run', $TestRun) }
if (-not $UsePlan) {
    & python @plannerArguments
    if ($LASTEXITCODE -ne 0) { throw 'Cleanup inventory failed; nothing removed' }
} elseif ($TestRun) { throw 'Test cleanup always requires a fresh inventory' }
$plan = Get-Content -LiteralPath $planPath -Raw | ConvertFrom-Json
if (-not $Apply) { return }
if ($plan.root -ne $taskRoot) { throw 'Cleanup root mismatch' }
if (([DateTime]::UtcNow - [DateTime]::Parse($plan.created_at).ToUniversalTime()).TotalMinutes -gt 30) { throw 'Cleanup plan expired; generate a fresh inventory' }
$results = @()
$processed = 0
foreach ($target in $plan.removals) {
    $absolute = [System.IO.Path]::GetFullPath((Join-Path $taskRoot $target.path))
    if (-not $absolute.StartsWith($taskRoot + '\', [System.StringComparison]::OrdinalIgnoreCase) -or $absolute -ne $target.absolute_path) { throw 'Unsafe cleanup target' }
    $allowed = $target.path -match '^(runtime/(?!python_packages(?:/|$)|locks(?:/|$))|projects/|implementation/CHECKPOINTS/|\.pytest_cache$)' -or $target.path -match '^(src|scripts|tests|runtime/python_packages)/(?:.*/)?__pycache__$'
    if (-not $allowed) { throw "Unapproved cleanup area: $($target.path)" }
    try {
        if (Test-Path -LiteralPath $absolute) {
            $resolved = (Resolve-Path -LiteralPath $absolute).ProviderPath
            if (-not $resolved.StartsWith($taskRoot + '\', [System.StringComparison]::OrdinalIgnoreCase)) { throw 'Resolved cleanup path outside workspace' }
            if ($target.folders -gt 1000) {
                # Avoid provider overhead for huge, previously inspected test trees.
                try { [System.IO.Directory]::Delete(('\\?\' + $absolute), $true) }
                catch { Remove-Item -LiteralPath ('\\?\' + $absolute) -Recurse -Force }
            } else {
                Remove-Item -LiteralPath ('\\?\' + $absolute) -Recurse -Force
            }
        }
        $results += [pscustomobject]@{ path = $target.path; removed = $true; files = $target.files; folders = $target.folders; bytes = $target.bytes }
    } catch {
        $results += [pscustomobject]@{ path = $target.path; removed = $false; error = $_.Exception.Message }
    }
    $processed++
    if ($processed % 25 -eq 0) { Write-Output "Cleanup progress: $processed/$($plan.removals.Count) targets." }
}
$report = [pscustomobject]@{ completed_at = [DateTime]::UtcNow.ToString('o'); root = $taskRoot; results = $results; protected = $plan.protected }
$reportPath = Join-Path $taskRoot 'implementation\CLEANUP_REPORT.json'
if ($TestRun) {
    # The main audit persists bulk cleanup; successful test cleanup is disposable.
    Remove-Item -LiteralPath $planPath -Force
} else {
    $history = @()
    if (Test-Path -LiteralPath $reportPath) {
        $previous = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json
        if ($previous.runs) { $history = @($previous.runs) } else { $history = @($previous) }
    }
    $history += $report
    [pscustomobject]@{ schema_version = '1.0'; runs = $history } | ConvertTo-Json -Depth 25 | Set-Content -LiteralPath $reportPath -Encoding utf8
}
$failed = @($results | Where-Object { -not $_.removed })
Write-Output "Removed $(@($results | Where-Object removed).Count) targets; failed $($failed.Count)."
if ($failed.Count) { throw 'Some cleanup targets could not be removed; see cleanup report' }
