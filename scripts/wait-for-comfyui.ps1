param(
  [int]$Port = 8188,
  [int]$TimeoutSeconds = 90
)

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$url = "http://127.0.0.1:$Port/system_stats"
while ((Get-Date) -lt $deadline) {
  try {
    $response = Invoke-RestMethod -Uri $url -TimeoutSec 3
    if ($null -ne $response) { exit 0 }
  } catch {}
  Start-Sleep -Seconds 2
}
exit 1
