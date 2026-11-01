@echo off
chcp 65001 >nul
cd /d "%~dp0.."
python prototypes\ma_semaine.py --creer
echo.
pause
