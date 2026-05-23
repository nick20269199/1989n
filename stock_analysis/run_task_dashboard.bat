@echo off
cd /d "D:\1989n\stock_analysis"
echo [%DATE% %TIME%] Task Dashboard start >> D:\1989n\stock_data\cognitive_agent.log
D:\Python314\python task_dashboard.py >> D:\1989n\stock_data\cognitive_agent.log 2>&1
echo [%DATE% %TIME%] Task Dashboard end >> D:\1989n\stock_data\cognitive_agent.log
