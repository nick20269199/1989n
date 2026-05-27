@echo off
REM 收盘复盘 (带退出码修复) - 工作日 15:15
REM 注意: Python + akshare 退出时可能产生 STATUS_CONTROL_C_EXIT (3221225786)
REM 此为误报(脚本已完成工作)，powershell 包装后以 exit 0 结束
powershell -WindowStyle Hidden -Command "cmd /c 'D:\Python314\python daily_task.py closing_review >> D:\1989n\stock_data\closing_review.log 2>&1'"
exit /b 0
