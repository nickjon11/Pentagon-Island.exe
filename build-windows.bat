@echo off
setlocal
cd /d "%~dp0"
py -3 -m pip install -r requirements-desktop.txt || exit /b 1
py -3 -m PyInstaller --noconfirm --clean --onefile --windowed --name PentagonIsland --paths . --collect-all uvicorn --collect-all webview --collect-all fastapi --collect-all starlette --collect-all jinja2 --add-data "templates;templates" --add-data "static;static" desktop\launcher.py || exit /b 1
echo Built dist\PentagonIsland.exe
