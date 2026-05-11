# Register Windows Task Scheduler tasks for financial news collection
# Run as Administrator: right-click PowerShell -> Run as Administrator -> execute this script

$ErrorActionPreference = "Stop"
$pythonExe = "D:\Python314\python.exe"
$scriptPath = "D:\1989n\stock_analysis\news_scheduler.py"
$workDir = "D:\1989n\stock_analysis"
$taskFolder = "\StockAnalysis"

# Ensure task folder exists
$folder = Get-ScheduledTask -TaskPath $taskFolder -ErrorAction SilentlyContinue
if (-not $folder) {
    Write-Host "Creating task folder: $taskFolder"
    # Create a dummy task to create the folder
    $dummyAction = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c echo placeholder"
    $dummyTrigger = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddYears(10))
    $dummyPrincipal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive
    $dummyTask = Register-ScheduledTask -Action $dummyAction -Trigger $dummyTrigger `
        -TaskName "_dummy" -TaskPath $taskFolder -Principal $dummyPrincipal -Force
    Unregister-ScheduledTask -TaskName "_dummy" -TaskPath $taskFolder -Confirm:$false
}

function Register-NewsTask {
    param([string]$Name, $Trigger, [string]$Arg)

    $action = New-ScheduledTaskAction -Execute $pythonExe `
        -Argument "`"$scriptPath`" $Arg" `
        -WorkingDirectory $workDir

    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -RunOnlyIfNetworkAvailable `
        -MultipleInstances IgnoreNew `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

    $principal = New-ScheduledTaskPrincipal `
        -UserId "$env:USERDOMAIN\$env:USERNAME" `
        -LogonType Interactive `
        -RunLevel Limited

    Register-ScheduledTask -TaskName $Name -TaskPath $taskFolder `
        -Action $action -Trigger $Trigger `
        -Settings $settings -Principal $principal -Force | Out-Null
    Write-Host "  [OK] $Name"
}

# ============================================================
# 1. Intraday flash news - Mon-Fri 9:30-15:00 every 30 minutes
# ============================================================
$trigger1 = New-ScheduledTaskTrigger -Weekly `
    -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday `
    -At "09:30"
$trigger1.Repetition = New-ScheduledTaskRepetition `
    -Interval (New-TimeSpan -Minutes 30) `
    -Duration (New-TimeSpan -Hours 5 -Minutes 30)

Register-NewsTask "StockNews_Intraday" $trigger1 "intraday"

# ============================================================
# 2. Morning summary - daily at 08:00
# ============================================================
$trigger2 = New-ScheduledTaskTrigger -Daily -At "08:00"
Register-NewsTask "StockNews_Morning" $trigger2 "morning"

# ============================================================
# 3. Evening summary - daily at 22:00
# ============================================================
$trigger3 = New-ScheduledTaskTrigger -Daily -At "22:00"
Register-NewsTask "StockNews_Evening" $trigger3 "evening"

Write-Host ""
Write-Host "All tasks registered. Verify: taskschd.msc -> StockAnalysis"
Write-Host ""
Write-Host "Test run commands:"
Write-Host "  Start-ScheduledTask -TaskName 'StockNews_Intraday' -TaskPath '\StockAnalysis\'"
Write-Host "  Start-ScheduledTask -TaskName 'StockNews_Morning' -TaskPath '\StockAnalysis\'"
Write-Host "  Start-ScheduledTask -TaskName 'StockNews_Evening' -TaskPath '\StockAnalysis\'"
