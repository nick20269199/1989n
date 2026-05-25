@echo off
REM 大V雷达每日管线 (转录+分析+日报) - 工作日 13:10
cd /d D:\1989n\stock_analysis
D:\Python314\python vv_daily.py >> D:\1989n\stock_data\vv_daily.log 2>&1
