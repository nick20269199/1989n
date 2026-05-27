@echo off
REM 工程部 Morning Lint — 6项检测 - 08:30
REM 注册: SEL_MorningLint (08:30 每日)
set PYTHONPATH=D:\1989n\stock_analysis

if "%1"=="--local" (
    powershell -WindowStyle Hidden -Command "cmd /c 'D:\Python314\python lint_wrapper.py'"
) else (
    set FEISHU_SEND_ENABLED=true
    powershell -WindowStyle Hidden -Command "cmd /c 'D:\Python314\python lint_wrapper.py'"
)

exit /b %ERRORLEVEL%
