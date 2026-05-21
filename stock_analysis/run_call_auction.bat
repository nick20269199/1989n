@echo off
REM 集合竞价采集 - 每日 09:26 执行
cd /d D:\1989n\stock_analysis
D:\Python314\python call_auction.py >> D:\1989n\stock_data\call_auction.log 2>&1
