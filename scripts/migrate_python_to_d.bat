@echo off
echo ============================================
echo  Python D盘迁移 (C:\Python314 -> D:\Python314)
echo ============================================
echo.
echo Close all Python programs before continuing!
echo (VS Code, Claude Code, terminals, etc.)
echo.
pause

echo.
echo [1/3] Checking D:\Python314...
if not exist "D:\Python314\python.exe" (
    echo [ERROR] D:\Python314 not found! Copy it first.
    pause
    exit /b 1
)
echo [OK] D:\Python314 exists

echo [2/3] Renaming C:\Python314 to C:\Python314_old...
ren C:\Python314 Python314_old
if %errorlevel% neq 0 (
    echo [FAIL] Could not rename. Close ALL programs using Python and retry.
    echo        Check Task Manager for python.exe processes.
    pause
    exit /b 1
)
echo [OK] Renamed

echo [3/3] Creating junction C:\Python314 -^> D:\Python314...
mklink /J C:\Python314 D:\Python314
if %errorlevel% equ 0 (
    echo [OK] Junction created!
    echo.
    echo You can now delete C:\Python314_old after verifying everything works.
) else (
    echo [FAIL] Could not create junction.
    echo        Restore: ren C:\Python314_old Python314
)

pause
