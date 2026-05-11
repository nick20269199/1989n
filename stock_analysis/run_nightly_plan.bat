@echo off
REM 隔夜交易计划生成 - 每日 15:40 执行 (收盘复盘之后)
cd /d D:\1989n\stock_analysis
D:\Python314\python nightly_plan.py auto >> D:\1989n\stock_data\nightly_plan.log 2>&1
