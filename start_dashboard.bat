@echo off
REM 知识库助手 · 科研选题版 —— 双击启动（桌面快捷方式指向这里）
REM 主界面：app_main.py（多页工作台）
REM 旧版桌面卡片仍可用：start_widget.bat
REM
REM 找 Python 的顺序：环境变量 KB_PYTHON > PATH 里的 pythonw > PATH 里的 python
REM 找不到就提示，而不是静默退出（以前写死绝对路径，换台机器就打不开）
cd /d "%~dp0"

if not "%~1"=="" goto custom
if defined KB_PYTHON (
    start "" "%KB_PYTHON%" "%~dp0app_main.py"
    goto :eof
)
where pythonw.exe >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw.exe "%~dp0app_main.py"
    goto :eof
)
where python.exe >nul 2>nul
if %errorlevel%==0 (
    start "" python.exe "%~dp0app_main.py"
    goto :eof
)
echo.
echo 没找到 Python。请安装 Python 3.10+ 并勾选「Add to PATH」，
echo 或先设置环境变量 KB_PYTHON 指向 pythonw.exe，例如：
echo     setx KB_PYTHON "C:\Path\To\python\pythonw.exe"
echo.
pause
exit /b 1

:custom
start "" "%~1" "%~dp0app_main.py"
:eof