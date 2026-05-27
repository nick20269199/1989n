@echo off
REM 隔夜交易计划生成 - 工作日 15:40
powershell -WindowStyle Hidden -Command "cmd /c 'D:\Python314\python nightly_plan.py auto >> D:\1989n\stock_data\nightly_plan.log 2>&1'"
