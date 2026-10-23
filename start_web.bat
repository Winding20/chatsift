@echo off
chcp 936 >nul
setlocal
title chatsift
cd /d "%~dp0"

echo ============================================
echo   chatsift - 群聊阅读代理
echo ============================================
echo.

rem ---------- 1. 检查 Python ----------
where python >nul 2>nul
if errorlevel 1 goto no_python

for /f "tokens=2" %%v in ('python -V 2^>^&1') do set "PYVER=%%v"
echo [检查] 系统 Python %PYVER%

rem ---------- 2. 准备运行环境 ----------
if exist ".venv\Scripts\python.exe" goto env_ok

echo.
echo [1/3] 第一次运行，正在创建运行环境...
python -c "import sys;sys.exit(0 if sys.version_info>=(3,10) else 1)"
if errorlevel 1 goto old_python
python -m venv .venv
if errorlevel 1 goto fail

echo [2/3] 正在安装依赖，第一次会慢一点，请耐心等...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul 2>nul
".venv\Scripts\python.exe" -m pip install -e .
if errorlevel 1 goto fail
echo [3/3] 依赖安装完成

:env_ok
echo [检查] 运行环境已就绪

rem ---------- 3. 检查配置文件 ----------
if exist ".env" goto env_file_ok

copy ".env.example" ".env" >nul
echo.
echo [第一次运行] 已生成配置文件 .env
echo 现在会用记事本打开它，请填这三行：
echo.
echo    AI_API_KEY=你的密钥
echo    AI_BASE_URL=https://open.bigmodel.cn/api/paas/v4/
echo    AI_MODEL=glm-4-flash
echo.
echo 保存并关闭记事本后，这里会自动继续启动。
echo.
start /wait notepad .env

:env_file_ok
".venv\Scripts\python.exe" -c "import pathlib,sys;t=pathlib.Path('.env').read_text(encoding='utf-8',errors='ignore');k=[l.split('=',1)[1].strip() for l in t.splitlines() if l.strip().startswith(('AI_API_KEY=','ZHIPU_API_KEY='))];sys.exit(0 if any(k) else 1)"
if errorlevel 1 goto no_key
goto port_check

:no_key
echo.
echo [提示] .env 里的 AI_API_KEY 还是空的。
echo 没有密钥可以先去 https://open.bigmodel.cn 注册，或用本地 Ollama。
echo 现在照样启动，只是点总结时会提示配置不完整。

:port_check
netstat -ano | findstr ":5000 " | findstr "LISTENING" >nul 2>nul
if not errorlevel 1 goto port_5000

netstat -ano | findstr ":8765 " | findstr "LISTENING" >nul 2>nul
if not errorlevel 1 goto port_8765

goto run

:port_5000
echo.
echo [提示] 5000 端口已被占用，可能已经有一个实例在运行。
echo 如果那就是本项目，直接打开页面即可；否则请先关闭占用它的程序。
set "ANS="
set /p "ANS=要打开页面吗？(Y/N) "
if /i "%ANS%"=="Y" start "" http://127.0.0.1:5000
exit /b 0

:port_8765
echo.
echo [提示] 8765 端口已被占用，接收端无法启动。
echo 多半是另一个本项目实例还在运行，请先关掉那个窗口再试。
pause
exit /b 1

:run
echo.
echo 启动中... 面板：http://127.0.0.1:5000
echo 关闭这个窗口 = 停止服务。
echo.

if "%CHATSIFT_NO_BROWSER%"=="1" goto server
start "" /b cmd /c "timeout /t 5 >nul & start http://127.0.0.1:5000"

:server
".venv\Scripts\python.exe" -X utf8 run.py

echo.
echo 服务已停止。
pause
exit /b 0

:old_python
echo.
echo [错误] Python 版本太低，本项目需要 3.10 或更高。
echo 当前版本：
python -V
echo 请到 https://www.python.org/downloads/ 安装新版本后重试。
echo.
pause
exit /b 1

:no_python
echo.
echo [错误] 没有找到 Python。
echo 请先安装 Python 3.11 或更高版本：https://www.python.org/downloads/
echo 安装时务必勾选 Add Python to PATH。
echo.
pause
exit /b 1

:fail
echo.
echo [错误] 安装失败。
echo 常见原因：网络无法下载依赖、Python 版本太低、或没有写文件的权限。
echo 手动排查：python -m venv .venv
echo           .venv\Scripts\python.exe -m pip install -e .
pause
exit /b 1
