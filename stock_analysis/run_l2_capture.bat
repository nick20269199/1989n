@echo off
REM L2 竞价数据自动采集 - 工作日 09:24:55
REM 在竞价窗口自动循环切换5只持仓股票，确保每只都捕获到 L2 逐笔数据
cd /d D:\1989n\stock_analysis
D:\Python314\python l2_auction_capture.py >> D:\1989n\stock_data\l2_capture.log 2>&1
