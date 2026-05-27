@echo off
REM 侦查日报 (收盘后探索层) - 工作日 15:30
powershell -WindowStyle Hidden -Command "cmd /c 'D:\Python314\python recon_daily.py >> D:\1989n\stock_data\recon_daily.log 2>&1'"
