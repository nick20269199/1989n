<#
.SYNOPSIS
    注册所有 Windows 定时任务 — 由 tools/generate_task_bats.py 自动生成
.DESCRIPTION
    读 data/tasks.json 定义，为所有 enabled win_task 注册/更新计划任务。
    安全: CREATE-only（/F 覆盖已存在），从不先删后建。
#>

$ErrorActionPreference = 'Continue'
$projectDir = "D:\1989n\stock_analysis"

function Register-SimpleTask {
    param($Name, $ScriptPath, $Schedule, $StartTime, $DaysOfWeek, $RepeatInterval, $Duration)
    $extra = @()
    if ($DaysOfWeek) { $extra += '/D', $DaysOfWeek }
    if ($RepeatInterval) { $extra += '/RI', $RepeatInterval; $extra += '/DU', $Duration }
    $args = @('/Create', '/TN', $Name, '/TR', "cmd /c `"$ScriptPath`"",
             '/SC', $Schedule, '/ST', $StartTime) + $extra + @('/F', '/RL', 'HIGHEST')
    $result = & schtasks $args 2>&1
    if ($LASTEXITCODE -eq 0) { Write-Host "[OK] $Name ($StartTime)" -ForegroundColor Green }
    else { Write-Host "[FAIL] $Name : $result" -ForegroundColor Red }
}

function Register-MultiTriggerTask {
    param($Name, $ScriptPath, $Triggers)
    $triggerList = @()
    foreach ($t in $Triggers) {
        if ($t.Days -and $t.Days -ne '') {
            $triggerList += New-ScheduledTaskTrigger -Weekly -At $t.StartTime -DaysOfWeek $t.Days
        } else {
            $triggerList += New-ScheduledTaskTrigger -Daily -At $t.StartTime
        }
    }
    $action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument "/c `"$ScriptPath`""
    Register-ScheduledTask -TaskName $Name -Trigger $triggerList -Action $action -RunLevel Limited -Force | Out-Null
    Write-Host "[OK] $Name (multi-trigger)" -ForegroundColor Green
}

# 午盘30分钟分析
Register-SimpleTask -Name 'StockAnalysis_IntradayMidday' -ScriptPath 'D:\1989n\stock_analysis\run_intraday_midday.bat' -Schedule 'WEEKLY' -StartTime '11:30' -DaysOfWeek 'MON,TUE,WED,THU,FRI'

# 大V雷达 (13:00下午)
Register-SimpleTask -Name 'StockAnalysis_VVRadar_Afternoon' -ScriptPath 'D:\1989n\stock_analysis\run_vv_radar_afternoon.bat' -Schedule 'DAILY' -StartTime '13:00'

# 大V雷达每日管线 (转录+分析+日报)
Register-SimpleTask -Name 'StockAnalysis_VVDaily' -ScriptPath 'D:\1989n\stock_analysis\run_vv_daily_afternoon.bat' -Schedule 'WEEKLY' -StartTime '13:10' -DaysOfWeek 'MON,TUE,WED,THU,FRI'

# 收盘30分钟分析
Register-SimpleTask -Name 'StockAnalysis_IntradayClose' -ScriptPath 'D:\1989n\stock_analysis\run_intraday_close.bat' -Schedule 'WEEKLY' -StartTime '15:00' -DaysOfWeek 'MON,TUE,WED,THU,FRI'

# 收盘复盘 (带退出码修复)
Register-SimpleTask -Name 'StockAnalysis_ClosingReview' -ScriptPath 'D:\1989n\stock_analysis\run_closing_review.bat' -Schedule 'WEEKLY' -StartTime '15:15' -DaysOfWeek 'MON,TUE,WED,THU,FRI'

# 板块日数据采集
Register-SimpleTask -Name 'StockAnalysis_SectorCollect' -ScriptPath 'D:\1989n\stock_analysis\run_sector_collect.bat' -Schedule 'WEEKLY' -StartTime '15:20' -DaysOfWeek 'MON,TUE,WED,THU,FRI'

# 侦查日报 (收盘后探索层)
Register-SimpleTask -Name 'StockAnalysis_Recon' -ScriptPath 'D:\1989n\stock_analysis\run_recon_daily.bat' -Schedule 'WEEKLY' -StartTime '15:30' -DaysOfWeek 'MON,TUE,WED,THU,FRI'

# 技术形态扫描
Register-SimpleTask -Name 'StockAnalysis_TechScan' -ScriptPath 'D:\1989n\stock_analysis\run_tech_scan.bat' -Schedule 'WEEKLY' -StartTime '15:33' -DaysOfWeek 'MON,TUE,WED,THU,FRI'

# 隔夜交易计划生成
Register-SimpleTask -Name 'StockAnalysis_NightlyPlan' -ScriptPath 'D:\1989n\stock_analysis\run_nightly_plan.bat' -Schedule 'WEEKLY' -StartTime '15:40' -DaysOfWeek 'MON,TUE,WED,THU,FRI'

# 决策 T+5 定时回测
Register-SimpleTask -Name 'StockAnalysis_DecisionBacktest' -ScriptPath 'D:\1989n\stock_analysis\run_decision_backtest.bat' -Schedule 'WEEKLY' -StartTime '16:30' -DaysOfWeek 'MON,TUE,WED,THU,FRI'

# 决策梦境推演 — 专家权重动态调整
Register-SimpleTask -Name 'StockAnalysis_Dreamer' -ScriptPath 'D:\1989n\stock_analysis\run_dreamer.bat' -Schedule 'WEEKLY' -StartTime '17:00' -DaysOfWeek 'MON,TUE,WED,THU,FRI'

# 预测追踪闭环
Register-SimpleTask -Name 'StockForecastCloser' -ScriptPath 'D:\1989n\stock_analysis\run_forecast_closer.bat' -Schedule 'WEEKLY' -StartTime '17:05' -DaysOfWeek 'MON,TUE,WED,THU,FRI'

# 晚间总结 + 大V雷达 + 预测闭环
Register-SimpleTask -Name 'StockAnalysis_Evening' -ScriptPath 'D:\1989n\stock_analysis\run_evening.bat' -Schedule 'DAILY' -StartTime '22:00'

# 隔夜分析 (美股+次日展望)
Register-SimpleTask -Name 'StockAnalysis_Overnight' -ScriptPath 'D:\1989n\stock_analysis\run_overnight.bat' -Schedule 'WEEKLY' -StartTime '23:37' -DaysOfWeek 'MON,TUE,WED,THU,FRI'

# 盘前晨报 v2 (AI Agent)
Register-SimpleTask -Name 'Cognitive_MorningBrief' -ScriptPath 'D:\1989n\stock_analysis\run_morning_brief_agent.bat' -Schedule 'WEEKLY' -StartTime '08:37' -DaysOfWeek 'MON,TUE,WED,THU,FRI'

# 集合竞价数据采集
Register-SimpleTask -Name 'StockAnalysis_CallAuction' -ScriptPath 'D:\1989n\stock_analysis\run_call_auction.bat' -Schedule 'WEEKLY' -StartTime '09:26' -DaysOfWeek 'MON,TUE,WED,THU,FRI'

# 热门股票采集 + 大V雷达联动
$triggers = @(
    @{StartTime='09:35'; Days=@('MON','TUE','WED','THU','FRI')},
    @{StartTime='13:00'; Days=@('MON','TUE','WED','THU','FRI')}
)
Register-MultiTriggerTask -Name 'StockAnalysis_HotStocks' -ScriptPath 'D:\1989n\stock_analysis\run_hot_stocks.bat' -Triggers $triggers

# 大V雷达 (09:35)
Register-SimpleTask -Name 'StockAnalysis_VVRadar' -ScriptPath 'D:\1989n\stock_analysis\run_vv_radar.bat' -Schedule 'DAILY' -StartTime '09:35'

# 情报部盘前侦察
Register-SimpleTask -Name 'Intel_Recon' -ScriptPath 'D:\1989n\stock_analysis\run_intel_recon.bat' -Schedule 'WEEKLY' -StartTime '08:32' -DaysOfWeek 'MON,TUE,WED,THU,FRI'

# 情报部收盘推演
Register-SimpleTask -Name 'Intel_Deduce' -ScriptPath 'D:\1989n\stock_analysis\run_intel_deduce.bat' -Schedule 'WEEKLY' -StartTime '15:35' -DaysOfWeek 'MON,TUE,WED,THU,FRI'

# 晚间新闻采集
Register-SimpleTask -Name 'StockNews_Evening' -ScriptPath 'D:\1989n\stock_analysis\run_news_evening.bat' -Schedule 'DAILY' -StartTime '21:55'

# 早间新闻采集
Register-SimpleTask -Name 'StockNews_Morning' -ScriptPath 'D:\1989n\stock_analysis\run_news_morning.bat' -Schedule 'DAILY' -StartTime '08:00'

# 盘中新闻采集 (09:30-15:00 每30分钟)
Register-SimpleTask -Name 'StockNews_Intraday' -ScriptPath 'D:\1989n\stock_analysis\run_news_intraday.bat' -Schedule 'WEEKLY' -StartTime '09:30' -DaysOfWeek 'MON,TUE,WED,THU,FRI' -RepeatInterval '30' -Duration '05:30'

# 夜间健康检查
Register-SimpleTask -Name 'StockNightlyHealth' -ScriptPath 'D:\1989n\stock_analysis\run_nightly_health.bat' -Schedule 'DAILY' -StartTime '00:30'

# 任务哨兵 — 检查定时任务+数据文件健康
Register-SimpleTask -Name 'SEL_TaskSentinel' -ScriptPath 'D:\1989n\stock_analysis\run_task_sentinel.bat' -Schedule 'DAILY' -StartTime '10:00'

# 工程部 Evolve — 知识阅读
Register-SimpleTask -Name 'SEL_EvolveRead' -ScriptPath 'D:\1989n\stock_analysis\run_evolve_read.bat' -Schedule 'DAILY' -StartTime '12:00'

# 工程部 Evolve — 知识操作化
Register-SimpleTask -Name 'SEL_EvolveOp' -ScriptPath 'D:\1989n\stock_analysis\run_evolve_op.bat' -Schedule 'DAILY' -StartTime '12:15'

# 蒸馏队列扫描 — 扫描当日产出加入队列
$triggers = @(
    @{StartTime='15:45'; Days=@('MON','TUE','WED','THU','FRI')},
    @{StartTime='23:45'; Days=''}
)
Register-MultiTriggerTask -Name 'SEL_DistillQueue' -ScriptPath 'D:\1989n\stock_analysis\run_distill_queue.bat' -Triggers $triggers

# 任务仪表盘监控
Register-SimpleTask -Name 'Cognitive_TaskDashboard' -ScriptPath 'D:\1989n\stock_analysis\run_task_dashboard.bat' -Schedule 'DAILY' -StartTime '20:00'

# 对话挖掘
Register-SimpleTask -Name 'Cognitive_ConversationMiner' -ScriptPath 'D:\1989n\stock_analysis\run_conversation_miner.bat' -Schedule 'DAILY' -StartTime '22:30'

# 每日复盘压缩
Register-SimpleTask -Name 'StockAnalysis_DailyCompress' -ScriptPath 'D:\1989n\stock_analysis\run_daily_compress_agent.bat' -Schedule 'DAILY' -StartTime '23:00'

# 系统健康检查
Register-SimpleTask -Name 'StockAnalysis_HealthCheck' -ScriptPath 'D:\1989n\stock_analysis\run_health_check.bat' -Schedule 'DAILY' -StartTime '07:03'

# 工程部 Morning Lint — 6项检测
Register-SimpleTask -Name 'SEL_MorningLint' -ScriptPath 'D:\1989n\stock_analysis\run_lint.bat' -Schedule 'DAILY' -StartTime '08:30'

# 工程部 Digest — 知识库消化
Register-SimpleTask -Name 'SEL_Digest' -ScriptPath 'D:\1989n\stock_analysis\run_digest.bat' -Schedule 'DAILY' -StartTime '09:00'

# 工程部 Connect — 知识连接
Register-SimpleTask -Name 'SEL_Connect' -ScriptPath 'D:\1989n\stock_analysis\run_connect.bat' -Schedule 'DAILY' -StartTime '09:10'

# 工程部 Prune — 知识裁剪
Register-SimpleTask -Name 'SEL_Prune' -ScriptPath 'D:\1989n\stock_analysis\run_prune.bat' -Schedule 'DAILY' -StartTime '09:15'

# 工程部 Maintain — 知识库维护
Register-SimpleTask -Name 'SEL_Maintain' -ScriptPath 'D:\1989n\stock_analysis\run_maintain.bat' -Schedule 'DAILY' -StartTime '09:05'


# ── 验证 ──
Write-Host "`n=== 验证 ===" -ForegroundColor Cyan
$allOk = $true
$checkNames = @(
    'StockAnalysis_IntradayMidday',
    'StockAnalysis_VVRadar_Afternoon',
    'StockAnalysis_VVDaily',
    'StockAnalysis_IntradayClose',
    'StockAnalysis_ClosingReview',
    'StockAnalysis_SectorCollect',
    'StockAnalysis_Recon',
    'StockAnalysis_TechScan',
    'StockAnalysis_NightlyPlan',
    'StockAnalysis_DecisionBacktest',
    'StockAnalysis_Dreamer',
    'StockForecastCloser',
    'StockAnalysis_Evening',
    'StockAnalysis_Overnight',
    'Cognitive_MorningBrief',
    'StockAnalysis_CallAuction',
    'StockAnalysis_HotStocks',
    'StockAnalysis_VVRadar',
    'Intel_Recon',
    'Intel_Deduce',
    'StockNews_Evening',
    'StockNews_Morning',
    'StockNews_Intraday',
    'StockNightlyHealth',
    'SEL_TaskSentinel',
    'SEL_EvolveRead',
    'SEL_EvolveOp',
    'SEL_DistillQueue',
    'Cognitive_TaskDashboard',
    'Cognitive_ConversationMiner',
    'StockAnalysis_DailyCompress',
    'StockAnalysis_HealthCheck',
    'SEL_MorningLint',
    'SEL_Digest',
    'SEL_Connect',
    'SEL_Prune',
    'SEL_Maintain'
)
foreach ($n in $checkNames) {
    $q = schtasks /Query /TN $n /FO LIST 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] $n" -ForegroundColor Green
    } else {
        Write-Host "[MISSING] $n - CRITICAL" -ForegroundColor Red
        $allOk = $false
    }
}
if ($allOk) { Write-Host "`nAll tasks verified OK" -ForegroundColor Green }
else { Write-Host "`nSOME TASKS FAILED VERIFICATION" -ForegroundColor Red; exit 1 }
