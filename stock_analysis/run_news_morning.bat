@echo off
REM 早间新闻采集 - 08:00
powershell -WindowStyle Hidden -Command "cmd /c 'D:\Python314\python news_scheduler.py morning >> D:\1989n\stock_data\logs\news_morning.log 2>&1'"
exit /b %ERRORLEVEL%
