# Резервная копия БД. Запуск вручную или по расписанию:
#   powershell -ExecutionPolicy Bypass -File backup.ps1
# Ежедневная регистрация в Планировщике задач (один раз):
#   powershell -ExecutionPolicy Bypass -File backup.ps1 -Register
param(
    [switch]$Register
)
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$dbPath = Join-Path $PSScriptRoot "data\trainer.db"
$backupDir = Join-Path $PSScriptRoot "data\backups"
if (-not (Test-Path $backupDir)) { New-Item -ItemType Directory -Path $backupDir | Out-Null }

if ($Register) {
    $action = New-ScheduledTaskAction -Execute "powershell.exe" `
        -Argument "-ExecutionPolicy Bypass -File `"$PSCommandPath`""
    $trigger = New-ScheduledTaskTrigger -Daily -At 2am
    Register-ScheduledTask -TaskName "LexiTrainBackup" -Action $action -Trigger $trigger -Force
    Write-Host "Задача LexiTrainBackup зарегистрирована: ежедневно в 02:00"
    return
}

if (-not (Test-Path $dbPath)) {
    Write-Host "База ещё не создана: $dbPath"
    exit 0
}

$stamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
$dest = Join-Path $backupDir "trainer_$stamp.db"
& .\.venv\Scripts\python -c @"
import sqlite3
src = sqlite3.connect(r'$dbPath')
dst = sqlite3.connect(r'$dest')
src.backup(dst)
src.close(); dst.close()
print('backup ok')
"@

Get-ChildItem $backupDir -Filter "trainer_*.db" |
    Sort-Object Name -Descending |
    Select-Object -Skip 14 |
    Remove-Item -Force

Write-Host "Готово: $dest. Копий в каталоге: $((Get-ChildItem $backupDir -Filter 'trainer_*.db').Count)"
