# Fix Python PATH - Remove C:\Python314 from System PATH, keep D:\Python314
# Run as Administrator: right-click PowerShell → Run as Administrator
# Or: powershell -ExecutionPolicy Bypass -File fix_python_path_admin.ps1

$ErrorActionPreference = "Stop"

Write-Host "=== Python PATH Migration: C: → D: ===" -ForegroundColor Cyan
Write-Host ""

# 1. Remove C:\Python314 from System PATH
$sysPath = [Environment]::GetEnvironmentVariable('Path', 'Machine')
$sysEntries = $sysPath -split ';'
$newSysEntries = $sysEntries | Where-Object { $_ -notmatch 'C:\\Python314' }
$newSysPath = ($newSysEntries -join ';').TrimEnd(';')

if ($sysPath -ne $newSysPath) {
    [Environment]::SetEnvironmentVariable('Path', $newSysPath, 'Machine')
    Write-Host "[OK] Removed C:\Python314 from System PATH" -ForegroundColor Green
} else {
    Write-Host "[SKIP] C:\Python314 not in System PATH" -ForegroundColor Yellow
}

# 2. Ensure D:\Python314 is in User PATH at front
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
$userEntries = $userPath -split ';'
$newUserEntries = $userEntries | Where-Object { $_ -notmatch 'D:\\Python314' }
$newUserPath = 'D:\Python314\Scripts;D:\Python314;' + ($newUserEntries -join ';').TrimEnd(';')
[Environment]::SetEnvironmentVariable('Path', $newUserPath, 'User')
Write-Host "[OK] D:\Python314 at front of User PATH" -ForegroundColor Green

# 3. Verify
Write-Host ""
Write-Host "=== Verification ===" -ForegroundColor Cyan
Write-Host "New System PATH (Python entries):"
([Environment]::GetEnvironmentVariable('Path', 'Machine') -split ';' | Select-String 'Python')

Write-Host ""
Write-Host "New User PATH (Python entries):"
([Environment]::GetEnvironmentVariable('Path', 'User') -split ';' | Select-String 'Python')

Write-Host ""
Write-Host "NOTE: Restart terminal/IDE for changes to take effect." -ForegroundColor Yellow
Write-Host "After restart, 'python' should resolve to D:\Python314\python.exe" -ForegroundColor Yellow
