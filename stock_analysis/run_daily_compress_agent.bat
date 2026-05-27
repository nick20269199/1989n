@echo off
REM 每日复盘压缩 - 23:00
powershell -WindowStyle Hidden -Command "cmd /c 'D:\Python314\python daily_compress_agent.py >> D:\1989n\stock_data\cognitive_agent.log 2>&1'"
