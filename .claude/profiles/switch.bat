@echo off
if "%1"=="" (
    echo Usage: switch deepseek  or  switch gpt
    exit /b 1
)

if /i "%1"=="deepseek" (
    copy /y "%~dp0deepseek.json" "%~dp0..\settings.json" >nul
    echo [OK] Switched to DeepSeek V4-Pro
) else if /i "%1"=="gpt" (
    copy /y "%~dp0gpt.json" "%~dp0..\settings.json" >nul
    echo [OK] Switched to GPT (via proxy 127.0.0.1:15721)
) else (
    echo Unknown model: %1
    echo Usage: switch deepseek  or  switch gpt
    exit /b 1
)
echo.
echo Restart Claude Code for the change to take effect.
