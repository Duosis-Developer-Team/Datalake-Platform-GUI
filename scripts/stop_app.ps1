# Force-stop any process listening on port 8050 (Dash app).
# Use when Ctrl+C did not fully stop the app and the UI is still reachable.
# Run from project root: scripts\stop_app.bat  (or: powershell -ExecutionPolicy Bypass -File .\scripts\stop_app.ps1)

$port = 8050
$conn = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
if (-not $conn) {
    Write-Host "No process is listening on port $port. Nothing to stop." -ForegroundColor Yellow
    exit 0
}
$pid = $conn.OwningProcess
Write-Host "Stopping process PID $pid (port $port)..." -ForegroundColor Cyan
Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
Write-Host "Done. You can start the app again with: python app.py" -ForegroundColor Green
