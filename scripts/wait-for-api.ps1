param(
  [int]$Port = 8010,
  [int]$TimeoutSeconds = 45
)

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$urls = @(
  "http://127.0.0.1:$Port/imagegen/",
  "http://localhost:$Port/imagegen/"
)
while ((Get-Date) -lt $deadline) {
  foreach ($url in $urls) {
    $response = $null
    try {
      $request = [Net.HttpWebRequest]::Create($url)
      $request.Method = "GET"
      $request.AllowAutoRedirect = $false
      $request.Timeout = 2000
      $request.ReadWriteTimeout = 2000
      $response = $request.GetResponse()
      if ([int]$response.StatusCode -eq 200 -and $response.ContentType -match "^application/json(?:\s*;|$)") {
        Write-Output "Image generation API ready: $url"
        exit 0
      }
    } catch {
      # HTTP errors, redirects, and startup failures are not ready.
    } finally {
      if ($response) { $response.Close() }
    }
  }
  Start-Sleep -Milliseconds 500
}

Write-Error "ExplainFlow image generation API did not return HTTP 200 on port $Port within $TimeoutSeconds seconds. Check the EF-API window and confirm no other application owns this port."
exit 1
