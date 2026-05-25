@echo off
REM Bot v2 守护进程 — 每 5 分钟检查心跳，死亡自动重启
cd /d D:\1989n\stock_analysis
D:\Python314\python bot_v2_guardian.py >> bot_v2_guardian.log 2>&1
