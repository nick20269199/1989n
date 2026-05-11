@echo off
REM 新闻晚间汇总 - 每日 22:00 执行
powershell -WindowStyle Hidden -Command "cmd /c 'D:\Python314\python D:\1989n\stock_analysis\news_scheduler.py evening >> D:\1989n\stock_data\news_evening.log 2>&1'"
