@echo off
cd /d "%~dp0"
python -m india_trader.web --open
if errorlevel 1 pause
