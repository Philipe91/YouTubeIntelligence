# Mede a RAM da API (Python direto, sem o wrapper do uv) ociosa e depois de carregar a analise.
# Sobe em portas proprias e encerra tudo ao final. Nao altera dados alem de criar bancos vazios se faltarem.
param([int]$Port = 8010)

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root 'backend\.venv\Scripts\python.exe'
$backend = Join-Path $root 'backend'

# No Windows, o python.exe do venv e so um lancador: o processo real e filho dele. Soma a arvore.
function TreeIds($rootId) {
  $all = Get-CimInstance Win32_Process
  $ids = @($rootId); $i = 0
  while ($i -lt $ids.Count) {
    $all | Where-Object { $_.ParentProcessId -eq $ids[$i] } | ForEach-Object { $ids += $_.ProcessId }
    $i++
  }
  $ids
}
function Mb($id) {
  $total = 0
  foreach ($item in (TreeIds $id)) {
    $p = Get-Process -Id $item -ErrorAction SilentlyContinue
    if ($p) { $total += $p.WorkingSet64 }
  }
  [math]::Round($total / 1MB)
}

$api = Start-Process -FilePath $python -WorkingDirectory $backend -WindowStyle Hidden -PassThru `
  -ArgumentList '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', $Port, '--no-access-log'
try {
  $ready = $false
  foreach ($i in 1..60) {
    try { Invoke-RestMethod "http://127.0.0.1:$Port/api/filters" -TimeoutSec 5 | Out-Null; $ready = $true; break } catch { Start-Sleep -Milliseconds 500 }
  }
  if (-not $ready) { throw 'A API nao respondeu.' }
  Start-Sleep -Seconds 2
  "API ociosa, sem analise carregada: $(Mb $api.Id) MB"
  $t = Measure-Command { Invoke-RestMethod "http://127.0.0.1:$Port/api/overview?format=short" -TimeoutSec 120 | Out-Null }
  "Primeira analise: $([math]::Round($t.TotalSeconds, 1)) s"
  "API depois da analise: $(Mb $api.Id) MB"
  foreach ($i in 1..5) { Invoke-RestMethod "http://127.0.0.1:$Port/api/overview?format=long" -TimeoutSec 120 | Out-Null }
  "API depois de 5 consultas: $(Mb $api.Id) MB"
} finally {
  foreach ($item in (TreeIds $api.Id)) { Stop-Process -Id $item -Force -Confirm:$false -ErrorAction SilentlyContinue }
}
