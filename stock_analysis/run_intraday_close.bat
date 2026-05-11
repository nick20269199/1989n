@echo off
REM 收盘30分钟分析 - 每日 15:00 执行
powershell -WindowStyle Hidden -Command "cmd /c 'D:\Python314\python D:\1989n\stock_analysis\daily_task.py intraday_analysis close >> D:\1989n\stock_data\intraday_close.log 2>&1'"
