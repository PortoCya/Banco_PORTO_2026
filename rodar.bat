@echo off
chcp 65001 >nul
title NPS KeyCore - Launcher (Banco_PORTO_2026)
setlocal enabledelayedexpansion
set PYTHONUTF8=1

cd /d "%~dp0"

set "VENV_PY=%~dp0venv\Scripts\python.exe"
set "VENV_ALEMBIC=%~dp0venv\Scripts\alembic.exe"
set "VENV_UVICORN=%~dp0venv\Scripts\uvicorn.exe"
set "VENV_STREAMLIT=%~dp0venv\Scripts\streamlit.exe"
set "VENV_PYTEST=%~dp0venv\Scripts\pytest.exe"

if not exist "%VENV_PY%" (
    echo [ERRO] Ambiente virtual 'venv' nao encontrado!
    echo Crie com: python -m venv venv ^&^& venv\Scripts\pip install -r requirements-dev.txt -r requirements-dashboard.txt
    pause
    exit /b 1
)

if not exist "%~dp0.env" (
    echo [AVISO] Arquivo .env nao encontrado. Copiando .env.example para .env...
    copy "%~dp0.env.example" "%~dp0.env" >nul
    echo [ATENCAO] Edite o arquivo .env e preencha SECRET_KEY, ADMIN_EMAIL e ADMIN_SENHA!
    pause
    exit /b 1
)

:MENU
cls
echo ====================================================================
echo             NPS KeyCore (Banco_PORTO_2026) - Menu Rapido
echo ====================================================================
echo.
echo   [1] Rodar TUDO (API :8000 + Frontend Next.js :3000 + Dashboard :8501)
echo   [2] Rodar API (:8000) + Frontend Next.js (:3000)
echo   [3] Rodar apenas API Backend (:8000 - Swagger /docs)
echo   [4] Rodar API (:8000) + Dashboard Streamlit (:8501)
echo   [5] Rodar Worker de IA (processa comentarios com Gemini)
echo   [6] Rodar Testes Automatizados (pytest)
echo   [0] Fechar todas as portas (8000, 3000, 8501)
echo   [S] Sair
echo.
echo ====================================================================
set /p "OP=Escolha uma opcao (padrao 1): "
if "%OP%"=="" set "OP=1"

if /i "%OP%"=="1" goto RUN_ALL
if /i "%OP%"=="2" goto RUN_API_FRONT
if /i "%OP%"=="3" goto RUN_API_ONLY
if /i "%OP%"=="4" goto RUN_API_DASH
if /i "%OP%"=="5" goto RUN_WORKER
if /i "%OP%"=="6" goto RUN_TESTS
if /i "%OP%"=="0" goto CLOSE_PORTS
if /i "%OP%"=="S" exit /b 0
goto MENU

:PREPARE_DB
echo.
echo [1/2] Aplicando migrations do banco (alembic upgrade head)...
"%VENV_ALEMBIC%" upgrade head
if errorlevel 1 (
    echo [ERRO] Falha ao rodar alembic upgrade head!
    pause
    exit /b 1
)
echo [2/2] Garantindo dados iniciais (seed_db.py --demo)...
"%VENV_PY%" seed_db.py --demo --demo-token nps-keycore-2026
if errorlevel 1 (
    echo [ERRO] Falha ao rodar seed_db.py! Verifique ADMIN_EMAIL e ADMIN_SENHA no .env.
    pause
    exit /b 1
)
exit /b 0

:RUN_ALL
call :PREPARE_DB
if errorlevel 1 goto MENU
echo.
echo Liberando portas 8000, 3000 e 8501 antes de iniciar...
call "%~dp0fechar_portas.bat" --silencioso
echo.
echo Iniciando API FastAPI (porta 8000)...
start "NPS KeyCore - API (8000)" cmd /k "cd /d "%~dp0" && "%VENV_UVICORN%" main:app --reload --host 127.0.0.1 --port 8000"
echo Iniciando Frontend Next.js (porta 3000)...
start "NPS KeyCore - Frontend Next.js (3000)" cmd /k "cd /d "%~dp0frontend" && npm run dev"
echo Iniciando Dashboard Streamlit (porta 8501)...
start "NPS KeyCore - Dashboard Streamlit (8501)" cmd /k "cd /d "%~dp0" && set NPS_API_URL=http://localhost:8000 && "%VENV_STREAMLIT%" run dashboard/nps_dashboard.py --server.port 8501"
echo Iniciando Worker de IA (classificacao automatica de Tags e Sentimento)...
start "NPS KeyCore - Worker IA" cmd /k "cd /d "%~dp0" && "%VENV_PY%" -m app.ia.worker"
echo.
echo ====================================================================
echo   Tudo iniciado com sucesso! Acesse no navegador:
echo   - Frontend (Login / Admin / Pesquisa): http://localhost:3000
echo   - Link de Pesquisa Demo:               http://localhost:3000/pesquisa/nps-keycore-2026
echo   - API Swagger (/docs):                 http://localhost:8000/docs
echo   - Dashboard Analitico (Streamlit):     http://localhost:8501
echo ====================================================================
echo.
pause
goto MENU

:RUN_API_FRONT
call :PREPARE_DB
if errorlevel 1 goto MENU
call "%~dp0fechar_portas.bat" --silencioso
start "NPS KeyCore - API (8000)" cmd /k "cd /d "%~dp0" && "%VENV_UVICORN%" main:app --reload --host 127.0.0.1 --port 8000"
start "NPS KeyCore - Frontend Next.js (3000)" cmd /k "cd /d "%~dp0frontend" && npm run dev"
echo.
echo API em http://localhost:8000/docs e Frontend em http://localhost:3000
pause
goto MENU

:RUN_API_ONLY
call :PREPARE_DB
if errorlevel 1 goto MENU
call "%~dp0fechar_portas.bat" --silencioso
echo.
echo Iniciando API em http://localhost:8000/docs (Ctrl+C para parar)...
"%VENV_UVICORN%" main:app --reload --host 127.0.0.1 --port 8000
pause
goto MENU

:RUN_API_DASH
call :PREPARE_DB
if errorlevel 1 goto MENU
call "%~dp0fechar_portas.bat" --silencioso
start "NPS KeyCore - API (8000)" cmd /k "cd /d "%~dp0" && "%VENV_UVICORN%" main:app --reload --host 127.0.0.1 --port 8000"
start "NPS KeyCore - Dashboard Streamlit (8501)" cmd /k "cd /d "%~dp0" && set NPS_API_URL=http://localhost:8000 && "%VENV_STREAMLIT%" run dashboard/nps_dashboard.py --server.port 8501"
echo.
echo API em http://localhost:8000/docs e Dashboard em http://localhost:8501
pause
goto MENU

:RUN_WORKER
echo.
echo Iniciando Worker de IA (lembre-se de configurar IA_API_KEY no .env)...
start "NPS KeyCore - Worker IA" cmd /k "cd /d "%~dp0" && "%VENV_PY%" -m app.ia.worker"
pause
goto MENU

:RUN_TESTS
echo.
echo Executando suite de testes (pytest)...
"%VENV_PYTEST%"
echo.
pause
goto MENU

:CLOSE_PORTS
call "%~dp0fechar_portas.bat"
goto MENU
