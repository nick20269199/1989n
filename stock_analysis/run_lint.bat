@echo off
REM 工程部 Morning Lint — Win Task Scheduler wrapper
REM 注册到计划任务: 每天 08:30 执行
REM
REM 用法:
REM   run_lint.bat          → 执行 lint，HIGH 问题发飞书
REM   run_lint.bat --local  → 执行 lint，不发飞书（调试用）

setlocal
cd /d D:\1989n\stock_analysis

set PYTHONPATH=D:\1989n\stock_analysis
set LOG_DIR=D:\1989n\.claude\memory\daily
set LOG_FILE=%LOG_DIR%\lint_cron.log

if not exist %LOG_DIR% mkdir %LOG_DIR%

echo [%date% %time%] 工程部 start >> %LOG_FILE%

if "%1"=="--local" (
    python sel_lint.py >> %LOG_FILE% 2>&1
    set EXIT_CODE=%ERRORLEVEL%
) else (
    set FEISHU_SEND_ENABLED=true
    python sel_lint.py >> %LOG_FILE% 2>&1
    set EXIT_CODE=%ERRORLEVEL%
)

echo [%date% %time%] 工程部 exit=%EXIT_CODE% >> %LOG_FILE%

REM Exit codes: 0=LOW 1=MEDIUM 2=HIGH
exit /b %EXIT_CODE%
