@echo off
REM 决策 T+5 定时回测 - 工作日 16:30
cd /d D:\1989n\stock_analysis
D:\Python314\python daily_task.py backtest >> D:\1989n\stock_data\logs\decision_backtest.log 2>&1
