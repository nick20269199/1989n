@echo off
REM 大V雷达 (13:00下午) - 13:00
powershell -WindowStyle Hidden -Command "cmd /c 'D:\Python314\python D:\1989n\stock_analysis\vv_radar.py fetch >> D:\1989n\stock_data\vv_radar.log 2>&1'"
