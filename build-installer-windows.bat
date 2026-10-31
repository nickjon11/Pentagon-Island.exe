@echo off
setlocal
cd /d "%~dp0"
echo Pentagon Island v1.0.0 Installer Builder
py -3.13 -m venv .venv || goto fail
call .venv\Scripts\activate.bat
python -m pip install -r requirements-desktop.txt || goto fail
python -m PyInstaller --noconfirm --clean --onedir --windowed --name PentagonIsland --paths . --collect-all uvicorn --collect-all webview --collect-all fastapi --collect-all starlette --collect-all jinja2 --add-data "templates;templates" --add-data "static;static" desktop\launcher.py || goto fail
set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
 echo Install Inno Setup 6 and compile installer\PentagonIsland.iss
 pause
 exit /b 2
)
"%ISCC%" installer\PentagonIsland.iss || goto fail
echo SUCCESS: release\PentagonIsland-Setup-v1.0.0.exe
pause
exit /b 0
:fail
echo BUILD FAILED - see errors above.
pause
exit /b 1
