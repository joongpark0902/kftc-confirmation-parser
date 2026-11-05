@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"
set "PYTHONPATH=%~dp0프로그램;%~dp0;%PYTHONPATH%"
python -m unittest discover -s tests -t . %*
exit /b %errorlevel%
