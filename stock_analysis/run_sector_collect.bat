@echo off
REM 板块日数据采集 - 工作日 15:20
cd /d D:\1989n\stock_analysis
D:\Python314\python daily_task.py sector_collect >> nul 2>&1
