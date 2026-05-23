@echo off
cd /d D:\1989n\stock_analysis
/D/Python314/python daily_task.py backtest
if %ERRORLEVEL% NEQ 0 (
    echo 回测失败
    pause
    exit /b 1
)
echo.
echo 完成
pause
