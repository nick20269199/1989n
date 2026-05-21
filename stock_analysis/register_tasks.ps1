# Register all stock_analysis scheduled tasks
# Usage: powershell -ExecutionPolicy Bypass -File register_tasks.ps1
# Design: CREATE-only with /F (force update), NEVER delete before create
# Encoding: ASCII-safe, no non-ASCII chars to avoid GBK/UTF-8 corruption

$projectDir = "D:\1989n\stock_analysis"
$pythonExe = "D:\Python314\python.exe"

$tasks = @(
    # ── 前厅部 ───────────────────────────────────────────────────────
    @{
        Name = "StockAnalysis_HealthCheck"
        Script = "$projectDir\run_health_check.bat"
        Time = "07:03"
    },
    @{
        Name = "StockAnalysis_MorningBrief"
        Script = "$projectDir\run_morning_brief.bat"
        Time = "22:40"
    },
    @{
        Name = "StockAnalysis_CallAuction"
        Script = "$projectDir\run_call_auction.bat"
        Time = "09:26"
    },
    @{
        Name = "StockAnalysis_HotStocks"
        Script = "$projectDir\run_hot_stocks.bat"
        Time = "09:35 / 13:00 # 见下方 PS 多触发器注册"
    },
    @{
        Name = "StockAnalysis_IntradayMidday"
        Script = "$projectDir\run_intraday_midday.bat"
        Time = "11:30"
    },
    @{
        Name = "StockAnalysis_IntradayClose"
        Script = "$projectDir\run_intraday_close.bat"
        Time = "15:00"
    },
    @{
        Name = "StockAnalysis_ClosingReview"
        Script = "$projectDir\run_closing_review.bat"
        Time = "15:15"
    },
    @{
        Name = "StockAnalysis_TechScan"
        Script = "$projectDir\run_tech_scan.bat"
        Time = "15:30"
    },
    @{
        Name = "StockAnalysis_NightlyPlan"
        Script = "$projectDir\run_nightly_plan.bat"
        Time = "15:40"
    },
    @{
        Name = "StockAnalysis_Evening"
        Script = "$projectDir\run_evening.bat"
        Time = "22:00"
    },
    @{
        Name = "StockAnalysis_Overnight"
        Script = "$projectDir\run_overnight.bat"
        Time = "23:30"
    },
    # ── 后勤部 新闻采集 ──────────────────────────────────────────────────
    @{
        Name = "StockNews_Morning"
        Script = "$projectDir\run_news_morning.bat"
        Time = "08:00"
    },
    @{
        Name = "StockNews_Intraday"
        Script = "$projectDir\run_news_intraday.bat"
        Time = "09:30 / 每30分钟 至 15:00"
    },
    @{
        Name = "StockNews_Evening"
        Script = "$projectDir\run_news_evening.bat"
        Time = "21:55"
    },
    # ── 后勤部 健康监控 + 认知任务 ──────────────────────────────────────
    @{
        Name = "StockNightlyHealth"
        Script = "$projectDir\run_nightly_health.bat"
        Time = "00:30"
    },
    @{
        Name = "Cognitive_TaskDashboard"
        Script = "$projectDir\run_task_dashboard.bat"
        Time = "20:00"
    },
    @{
        Name = "Cognitive_ConversationMiner"
        Script = "$projectDir\run_conversation_miner.bat"
        Time = "22:30"
    },
    @{
        Name = "Cognitive_MorningBrief"
        Script = "$projectDir\run_morning_brief_agent.bat"
        Time = "08:37"
    },
    # ── 工程部 Morning Maintenance ──────────────────────────────────────
    # 时间线: 08:30→09:00→09:05→09:10→09:15
    # 全部在前厅部 09:26 CallAuction 之前完成
    @{
        Name = "SEL_MorningLint"
        Script = "$projectDir\run_lint.bat"
        Time = "08:30"
    },
    @{
        Name = "SEL_Digest"
        Script = "$projectDir\run_digest.bat"
        Time = "09:00"
    },
    @{
        Name = "SEL_Maintain"
        Script = "$projectDir\run_maintain.bat"
        Time = "09:05"
    },
    @{
        Name = "SEL_Connect"
        Script = "$projectDir\run_connect.bat"
        Time = "09:10"
    },
    @{
        Name = "SEL_Prune"
        Script = "$projectDir\run_prune.bat"
        Time = "09:15"
    },
    # ── 工程部 Midday Evolution ────────────────────────────────────────
    # 休盘时段执行，避开前厅部交易时段
    @{
        Name = "SEL_EvolveRead"
        Script = "$projectDir\run_evolve_read.bat"
        Time = "12:00"
    },
    @{
        Name = "SEL_EvolveOp"
        Script = "$projectDir\run_evolve_op.bat"
        Time = "12:15"
    }
)

$success = 0
$failed = 0

foreach ($task in $tasks) {
    $taskName = $task.Name
    $scriptPath = $task.Script
    $taskTime = $task.Time

    if ($taskName -eq "StockAnalysis_HotStocks") {
        $displayTime = "09:35 / 13:00"
    } elseif ($taskName -eq "StockNews_Intraday") {
        $displayTime = "09:30 / 每30分钟 至 15:00"
    } else {
        $displayTime = $taskTime
    }

    if ($taskName -eq "StockAnalysis_HotStocks") {
        # 使用 PowerShell 注册多触发器（09:35 / 13:00 各一次）
        $t1 = New-ScheduledTaskTrigger -Daily -At 09:35
        $t2 = New-ScheduledTaskTrigger -Daily -At 13:00
        $act = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c $scriptPath"
        Register-ScheduledTask -TaskName $taskName -Trigger @($t1, $t2) -Action $act -RunLevel Limited -Force | Out-Null
    } elseif ($taskName -eq "StockNews_Intraday") {
        # 盘中 09:30→每30分钟重复→至15:00
        schtasks /Create /TN $taskName `
            /TR "cmd /c `"$scriptPath`"" `
            /SC DAILY `
            /ST 09:30 `
            /RI 30 `
            /DU 05:30 `
            /F `
            /RL HIGHEST
    } else {
        schtasks /Create /TN $taskName `
            /TR "cmd /c `"$scriptPath`"" `
            /SC DAILY `
            /ST $taskTime `
            /F `
            /RL HIGHEST
    }

    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] $taskName ($displayTime)" -ForegroundColor Green
        $success++
    } else {
        Write-Host "[FAIL] $taskName ($displayTime) - exit code: $LASTEXITCODE" -ForegroundColor Red
        $failed++
    }
}

Write-Host ""
Write-Host "=== Result: $success created, $failed failed ===" -ForegroundColor Cyan

# Validation: verify all tasks exist
Write-Host ""
Write-Host "=== Verification ===" -ForegroundColor Cyan
$allOk = $true
foreach ($task in $tasks) {
    $query = schtasks /Query /TN $task.Name /FO LIST 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] $($task.Name) exists" -ForegroundColor Green
    } else {
        Write-Host "[MISSING] $($task.Name) - CRITICAL" -ForegroundColor Red
        $allOk = $false
    }
}

if ($allOk) {
    Write-Host "All tasks verified OK" -ForegroundColor Green
} else {
    Write-Host "SOME TASKS FAILED VERIFICATION - DO NOT IGNORE" -ForegroundColor Red
}
