@echo off
REM 晚间总结 + 大V雷达 + 预测闭环 - 22:00
cd /d D:\1989n\stock_analysis
D:\Python314\python vv_radar.py fetch >> D:\1989n\stock_data\vv_radar.log 2>&1

echo [%DATE% %TIME%] Daily Task start >> D:\1989n\stock_data\evening.log
D:\Python314\python daily_task.py evening >> D:\1989n\stock_data\evening.log 2>&1
echo [%DATE% %TIME%] Daily Task end >> D:\1989n\stock_data\evening.log
D:\Python314\python forecast_closer.py --report >> D:\1989n\stock_data\forecast_closer.log 2>&1
