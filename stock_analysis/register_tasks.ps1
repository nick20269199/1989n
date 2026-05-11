# Register all stock_analysis scheduled tasks
# Usage: powershell -ExecutionPolicy Bypass -File register_tasks.ps1
# Design: CREATE-only with /F (force update), NEVER delete before create
# Encoding: ASCII-safe, no non-ASCII chars to avoid GBK/UTF-8 corruption

$projectDir = "D:\1989n\stock_analysis"
$pythonExe = "D:\Python314\python.exe"

$tasks = @(
    @{
        Name = "StockAnalysis_MorningBrief"
        Script = "$projectDir\run_morning_brief.bat"
        Time = "09:00"
    },
    @{
        Name = "StockAnalysis_HotStocks"
        Script = "$projectDir\run_hot_stocks.bat"
        Time = "09:15"
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
        Name = "StockAnalysis_Overnight"
        Script = "$projectDir\run_overnight.bat"
        Time = "23:30"
    }
)

$success = 0
$failed = 0

foreach ($task in $tasks) {
    $taskName = $task.Name
    $scriptPath = $task.Script
    $taskTime = $task.Time

    if ($taskName -eq "StockAnalysis_HotStocks") {
        schtasks /Create /TN $taskName `
            /TR "cmd /c `"$scriptPath`"" `
            /SC HOURLY /MO 1 `
            /ST $taskTime `
            /ET "15:30" `
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
        Write-Host "[OK] $taskName ($taskTime)" -ForegroundColor Green
        $success++
    } else {
        Write-Host "[FAIL] $taskName - exit code: $LASTEXITCODE" -ForegroundColor Red
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
