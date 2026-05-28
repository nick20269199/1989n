@echo off
REM 侦查日报 (收盘后探索层) - 工作日 15:30 → 已合并到 intelligence_service.py recon --full
powershell -WindowStyle Hidden -Command "cmd /c 'D:\Python314\python intelligence_service.py recon --full >> D:\1989n\stock_data\recon_daily.log 2>&1'"
