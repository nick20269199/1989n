@echo off
REM 盘前简报 - 每日 09:00 执行
cd /d D:\1989n\stock_analysis
D:\Python314\python daily_task.py morning_enhanced >> D:\1989n\stock_data\morning_brief.log 2>&1
