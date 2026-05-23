@echo off
REM 隔夜分析 (美股+次日展望) - 工作日 23:37
powershell -WindowStyle Hidden -Command "cmd /c 'D:\Python314\python D:\1989n\stock_analysis\daily_task.py overnight >> D:\1989n\stock_data\overnight.log 2>&1'"
