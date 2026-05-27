@echo off
REM 情报部盘前侦察 - 工作日 08:32
powershell -WindowStyle Hidden -Command "cmd /c 'echo [%DATE% %TIME%] Intelligence Service start >> D:\1989n\stock_data/logs/intel_recon.log & D:\Python314\python intelligence_service.py recon >> D:\1989n\stock_data/logs/intel_recon.log 2>&1 & echo [%DATE% %TIME%] Intelligence Service end >> D:\1989n\stock_data/logs/intel_recon.log'"
