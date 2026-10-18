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

# Reclaim listeners owned by this local stack on restart. This also handles
# orphaned child processes whose command line no longer contains the project path.
foreach ($port in @(8010, 3010, 3002, 8188)) {
  foreach ($connection in @(Get-NetTCPConnection -LocalPort $port -State Listen)) {
  if ($connection.OwningProcess -and $connection.OwningProcess -ne $PID) {
    [void]$killIds.Add([int]$connection.OwningProcess)
  }
  }
}
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

# Kill reload supervisors and orphan workers even when their command line no
# longer carries the project path (uv run / --reload respawn chains). Without
# this, a surviving `uvicorn --reload` supervisor restarts killed workers and
# the port comes back before start.bat's own instance can bind it.
$stackPatterns = @(
  'uvicorn\b.*main:app',
  'spawn_main',
  'watchfiles.*main:app',
  'node\s+server\.mjs',
  'next\b.*\bdev\b.*3010'
)
for ($pass = 0; $pass -lt 5; $pass++) {
  $allProcesses = @(Get-CimInstance Win32_Process)
  $added = $false
  foreach ($process in $allProcesses) {
    if ($process.ProcessId -eq $PID -or -not $process.CommandLine) { continue }
    if ($process.CommandLine -match 'explorer\.exe') { continue }
    foreach ($pattern in $stackPatterns) {
      if ($process.CommandLine -match $pattern -and $killIds.Add([int]$process.ProcessId)) { $added = $true; break }
    }
  }
  if (-not $added) { break }
  Start-Sleep -Milliseconds 150
}

# Final sweep: keep reclaiming the stack ports until they are genuinely free,
# so a respawned worker cannot win the race against start.bat's new instance.
foreach ($attempt in 1..10) {
  $stillListening = $false
  foreach ($port in @(8010, 3010, 3002, 8188)) {
    foreach ($connection in @(Get-NetTCPConnection -LocalPort $port -State Listen)) {
      if ($connection.OwningProcess -and $connection.OwningProcess -ne $PID) {
        [void]$killIds.Add([int]$connection.OwningProcess)
        $stillListening = $true
      }
    }
  }
  foreach ($process in ($allProcesses | Where-Object { $killIds.Contains([int]$_.ProcessId) } | Sort-Object ProcessId -Descending)) {
    Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
  }
  if (-not $stillListening) { break }
  Start-Sleep -Milliseconds 400
}

foreach ($process in ($allProcesses | Where-Object { $killIds.Contains([int]$_.ProcessId) } | Sort-Object ProcessId -Descending)) {
  Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
}
Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
