@echo off
cd /d D:\1989n\stock_analysis
D:\Python314\python daily_task.py weekly_sector
if %ERRORLEVEL% NEQ 0 (
    echo 周度板块轮动报告 (手动)失败
    pause
    exit /b 1
)
echo.
echo 完成
pause
