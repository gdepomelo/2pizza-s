# Быстрый запуск демо: waitress + Cloudflare Quick Tunnel (бесплатно, без регистрации).
# Запуск: powershell -ExecutionPolicy Bypass -File start_demo.ps1
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}
& .\.venv\Scripts\python -m pip install -q -r requirements.txt

if (-not (Test-Path ".env")) {
    Copy-Item .env.example .env
    $key = -join ((1..64) | ForEach-Object { '{0:x}' -f (Get-Random -Max 16) })
    (Get-Content .env) -replace '^SECRET_KEY=.*', "SECRET_KEY=$key" | Set-Content .env
    Write-Host "Создан .env со случайным SECRET_KEY"
}

$env:Path = [System.Environment]::GetEnvironmentVariable('Path','Machine') + ';' +
            [System.Environment]::GetEnvironmentVariable('Path','User')
$cf = Get-Command cloudflared -ErrorAction SilentlyContinue
if (-not $cf) {
    Write-Host "Установка cloudflared через winget..."
    winget install --id Cloudflare.cloudflared -e --accept-source-agreements --accept-package-agreements | Out-Null
    $env:Path = [System.Environment]::GetEnvironmentVariable('Path','Machine') + ';' +
                [System.Environment]::GetEnvironmentVariable('Path','User')
    $cf = Get-Command cloudflared -ErrorAction SilentlyContinue
}
if (-not $cf) {
    Write-Error "cloudflared не найден. Скачайте: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"
    exit 1
}

Write-Host "Запуск сервера (waitress)..."
$serverJob = Start-Job -ScriptBlock {
    Set-Location $using:PSScriptRoot
    & .\.venv\Scripts\python.exe run_production.py 2>&1
}
Start-Sleep -Seconds 2

Write-Host "Запуск туннеля Cloudflare..."
$tunnelJob = Start-Job -ScriptBlock {
    param($cfPath)
    & $cfPath tunnel --protocol http2 --url http://127.0.0.1:5000 2>&1
} -ArgumentList $cf.Source

$url = $null
$acc = ""
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Seconds 1
    $acc += (Receive-Job $tunnelJob | Out-String)
    if ($acc -match 'https://[a-zA-Z0-9\-]+\.trycloudflare\.com') {
        $url = $Matches[0]
        break
    }
}

if ($url) {
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Green
    Write-Host "Сайт доступен по ссылке:" -ForegroundColor Green
    Write-Host $url -ForegroundColor Cyan
    Write-Host "Кабинет преподавателя: $url/teacher/login" -ForegroundColor Cyan
    Write-Host "Пароль преподавателя — в файле .env (TEACHER_PASSWORD)" -ForegroundColor Yellow
    Write-Host "Студентам: $url/start" -ForegroundColor Cyan
    Write-Host "Остановить: Ctrl+C в этом окне" -ForegroundColor Yellow
    Write-Host "============================================" -ForegroundColor Green
    Write-Host ""
    try {
        while ($true) { Start-Sleep -Seconds 3600 }
    } finally {
        Stop-Job $serverJob, $tunnelJob -ErrorAction SilentlyContinue
        Remove-Job $serverJob, $tunnelJob -Force -ErrorAction SilentlyContinue
    }
} else {
    Write-Host "URL не появился. Лог туннеля:" -ForegroundColor Red
    Receive-Job $tunnelJob | Select-Object -Last 15
    Stop-Job $serverJob, $tunnelJob -ErrorAction SilentlyContinue
    Remove-Job $serverJob, $tunnelJob -Force -ErrorAction SilentlyContinue
    exit 1
}
