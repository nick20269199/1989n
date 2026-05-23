@echo off
cd /d D:\1989n\stock_analysis
D:\Python314\python daily_task.py sector_collect
if %ERRORLEVEL% NEQ 0 (
    echo 板块日数据采集 (手动)失败
    pause
    exit /b 1
)
echo.
echo 完成
pause
