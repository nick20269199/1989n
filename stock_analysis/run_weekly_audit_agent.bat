@echo off
REM 周审计 (未注册定时任务) - 手动执行
powershell -WindowStyle Hidden -Command "cmd /c 'echo [%DATE% %TIME%] Weekly Audit Agent start >> D:\1989n\stock_data\cognitive_agent.log & D:\Python314\python weekly_audit_agent.py >> D:\1989n\stock_data\cognitive_agent.log 2>&1 & echo [%DATE% %TIME%] Weekly Audit Agent end >> D:\1989n\stock_data\cognitive_agent.log'"
