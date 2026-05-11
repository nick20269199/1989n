@echo off
REM A股集合竞价量价统计工具
REM 使用: jingjia [--watch|--schedule]
REM   --watch    持续监控模式(每5分钟刷新)
REM   --schedule 定时模式(每天9:25自动运行)
REM   不加参数   立即运行一次

cd /d "%~dp0"
bun run src/market/index.ts %*
