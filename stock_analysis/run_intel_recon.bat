@echo off
cd /d "D:\1989n\stock_analysis"
echo [%DATE% %TIME%] Intelligence Service start >> D:\1989n\stock_data/logs/intel_recon.log
D:\Python314\python intelligence_service.py recon >> D:\1989n\stock_data/logs/intel_recon.log 2>&1
echo [%DATE% %TIME%] Intelligence Service end >> D:\1989n\stock_data/logs/intel_recon.log
