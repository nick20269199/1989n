@echo off
REM 技术选股扫描 - 每日 15:30 执行
cd /d D:\1989n\stock_analysis
D:\Python314\python daily_task.py tech_scan >> D:\1989n\stock_data\tech_scan.log 2>&1
