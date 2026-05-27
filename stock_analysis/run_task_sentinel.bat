@echo off
REM 任务哨兵 — 检查定时任务+数据文件健康 - 10:00
powershell -WindowStyle Hidden -Command "cmd /c 'D:\Python314\python task_sentinel.py >> D:\1989n\stock_data\logs\task_sentinel.log 2>&1'"
