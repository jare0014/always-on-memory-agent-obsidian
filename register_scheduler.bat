@echo off
REM Registers Windows Task Scheduler OS-level jobs for 3x daily market scans
REM Runs at 10:00 AM, 1:00 PM, and 3:30 PM ET every weekday (Mon-Fri)

SET BAT_PATH="C:\Users\jare0\.gemini\antigravity-ide\scratch\always-on-memory-agent\run_agentic_trader.bat"

echo Registering Robinhood Agentic Windows OS Tasks...

schtasks /create /tn "Robinhood_Agentic_10AM" /tr %BAT_PATH% /sc weekly /d MON,TUE,WED,THU,FRI /st 10:00 /f
schtasks /create /tn "Robinhood_Agentic_1PM" /tr %BAT_PATH% /sc weekly /d MON,TUE,WED,THU,FRI /st 13:00 /f
schtasks /create /tn "Robinhood_Agentic_330PM" /tr %BAT_PATH% /sc weekly /d MON,TUE,WED,THU,FRI /st 15:30 /f

echo.
echo ✅ Windows Task Scheduler jobs successfully registered!
schtasks /query /tn "Robinhood_Agentic_*" /fo TABLE
pause
