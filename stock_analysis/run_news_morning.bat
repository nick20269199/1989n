@echo off
REM 新闻早间汇总 - 每日 08:00 执行
powershell -WindowStyle Hidden -Command "cmd /c 'D:\Python314\python D:\1989n\stock_analysis\news_scheduler.py morning >> D:\1989n\stock_data\news_morning.log 2>&1'"
