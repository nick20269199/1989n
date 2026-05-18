@echo off
chcp 65001 >nul
D:
cd D:\1989n\stock_analysis
D:\Python314\python -m market_pool.cli update --days 5 >> D:\1989n\stock_data\logs\pool_update.log 2>&1
