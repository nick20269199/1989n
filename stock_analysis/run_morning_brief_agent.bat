@echo off
REM 盘前晨报 v2 (AI Agent) - 工作日 08:37
powershell -WindowStyle Hidden -Command "cmd /c 'echo [%DATE% %TIME%] Morning Brief Agent start >> D:\1989n\stock_data\cognitive_agent.log & D:\Python314\python morning_brief_agent.py >> D:\1989n\stock_data\cognitive_agent.log 2>&1 & echo [%DATE% %TIME%] Morning Brief Agent end >> D:\1989n\stock_data\cognitive_agent.log'"
