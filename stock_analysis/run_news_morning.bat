@echo off
REM 早间新闻采集 - 08:00
cd /d D:\1989n\stock_analysis
D:\Python314\python news_scheduler.py morning >> D:\1989n\stock_data\logs\news_morning.log 2>&1
exit /b %ERRORLEVEL%
