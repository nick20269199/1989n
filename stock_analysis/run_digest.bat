@echo off
REM 工程部 SEL Digest — 09:00 每日 (Lint 之后)
cd /d D:\1989n\stock_analysis
D:\Python314\python sel_digest.py
exit /b %ERRORLEVEL%
