@echo off
echo [1] Kill ace processes
taskkill /F /IM ace.exe /T >nul 2>&1
echo [2] Delete Ace scheduled tasks
schtasks /delete /tn "\AceSystem\AceUpdater\AceUpdaterTaskSystem150.0.7874.0{D4CDA605-0969-496A-B7CC-DA373FD1E0B7}" /f
schtasks /query /fo csv 2>nul | findstr /i "AceSystem" > "%TEMP%\acetasks.txt"
echo [3] Remove Ace folders
rmdir /s /q "C:\Program Files\Ace"
rmdir /s /q "C:\Program Files (x86)\Ace"
rmdir /s /q "C:\Users\Administrator\AppData\Local\Ace"
rmdir /s /q "C:\Users\Administrator\AppData\Roaming\Ace"
echo [4] Done. Remaining Ace tasks:
schtasks /query /fo csv 2>nul | findstr /i "AceSystem"
echo ExitCode=%ERRORLEVEL%
