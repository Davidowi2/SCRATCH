@echo off
set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT_NAME=SCRATCH Bot Autostart.lnk"
if exist "%STARTUP_FOLDER%\%SHORTCUT_NAME%" (
    del "%STARTUP_FOLDER%\%SHORTCUT_NAME%"
    echo Auto-start on login DISABLED!
) else (
    echo Auto-start shortcut was not present.
)
pause
