@echo off
chcp 65001 >nul
echo ========================================
echo  Claude Code 数据迁移 C盘 -> D盘
echo ========================================
echo.
echo 请确认 Claude Code 已经完全关闭！
echo （关闭 VS Code 窗口即可）
echo.
pause

echo.
echo 正在删除 C盘 .claude ...
rmdir /s /q "C:\Users\1989n\.claude"
if exist "C:\Users\1989n\.claude" (
    echo [失败] 删除失败，可能有文件仍被占用。请确保 Claude Code 已完全关闭后重试。
    pause
    exit /b 1
)
echo [完成] C盘目录已删除

echo.
echo 正在创建联结...
mklink /J "C:\Users\1989n\.claude" "D:\1989n\.claude"
if exist "C:\Users\1989n\.claude\memory" (
    echo [成功] 联结创建成功！数据已迁移到 D盘。
) else (
    echo [失败] 联结可能未正确创建，请检查。
)
echo.
pause
