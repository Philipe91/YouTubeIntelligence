# Liga a API e a interface sem wrappers (uv, npm), para gastar menos memória e não deixar processos órfãos.
# Uso: powershell -ExecutionPolicy Bypass -File scripts\iniciar.ps1
# Requer ter rodado uma vez: uv sync (backend), npm install e npm run build (frontend).
param([int]$ApiPort = 8000, [int]$WebPort = 3000)

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root 'backend\.venv\Scripts\python.exe'
$next = Join-Path $root 'frontend\node_modules\next\dist\bin\next'
$pids = Join-Path $root 'data\processos.txt'
New-Item -ItemType Directory -Force (Join-Path $root 'data') | Out-Null

foreach ($port in $ApiPort, $WebPort) {
  if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) {
    throw "A porta $port já está em uso. Rode scripts\parar.ps1 ou escolha outra porta."
  }
}

$env:NEXT_TELEMETRY_DISABLED = '1'
$env:YTI_API_URL = "http://127.0.0.1:$ApiPort"
$api = Start-Process -FilePath $python -WorkingDirectory (Join-Path $root 'backend') -WindowStyle Hidden -PassThru `
  -ArgumentList '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', $ApiPort, '--no-access-log'
$web = Start-Process -FilePath 'node' -WorkingDirectory (Join-Path $root 'frontend') -WindowStyle Hidden -PassThru `
  -ArgumentList "`"$next`"", 'start', '-H', '127.0.0.1', '-p', $WebPort
"$($api.Id)`n$($web.Id)" | Set-Content -Path $pids -Encoding ascii

"Aberto em http://127.0.0.1:$WebPort. Para desligar: scripts\parar.ps1"
