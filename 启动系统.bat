@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0src"
title 智慧自习室预约与管理系统 v1.0

echo ==========================================
echo   智慧自习室预约与管理系统 v1.0
echo ==========================================
echo.

if not exist "app.py" (
    echo [错误] 未找到 src\app.py。请确认已解压完整项目，且 启动系统.bat 位于项目根目录。
    pause
    exit /b 1
)

where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未找到 Python，请安装 Python 3.13 并勾选 Add Python to PATH。
    pause
    exit /b 1
)

echo [1/4] 检查依赖（首次运行需要联网安装）...
python -m pip install -q -r requirements.txt
if errorlevel 1 (
    echo [错误] 依赖安装失败，请检查网络或 Python 环境，详见 docs/guides/launcher.md。
    pause
    exit /b 1
)

echo [2/4] 检查端口 5012...
netstat -ano | findstr "LISTENING" | findstr ":5012" >nul 2>nul
if not errorlevel 1 (
    echo [错误] 端口 5012 已被占用，请先关闭占用该端口的程序，详见 docs/guides/launcher.md。
    pause
    exit /b 1
)

echo [3/4] 启动服务，端口 5012...
echo [4/4] 浏览器将自动打开 http://127.0.0.1:5012/
echo       按 Ctrl+C 停止服务；关闭本窗口也可停止。
echo.

start "" powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:5012/'"
python app.py

echo.
echo 服务已停止。
pause
