@echo off
REM KAE 日增量管线 - 工作日 21:03
powershell -WindowStyle Hidden -Command "cmd /c 'D:\Python314\python knowledge_runner.py pipeline --incremental >> D:\1989n\stock_data\kae_daily.log 2>&1'"
