@echo off
cd /d %~dp0
echo ========================================
echo   FabTwin Pro Backend - 启动中
echo ========================================
pip install -r requirements.txt
python main.py
pause
