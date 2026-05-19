@echo off
cd /d D:\1989n\stock_analysis
echo [%DATE% %TIME%] Conversation Miner start >> D:\1989n\stock_data\cognitive_agent.log
D:\Python314\python conversation_miner.py >> D:\1989n\stock_data\cognitive_agent.log 2>&1
echo [%DATE% %TIME%] Conversation Miner end >> D:\1989n\stock_data\cognitive_agent.log
