@echo off
REM 晚间总结 - 每日 22:00 执行
cd /d D:\1989n\stock_analysis
echo [%DATE% %TIME%] Evening Summary start >> D:\1989n\stock_data\evening.log
D:\Python314\python daily_task.py evening >> D:\1989n\stock_data\evening.log 2>&1
echo [%DATE% %TIME%] Evening Summary end >> D:\1989n\stock_data\evening.log
