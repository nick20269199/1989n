@echo off
REM 午盘30分钟分析 - 每日 11:30 执行
powershell -WindowStyle Hidden -Command "cmd /c 'D:\Python314\python D:\1989n\stock_analysis\daily_task.py intraday_analysis midday >> D:\1989n\stock_data\intraday_midday.log 2>&1'"
