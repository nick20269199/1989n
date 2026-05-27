@echo off
REM 任务仪表盘监控 - 20:00
powershell -WindowStyle Hidden -Command "cmd /c 'echo [%DATE% %TIME%] Task Dashboard start >> D:\1989n\stock_data\cognitive_agent.log & D:\Python314\python task_dashboard.py >> D:\1989n\stock_data\cognitive_agent.log 2>&1 & echo [%DATE% %TIME%] Task Dashboard end >> D:\1989n\stock_data\cognitive_agent.log'"
