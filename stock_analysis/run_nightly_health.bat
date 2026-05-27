@echo off
REM 夜间健康检查 - 00:30
powershell -WindowStyle Hidden -Command "cmd /c 'D:\Python314\python nightly_health_check.py >> D:\1989n\stock_data\nightly_health.log 2>&1'"
