# Register all stock_analysis scheduled tasks
# Usage: powershell -ExecutionPolicy Bypass -File register_tasks.ps1
# Design: CREATE-only with /F (force update), NEVER delete before create
# Encoding: ASCII-safe only (avoid GBK/UTF-8 corruption)

$projectDir = "D:\1989n\stock_analysis"
$pythonExe = "D:\Python314\python.exe"

$tasks = @(
    # -- Front Office -------------------------------------------------
    @{
        Name = "StockAnalysis_HealthCheck"
        Script = "$projectDir\run_health_check.bat"
        Time = "07:03"
    },
    @{
        Name = "StockAnalysis_CallAuction"
        Script = "$projectDir\run_call_auction.bat"
        Time = "09:26"
    },
    @{
        Name = "StockAnalysis_HotStocks"
        Script = "$projectDir\run_hot_stocks.bat"
        Time = "09:35 / 13:00"
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
        Name = "StockAnalysis_Recon"
        Script = "$projectDir\run_recon_daily.bat"
        Time = "15:30"
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
    # -- Logistics News -----------------------------------------------
    @{
        Name = "StockNews_Morning"
        Script = "$projectDir\run_news_morning.bat"
        Time = "08:00"
    },
    @{
        Name = "StockNews_Intraday"
        Script = "$projectDir\run_news_intraday.bat"
        Time = "09:30 / every 30min to 15:00"
    },
    @{
        Name = "StockNews_Evening"
        Script = "$projectDir\run_news_evening.bat"
        Time = "21:55"
    },
    # -- Logistics Health + Cognitive ---------------------------------
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
    # -- Engineering Morning Maintenance -------------------------------
    # Timeline: 08:30->09:00->09:05->09:10->09:15
    # All before Front Office 09:26 CallAuction
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
    # -- Engineering Midday Evolution ---------------------------------
    # Runs during lunch break to avoid trading hours
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
        $displayTime = "09:30 / every 30min to 15:00"
    } else {
        $displayTime = $taskTime
    }

    if ($taskName -eq "StockAnalysis_HotStocks") {
        # Use PowerShell to register multi-trigger (09:35 / 13:00)
        $t1 = New-ScheduledTaskTrigger -Daily -At 09:35
        $t2 = New-ScheduledTaskTrigger -Daily -At 13:00
        $act = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c $scriptPath"
        Register-ScheduledTask -TaskName $taskName -Trigger @($t1, $t2) -Action $act -RunLevel Limited -Force | Out-Null
    } elseif ($taskName -eq "StockNews_Intraday") {
        # Intraday 09:30->every 30min->until 15:00
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
