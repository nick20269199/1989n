@echo off
REM 板块日数据采集 - 工作日 15:20
powershell -WindowStyle Hidden -Command "cmd /c 'D:\Python314\python daily_task.py sector_collect >> D:\1989n\stock_data\logs\sector_collect.log 2>&1'"
