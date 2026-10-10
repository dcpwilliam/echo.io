@echo off
rem aiservice 快速启动（Windows）
rem   start.bat              默认 127.0.0.1:8100
rem   set PORT=8200 && start.bat

setlocal
cd /d "%~dp0"

if "%AISERVICE_HOST%"=="" set AISERVICE_HOST=127.0.0.1
if "%PORT%"=="" set PORT=8100

where py >nul 2>nul && (set PY=py & goto :run)
where python >nul 2>nul && (set PY=python & goto :run)

echo [x] 没找到 Python。请先安装 Python 3.8+ 或设置 PYTHON_BIN
exit /b 1

:run
if not exist "data" mkdir data
echo ==========================================
echo  aiservice - Timeline Python service
echo ==========================================
echo  Listening: http://%AISERVICE_HOST%:%PORT%
echo ==========================================
echo.
"%PY%" run.py --host %AISERVICE_HOST% --port %PORT% %*

endlocal
