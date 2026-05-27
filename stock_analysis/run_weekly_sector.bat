@echo off
REM 周度板块轮动报告 (手动) - 手动执行
powershell -WindowStyle Hidden -Command "cmd /c 'D:\Python314\python daily_task.py weekly_sector'"
exit /b %ERRORLEVEL%
