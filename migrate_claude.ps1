$log = "D:\1989n\migrate_result.txt"
"Start: $(Get-Date)" | Out-File $log

# Check if .claude is in use
$inUse = $false
try {
    $testFile = "$env:USERPROFILE\.claude\.migrate_test"
    New-Item -Path $testFile -ItemType File -Force -ErrorAction Stop | Out-Null
    Remove-Item $testFile -Force
    "Directory is not locked" | Out-File $log -Append
} catch {
    $inUse = $true
    "ERROR: .claude is locked by another process. Close VS Code and all Claude Code windows first." | Out-File $log -Append
}

if ($inUse) {
    "Migration FAILED - directory in use" | Out-File $log -Append
    Write-Host "FAILED - Close VS Code first, then re-run this script"
    Read-Host "Press Enter to exit"
    exit 1
}

# Remove C:\.claude
try {
    Remove-Item -Path "$env:USERPROFILE\.claude" -Recurse -Force -ErrorAction Stop
    "Deleted C:\.claude" | Out-File $log -Append
} catch {
    "ERROR deleting C:\.claude: $_" | Out-File $log -Append
    Read-Host "Press Enter to exit"
    exit 1
}

# Create junction
try {
    New-Item -Path "$env:USERPROFILE\.claude" -ItemType Junction -Target "D:\1989n\.claude" -Force -ErrorAction Stop
    "Junction created: $env:USERPROFILE\.claude -> D:\1989n\.claude" | Out-File $log -Append
} catch {
    "ERROR creating junction: $_" | Out-File $log -Append
    Read-Host "Press Enter to exit"
    exit 1
}

# Verify
if (Test-Path "$env:USERPROFILE\.claude\memory") {
    "VERIFY: OK - junction works correctly" | Out-File $log -Append
    Write-Host "SUCCESS! Migration complete."
} else {
    "VERIFY: FAILED - junction may not be working" | Out-File $log -Append
    Write-Host "VERIFY FAILED"
}

"End: $(Get-Date)" | Out-File $log -Append
Read-Host "Press Enter to exit"
