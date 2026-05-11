@echo off
REM 热门股票采集 - 每日 09:15 起每小时
cd /d D:\1989n\stock_analysis
D:\Python314\python daily_task.py hot_stocks >> D:\1989n\stock_data\hot_stocks.log 2>&1
