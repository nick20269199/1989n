@echo off
cd /d D:\1989n
for /f %%i in ('python -c "from datetime import datetime, timedelta; print((datetime.now() - timedelta(days=1)).strftime('%%Y-%%m-%%d'))"') do set SINCE=%%i
python stock_analysis/vv_transcribe.py --since %SINCE% --priority --limit 30
if errorlevel 1 (
    echo [%DATE% %TIME%] vv_transcribe_daily 失败 >> stock_data/vv_transcribe_daily.log
) else (
    echo [%DATE% %TIME%] vv_transcribe_daily 完成 >> stock_data/vv_transcribe_daily.log
)
