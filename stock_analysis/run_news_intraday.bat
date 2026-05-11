@echo off
REM 新闻盘中采集 - 周一至周五 09:30-15:00 每30分钟
powershell -WindowStyle Hidden -Command "cmd /c 'D:\Python314\python D:\1989n\stock_analysis\news_scheduler.py intraday >> D:\1989n\stock_data\news_intraday.log 2>&1'"
