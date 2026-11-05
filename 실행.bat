@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"
if /I "%~1"=="--selftest" (
  python "%~dp0프로그램\kftc_gui_v3.py" --selftest
  exit /b
)
start "" pythonw "%~dp0프로그램\kftc_gui_v3.py" %*
