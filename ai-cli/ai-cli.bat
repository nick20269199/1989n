@echo off
REM 请先设置环境变量: set DEEPSEEK_API_KEY=your_key_here
cd /d D:\1989n\ai-cli
bun run src/cli.ts %*
