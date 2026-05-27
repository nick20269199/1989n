@echo off
REM 晚间新闻采集 - 21:55
powershell -WindowStyle Hidden -Command "cmd /c 'D:\Python314\python news_scheduler.py evening >> D:\1989n\stock_data\logs\news_evening.log 2>&1'"
exit /b %ERRORLEVEL%
