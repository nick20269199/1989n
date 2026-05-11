@echo off
REM 隔夜分析 - 每日 23:30 执行
powershell -WindowStyle Hidden -Command "cmd /c 'D:\Python314\python D:\1989n\stock_analysis\daily_task.py overnight >> D:\1989n\stock_data\overnight.log 2>&1'"
