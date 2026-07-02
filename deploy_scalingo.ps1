# Автодеплой xscam_bot на Scalingo
$ErrorActionPreference = "Stop"
$App = "xscambot"
$Branch = "main"
$Region = "osc-fr1"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Scalingo = "C:\Users\Александр\.grok\bin\scalingo.exe"
$TokenFile = "C:\Users\Александр\.grok\bin\.scalingo_token"
$EnvFile = "C:\Users\Александр\.grok\bin\xscam_bot\.env"

Set-Location $Root

if (-not (Test-Path $Scalingo)) {
    throw "Scalingo CLI не найден: $Scalingo"
}

function Get-BotToken {
    if (-not (Test-Path $EnvFile)) { return $null }
    foreach ($line in Get-Content $EnvFile) {
        if ($line -match '^\s*BOT_TOKEN\s*=\s*(.+)\s*$') {
            return $Matches[1].Trim()
        }
    }
    return $null
}

function Get-ScalingoToken {
    if ($env:SCALINGO_API_TOKEN) { return $env:SCALINGO_API_TOKEN.Trim() }
    if (Test-Path $TokenFile) { return (Get-Content $TokenFile -Raw).Trim() }
    return $null
}

Write-Host "=== 1. Push на GitHub ===" -ForegroundColor Cyan
git push origin $Branch 2>&1 | Out-Host
if ($LASTEXITCODE -ne 0) { throw "git push failed" }

$token = Get-ScalingoToken
if (-not $token) {
    Write-Host ""
    Write-Host "GitHub push OK. Для Scalingo CLI нужен API token." -ForegroundColor Yellow
    Write-Host "Создайте токен: https://dashboard.scalingo.com/account/tokens" -ForegroundColor Yellow
    Write-Host "Сохраните в: $TokenFile" -ForegroundColor Yellow
    Write-Host "Или: `$env:SCALINGO_API_TOKEN = 'tk-us-...'" -ForegroundColor Yellow
    exit 2
}

Write-Host "=== 2. Login Scalingo ===" -ForegroundColor Cyan
& $Scalingo login --api-token $token 2>&1 | Out-Host
if ($LASTEXITCODE -ne 0) { throw "scalingo login failed" }

Write-Host "=== 3. Env vars ===" -ForegroundColor Cyan
$botToken = Get-BotToken
if ($botToken) {
    & $Scalingo --app $App --region $Region env-set "BOT_TOKEN=$botToken" "PYTHONUNBUFFERED=1" "PROJECT_DIR=xscam_bot" "PROXY=" 2>&1 | Out-Host
} else {
    & $Scalingo --app $App --region $Region env-set "PYTHONUNBUFFERED=1" "PROJECT_DIR=xscam_bot" "PROXY=" 2>&1 | Out-Host
}
& $Scalingo --app $App --region $Region env-unset BUILDPACK_NAME 2>&1 | Out-Null

Write-Host "=== 4. Очистка кэша + деплой ===" -ForegroundColor Cyan
& $Scalingo --app $App --region $Region deployment-delete-cache 2>&1 | Out-Host
& $Scalingo --app $App --region $Region integration-link-manual-deploy $Branch --follow 2>&1 | Out-Host
if ($LASTEXITCODE -ne 0) { throw "manual deploy failed" }

Write-Host "=== 5. Scale worker ===" -ForegroundColor Cyan
& $Scalingo --app $App --region $Region scale web:0 worker:1 2>&1 | Out-Host
Write-Host "=== Готово ===" -ForegroundColor Green