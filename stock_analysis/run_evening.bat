@echo off
REM 晚间汇总 - 每日 22:00 执行
cd /d D:\1989n\stock_analysis
D:\Python314\python daily_task.py evening >> D:\1989n\stock_data\evening.log 2>&1
