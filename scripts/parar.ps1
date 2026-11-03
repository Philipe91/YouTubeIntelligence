# Desliga o que o iniciar.ps1 ligou, incluindo processos filhos. Não apaga dados.
$root = Split-Path -Parent $PSScriptRoot
$pids = Join-Path $root 'data\processos.txt'
if (-not (Test-Path $pids)) { 'Nada para desligar.'; return }

$all = Get-CimInstance Win32_Process
foreach ($line in Get-Content $pids) {
  $queue = @([int]$line); $i = 0
  while ($i -lt $queue.Count) {
    $all | Where-Object { $_.ParentProcessId -eq $queue[$i] } | ForEach-Object { $queue += $_.ProcessId }
    $i++
  }
  foreach ($id in $queue) {
    $process = $all | Where-Object { $_.ProcessId -eq $id }
    # Só encerra se ainda for processo do aplicativo: o Windows pode reutilizar números de processo.
    if ($process -and $process.Name -in @('python.exe', 'node.exe')) {
      Stop-Process -Id $id -Force -Confirm:$false -ErrorAction SilentlyContinue
    }
  }
}
Remove-Item $pids -Force
'Desligado.'
