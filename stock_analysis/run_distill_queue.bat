@echo off
REM 蒸馏队列扫描 — 扫描当日产出加入队列 - 工作日 15:45 / 23:45
cd /d D:\1989n\stock_analysis
D:\Python314\python distill_queue.py >> D:\1989n\stock_data\logs\distill_queue.log 2>&1
