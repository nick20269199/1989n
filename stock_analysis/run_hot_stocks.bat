@echo off
REM 热门股票采集 + 大V雷达联动 - 工作日 09:35 / 工作日 13:00
cd /d D:\1989n\stock_analysis
D:\Python314\python daily_task.py hot_stocks >> D:\1989n\stock_data\hot_stocks.log 2>&1
D:\Python314\python vv_radar.py fetch >> D:\1989n\stock_data\vv_radar.log 2>&1
