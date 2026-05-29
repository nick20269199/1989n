@echo off
cd /d D:\1989n
python stock_analysis\vv_transcribe.py --since 2026-05-25 --priority > stock_data\vv_transcribe_weekly.log 2>&1
