@echo off
REM 盘中新闻采集 (09:30-15:00 每30分钟) - 工作日 09:30 (每30分钟至05:30)
powershell -WindowStyle Hidden -Command "cmd /c 'D:\Python314\python news_scheduler.py intraday >> D:\1989n\stock_data\logs\news_intraday.log 2>&1'"
exit /b %ERRORLEVEL%
