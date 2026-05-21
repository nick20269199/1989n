@echo off
REM 工程部 Evolve Read+Extract — 12:00 每日 (休盘时段)
cd /d D:\1989n\stock_analysis
D:\Python314\python sel_evolve_read.py
exit /b %ERRORLEVEL%
