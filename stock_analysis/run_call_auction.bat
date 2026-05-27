@echo off
REM 集合竞价数据采集 - 工作日 09:26
powershell -WindowStyle Hidden -Command "cmd /c 'D:\Python314\python call_auction.py >> D:\1989n\stock_data\call_auction.log 2>&1'"
