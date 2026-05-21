@echo off
REM 新闻盘中采集 - 周一至周五 09:30-15:00 每30分钟
cd /d D:\1989n\stock_analysis
D:\Python314\python news_scheduler.py intraday >> D:\1989n\stock_data\logs\news_intraday.log 2>&1
exit /b %ERRORLEVEL%
