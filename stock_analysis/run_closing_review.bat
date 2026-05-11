@echo off
REM 收盘复盘 - 每日 15:15 执行
cd /d D:\1989n\stock_analysis
D:\Python314\python daily_task.py closing_review >> D:\1989n\stock_data\closing_review.log 2>&1
