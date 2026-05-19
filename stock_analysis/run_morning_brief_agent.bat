@echo off
cd /d "D:\1989n\stock_analysis"
echo [%DATE% %TIME%] Morning Brief Agent start >> D:\1989n\stock_data\cognitive_agent.log
D:\Python314\python morning_brief_agent.py >> D:\1989n\stock_data\cognitive_agent.log 2>&1
echo [%DATE% %TIME%] Morning Brief Agent end >> D:\1989n\stock_data\cognitive_agent.log
