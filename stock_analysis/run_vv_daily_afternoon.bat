@echo off
REM 大V雷达每日管线 (转录+分析+日报) - 工作日 13:10
powershell -WindowStyle Hidden -Command "cmd /c 'D:\Python314\python D:\1989n\stock_analysis\vv_daily.py  >> D:\1989n\stock_data\vv_daily.log 2>&1'"
