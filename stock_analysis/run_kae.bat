@echo off
REM 汲智引擎(KAE) 日管线 - 缺口审计→归档搜索→吸收→提案
cd /d D:\1989n\stock_analysis
D:\Python314\python knowledge_runner.py pipeline >> D:\1989n\stock_data\knowledge\kae.log 2>&1
