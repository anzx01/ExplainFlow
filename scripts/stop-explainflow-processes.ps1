$ErrorActionPreference = "SilentlyContinue"
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$rootPattern = [regex]::Escape($root.TrimEnd('\'))

$allProcesses = @(Get-CimInstance Win32_Process)
$processes = $allProcesses | Where-Object {
  $_.ProcessId -ne $PID -and $_.CommandLine -and $_.CommandLine -match $rootPattern -and (
    $_.CommandLine -match 'apps[\\/]web' -or
    $_.CommandLine -match 'services[\\/]api' -or
    $_.CommandLine -match 'apps[\\/]render'
  )
}

$killIds = [Collections.Generic.HashSet[int]]::new()
foreach ($process in $processes) { [void]$killIds.Add([int]$process.ProcessId) }
$pidFile = Join-Path $root '.explainflow-render.pid'
if (Test-Path -LiteralPath $pidFile) {
  $renderPid = 0
  [int]::TryParse((Get-Content -LiteralPath $pidFile -Raw), [ref]$renderPid) | Out-Null
  if ($renderPid -gt 0) { [void]$killIds.Add($renderPid) }
}

# Refresh the snapshot while walking descendants. This handles Node processes
# whose command line is only `node server.mjs` after their cmd.exe launcher.
for ($pass = 0; $pass -lt 5; $pass++) {
  Start-Sleep -Milliseconds 150
  $allProcesses = @(Get-CimInstance Win32_Process)
  $added = $false
  foreach ($process in $allProcesses) {
    if ($killIds.Contains([int]$process.ParentProcessId) -and $killIds.Add([int]$process.ProcessId)) { $added = $true }
  }
  if (-not $added) { break }
}

foreach ($process in ($allProcesses | Where-Object { $killIds.Contains([int]$_.ProcessId) } | Sort-Object ProcessId -Descending)) {
  Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
}
Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
