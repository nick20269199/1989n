@echo off
REM KAE 周全量管线 - 周日 10:03
powershell -WindowStyle Hidden -Command "cmd /c 'D:\Python314\python knowledge_runner.py pipeline >> D:\1989n\stock_data\kae_weekly.log 2>&1'"
