@echo off
REM 收盘复盘 - 每日 15:15 执行
REM 注意: Python + akshare 退出时可能产生 STATUS_CONTROL_C_EXIT (3221225786)
REM 此为误报(脚本已完成工作)，映射为 0
cd /d D:\1989n\stock_analysis
D:\Python314\python daily_task.py closing_review >> D:\1989n\stock_data\closing_review.log 2>&1
if %ERRORLEVEL% EQU 3221225786 exit /b 0
exit /b %ERRORLEVEL%
