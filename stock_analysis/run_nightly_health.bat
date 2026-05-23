@echo off
REM 夜间健康检查 - 00:30
cd /d D:\1989n\stock_analysis
D:\Python314\python nightly_health_check.py >> D:\1989n\stock_data\nightly_health.log 2>&1
