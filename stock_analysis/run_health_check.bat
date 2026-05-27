@echo off
REM 系统健康检查 - 07:03
powershell -WindowStyle Hidden -Command "cmd /c 'D:\Python314\python health_check.py >> D:\1989n\stock_data\health_check.log 2>&1'"
