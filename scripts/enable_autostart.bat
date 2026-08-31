@echo off
set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT_NAME=SCRATCH Bot Autostart.lnk"
set "TARGET=%~dp0..\start_user_mode.bat"
set "WORKING_DIR=%~dp0.."

powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%STARTUP_FOLDER%\%SHORTCUT_NAME%'); $s.TargetPath = '%TARGET%'; $s.WorkingDirectory = '%WORKING_DIR%'; $s.Save()"
echo Auto-start on login ENABLED!
pause
