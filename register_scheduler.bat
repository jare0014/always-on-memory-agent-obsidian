@echo off
REM Registers Windows Task Scheduler OS-level jobs for 3x daily market scans
REM Quant Workspace Location: C:\Users\jare0\Documents\Obsidian\04_Projects\Quant\always-on-memory-agent

SET BAT_PATH="C:\Users\jare0\Documents\Obsidian\04_Projects\Quant\always-on-memory-agent\run_agentic_trader.bat"

echo Registering Robinhood Agentic Windows OS Tasks for Quant Workspace...

schtasks /create /tn "Robinhood_Agentic_10AM" /tr %BAT_PATH% /sc weekly /d MON,TUE,WED,THU,FRI /st 10:00 /f
schtasks /create /tn "Robinhood_Agentic_1PM" /tr %BAT_PATH% /sc weekly /d MON,TUE,WED,THU,FRI /st 13:00 /f
schtasks /create /tn "Robinhood_Agentic_330PM" /tr %BAT_PATH% /sc weekly /d MON,TUE,WED,THU,FRI /st 15:30 /f

echo.
echo ✅ Windows Task Scheduler jobs successfully registered!
schtasks /query /tn "Robinhood_Agentic_10AM"
schtasks /query /tn "Robinhood_Agentic_1PM"
schtasks /query /tn "Robinhood_Agentic_330PM"
pause
