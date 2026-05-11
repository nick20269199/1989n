@echo off
REM Safe rebuild: register tasks via idempotent PS1 (create-or-update, never delete-first)
REM The PS1 uses /F flag to overwrite if exists — no gap where tasks are missing
cd /d D:\1989n\stock_analysis
echo Registering all scheduled tasks (safe mode: create/update, no pre-delete)...
powershell -ExecutionPolicy Bypass -File register_tasks.ps1
if %ERRORLEVEL% NEQ 0 (
    echo CRITICAL: Task registration failed with exit code %ERRORLEVEL%
    echo DO NOT close this window - check the errors above
    pause
    exit /b 1
)
echo Done - all tasks verified.
