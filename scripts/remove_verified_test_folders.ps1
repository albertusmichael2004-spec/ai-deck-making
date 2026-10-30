$ErrorActionPreference = 'Stop'
$workspaceRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$projectsRoot = [IO.Path]::GetFullPath((Join-Path $workspaceRoot 'projects'))
$pytestRoot = [IO.Path]::GetFullPath((Join-Path $workspaceRoot 'runtime/pytest'))
$reportPath = Join-Path $workspaceRoot 'implementation/PHASE_REPORTS/workspace_cleanup_20261024.json'
$report = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json
if ($report.status -ne 'archive_verified_ready_for_cleanup') { throw 'A verified archive is required' }
$archive = Get-Item -LiteralPath $report.archive
if (-not $archive.FullName.StartsWith($workspaceRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Archive outside workspace' }
if ((Get-FileHash -LiteralPath $archive.FullName -Algorithm SHA256).Hash.ToLowerInvariant() -ne $report.archive_sha256) { throw 'Archive checksum changed' }
$activePath = Join-Path $projectsRoot '.active_project.json'
$activeHash = (Get-FileHash -LiteralPath $activePath -Algorithm SHA256).Hash
$targets = @()
foreach ($name in $report.fixtures) {
    if ($name -notmatch '^(bench|chart-boundaries|consulting-e2e|critic-native|critic-smoke|exhibits|incremental-native|live-comments|live-native|live-probe|live-table|qa-smoke|reason-smoke|research-design|release-manufacturing|release-retail|release-financial_services)-[0-9a-f]{8,12}$') { throw "Invalid fixture identity: $name" }
    $target = [IO.Path]::GetFullPath((Join-Path $projectsRoot $name))
    if ([IO.Path]::GetDirectoryName($target) -ne $projectsRoot) { throw 'Fixture escaped projects' }
    if (Test-Path -LiteralPath (Join-Path $target 'state/workspace.json')) { throw "Registered user project: $target" }
    if (Test-Path -LiteralPath $target) {
        $item = Get-Item -LiteralPath $target -Force
        if ($item.LinkType -in @('Junction','SymbolicLink')) { throw "Linked fixture root: $target" }
    }
    $targets += $target
}
# Recheck original bytes against the verified archive before any removal.
foreach ($record in $report.files) {
    $source = [IO.Path]::GetFullPath((Join-Path $workspaceRoot $record.path))
    if (-not $source.StartsWith($projectsRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Archive member escaped projects' }
    $fixtureName = $source.Substring($projectsRoot.Length + 1).Split('\')[0]
    if ($fixtureName -notin $report.fixtures) { throw 'Unselected source file' }
    if ((Test-Path -LiteralPath $source) -and (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant() -ne $record.sha256) { throw "Changed fixture: $source" }
}
if ([IO.Path]::GetFullPath([string]$report.pytest_target) -ne $pytestRoot) { throw 'Unexpected pytest target' }
if (Test-Path -LiteralPath $pytestRoot) {
    $pytestItem = Get-Item -LiteralPath $pytestRoot -Force
    if ($pytestItem.LinkType -in @('Junction','SymbolicLink')) { throw 'Linked pytest root' }
}
foreach ($target in $targets) {
    if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Recurse -Force }
}
if (Test-Path -LiteralPath $pytestRoot) {
    # Remove links themselves first; never traverse junction/symlink targets.
    $linkReport = Join-Path $workspaceRoot 'implementation/PHASE_REPORTS/pytest_cleanup_links_20261024.json'
    & (Join-Path $workspaceRoot '.venv/Scripts/python.exe') (Join-Path $PSScriptRoot 'find_cleanup_links.py') --root $pytestRoot --report $linkReport
    if ($LASTEXITCODE -ne 0) { throw 'Link inventory failed' }
    $links = Get-Content -LiteralPath $linkReport -Raw | ConvertFrom-Json
    foreach ($link in $links.links) {
        $linkPath = [IO.Path]::GetFullPath([string]$link.path)
        if (-not $linkPath.StartsWith($pytestRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Link outside pytest root' }
        if ($link.directory) { ([IO.DirectoryInfo]::new($linkPath)).Delete() }
        else { [IO.File]::Delete($linkPath) }
    }
    Write-Output 'Removing verified pytest tree...'
    Remove-Item -LiteralPath $pytestRoot -Recurse -Force
}
if (Test-Path -LiteralPath $pytestRoot) { throw 'pytest cleanup incomplete' }
$remaining = @(Get-ChildItem -LiteralPath $projectsRoot -Directory | Select-Object -ExpandProperty Name | Sort-Object)
if (@(Compare-Object $remaining @($report.kept_projects | Sort-Object)).Count) { throw 'Unexpected remaining project folders' }
if ((Get-FileHash -LiteralPath $activePath -Algorithm SHA256).Hash -ne $activeHash) { throw 'Active project pointer changed' }
$report.status = 'complete'
$report.deleted = $true
$report | Add-Member -NotePropertyName remaining_projects -NotePropertyValue $remaining -Force
$report | Add-Member -NotePropertyName pytest_deleted -NotePropertyValue $true -Force
$report | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $reportPath -Encoding utf8
[pscustomobject]@{FixtureFoldersRemoved=$targets.Count; PytestRemoved=$true; RemainingProjects=$remaining; Archive=$archive.FullName} | ConvertTo-Json
