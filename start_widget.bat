@echo off
REM 旧版桌面卡片（520px 挂件形态），保留作为备用入口
REM 找 Python 的顺序：环境变量 KB_PYTHON > PATH 里的 pythonw > PATH 里的 python
cd /d "%~dp0"

if defined KB_PYTHON (
    start "" "%KB_PYTHON%" "%~dp0kb_widget.py"
    goto :eof
)
where pythonw.exe >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw.exe "%~dp0kb_widget.py"
    goto :eof
)
where python.exe >nul 2>nul
if %errorlevel%==0 (
    start "" python.exe "%~dp0kb_widget.py"
    goto :eof
)
echo.
echo 没找到 Python。请安装 Python 3.10+ 并勾选「Add to PATH」，
echo 或先设置环境变量 KB_PYTHON 指向 pythonw.exe，例如：
echo     setx KB_PYTHON "C:\Path\To\python\pythonw.exe"
echo.
pause
exit /b 1