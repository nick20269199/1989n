@echo off
REM 预测追踪闭环 - 工作日 17:05
powershell -WindowStyle Hidden -Command "cmd /c 'D:\Python314\python forecast_closer.py --report >> D:\1989n\stock_data\forecast_closer.log 2>&1'"
