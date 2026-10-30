@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" "%~dp0run.py" --in-terminal
) else (
    py -3.12 "%~dp0run.py" --in-terminal
)
set "studioExitCode=%ERRORLEVEL%"
if not "%studioExitCode%"=="0" (
    echo.
    echo Studio gagal berjalan. Pesan error di atas tetap tersedia untuk diperiksa.
    pause
)
exit /b %studioExitCode%
