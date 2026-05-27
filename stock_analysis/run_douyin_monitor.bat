@echo off
REM 抖音博主监控 - 每日 21:00
cd /d D:\1989n\stock_analysis
D:\Python314\python douyin_monitor.py >> D:\1989n\stock_data\douyin\monitor.log 2>&1
