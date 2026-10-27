@echo off
cd /d "%~dp0"
python -m india_trader connections connect kite
if errorlevel 1 goto done
python -m india_trader connections sync kite
:done
pause
