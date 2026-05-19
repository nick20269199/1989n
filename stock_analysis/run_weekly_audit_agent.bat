@echo off
cd /d "D:\1989n\stock_analysis"
echo [%DATE% %TIME%] Weekly Audit Agent start >> D:\1989n\stock_data\cognitive_agent.log
D:\Python314\python weekly_audit_agent.py >> D:\1989n\stock_data\cognitive_agent.log 2>&1
echo [%DATE% %TIME%] Weekly Audit Agent end >> D:\1989n\stock_data\cognitive_agent.log
