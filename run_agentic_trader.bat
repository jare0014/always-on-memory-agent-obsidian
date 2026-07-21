@echo off
REM Headless Autonomous Robinhood Agentic Trader Runner
REM Runs Windows OS-level scheduled market scans and data lake logging

cd /d "C:\Users\jare0\.gemini\antigravity-ide\scratch\always-on-memory-agent"
".venv\Scripts\python.exe" agentic_trader.py >> agentic_trader.log 2>&1
".venv\Scripts\python.exe" sync_to_quant.py >> sync_to_quant.log 2>&1
echo [%DATE% %TIME%] Robinhood Agentic scan completed successfully. >> agentic_trader.log
