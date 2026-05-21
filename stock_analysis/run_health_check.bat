@echo off
REM 系统健康检查 - 每日 07:03 执行
cd /d D:\1989n\stock_analysis
D:\Python314\python health_check.py >> D:\1989n\stock_data\health_check.log 2>&1
