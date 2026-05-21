@echo off
REM 工程部 Morning Lint — Win Task Scheduler wrapper v2
REM 注册: SEL_MorningLint (08:30 每日)

cd /d D:\1989n\stock_analysis
set PYTHONPATH=D:\1989n\stock_analysis

if "%1"=="--local" (
    D:\Python314\python lint_wrapper.py
) else (
    set FEISHU_SEND_ENABLED=true
    D:\Python314\python lint_wrapper.py
)

exit /b %ERRORLEVEL%
