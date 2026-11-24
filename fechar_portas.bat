@echo off
chcp 65001 >nul
echo Encerrando processos nas portas 8000 (API), 3000 (Frontend) e 8501 (Dashboard)...
powershell -NoProfile -ExecutionPolicy Bypass -Command "foreach ($port in @(8000, 3000, 8501)) { $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue; if ($conns) { $pids = $conns | Select-Object -ExpandProperty OwningProcess -Unique; foreach ($pidNum in $pids) { if ($pidNum -gt 0) { Stop-Process -Id $pidNum -Force -ErrorAction SilentlyContinue; Write-Host \"[OK] Porta $port liberada (PID $pidNum encerrado).\" -ForegroundColor Green } } } else { Write-Host \"[--] Porta $port ja estava livre.\" -ForegroundColor DarkGray } }"
if /i not "%~1"=="--silencioso" (
    echo.
    pause
)
