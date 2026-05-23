@echo off
REM 晚间新闻采集 - 21:55
cd /d D:\1989n\stock_analysis
D:\Python314\python news_scheduler.py evening >> D:\1989n\stock_data\logs\news_evening.log 2>&1
exit /b %ERRORLEVEL%
