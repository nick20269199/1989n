$action = New-ScheduledTaskAction -Execute "D:\1989n\stock_analysis\run_bot_v2_guardian.bat"
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 365)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERNAME" -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName "BotV2_Guardian" -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force
Write-Host "Scheduled task BotV2_Guardian created successfully"
