@echo off
schtasks /Delete /TN "SEL_DistillQueue" /F
schtasks /Delete /TN "SEL_TaskSentinel" /F
schtasks /Delete /TN "StockAnalysis_DailyCompress" /F
schtasks /Delete /TN "StockForecastCloser" /F
echo Done.
pause
