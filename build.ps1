<#
.SYNOPSIS
    Сборка и подготовка окружения Keitaro Wrapper (Windows / PowerShell).

.DESCRIPTION
    Скрипт создаёт виртуальное окружение .venv, устанавливает зависимости из
    requirements.txt, при необходимости создаёт .env из .env.example, применяет
    миграции Alembic и (опционально) запускает приложение.

.PARAMETER Run
    После сборки запустить сервер (uvicorn).

.PARAMETER Reload
    Запустить uvicorn с автоперезагрузкой кода (только вместе с -Run).

.PARAMETER Recreate
    Удалить существующее .venv и создать его заново.

.PARAMETER SkipMigrations
    Не применять миграции Alembic.

.PARAMETER Port
    Порт приложения (по умолчанию 8001).

.PARAMETER BindHost
    Адрес привязки сервера (по умолчанию 127.0.0.1).

.EXAMPLE
    .\build.ps1

.EXAMPLE
    .\build.ps1 -Run

.EXAMPLE
    .\build.ps1 -Recreate -Run -Port 8002
#>
[CmdletBinding()]
param(
    [switch]$Run,
    [switch]$Reload,
    [switch]$Recreate,
    [switch]$SkipMigrations,
    [int]$Port = 8001,
    [string]$BindHost = '127.0.0.1'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ProjectRoot = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
Set-Location -LiteralPath $ProjectRoot

$VenvDir = Join-Path $ProjectRoot '.venv'
$VenvPython = Join-Path $VenvDir 'Scripts\python.exe'
$EnvFile = Join-Path $ProjectRoot '.env'
$EnvExample = Join-Path $ProjectRoot '.env.example'
$Requirements = Join-Path $ProjectRoot 'requirements.txt'

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Write-Ok {
    param([string]$Message)
    Write-Host "    $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host "    $Message" -ForegroundColor Yellow
}

function Assert-ExitCode {
    param([string]$Action)
    if ($LASTEXITCODE -ne 0) {
        throw "$Action завершилось с ошибкой (код $LASTEXITCODE)."
    }
}

function Find-Python {
    $candidates = @(
        @{ Exe = 'python'; Prefix = @() },
        @{ Exe = 'py'; Prefix = @('-3') }
    )

    foreach ($candidate in $candidates) {
        $command = Get-Command $candidate.Exe -CommandType Application -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if (-not $command) { continue }

        $versionArgs = @($candidate.Prefix) + @(
            '-c',
            'import sys; print(sys.version_info[0], sys.version_info[1])'
        )

        $output = $null
        $isOk = $false
        try {
            $output = (& $command.Source @versionArgs 2>$null) 2>$null
            $isOk = ($LASTEXITCODE -eq 0)
        }
        catch {
            $isOk = $false
        }

        if (-not $isOk -or -not $output) { continue }

        $parts = ($output | Select-Object -Last 1).ToString().Trim() -split '\s+'
        if ($parts.Count -lt 2) { continue }

        return [pscustomobject]@{
            Exe     = $command.Source
            Prefix  = [string[]]$candidate.Prefix
            Version = ('{0}.{1}' -f $parts[0], $parts[1])
        }
    }

    return $null
}

Write-Step "Проверка окружения"
Write-Ok "Папка проекта: $ProjectRoot"

$python = Find-Python
if (-not $python) {
    throw "Python не найден. Установите Python 3.11+ и добавьте его в PATH (или установите менеджер 'py')."
}

if ([version]$python.Version -lt [version]'3.11') {
    throw "Требуется Python 3.11+ (найден $($python.Version))."
}
Write-Ok "Python $($python.Version)"

if ($Recreate -and (Test-Path -LiteralPath $VenvDir)) {
    Write-Step "Удаление существующего .venv"
    Remove-Item -LiteralPath $VenvDir -Recurse -Force
}

if (-not (Test-Path -LiteralPath $VenvPython)) {
    Write-Step "Создание виртуального окружения .venv"
    & $python.Exe @($python.Prefix) -m venv $VenvDir
    Assert-ExitCode 'Создание .venv'
    Write-Ok ".venv создано"
}
else {
    Write-Ok ".venv уже существует (пересоздать: -Recreate)"
}

Write-Step "Обновление pip"
& $VenvPython -m pip install --quiet --disable-pip-version-check --upgrade pip
Assert-ExitCode 'Обновление pip'

Write-Step "Установка зависимостей"
& $VenvPython -m pip install --disable-pip-version-check -r $Requirements
Assert-ExitCode 'Установка зависимостей'
Write-Ok "Зависимости установлены"

if (-not (Test-Path -LiteralPath $EnvFile) -and (Test-Path -LiteralPath $EnvExample)) {
    Write-Step "Создание .env из .env.example"
    Copy-Item -LiteralPath $EnvExample -Destination $EnvFile
    Write-Warn "Укажите KEITARO_URL и KEITARO_API_KEY в .env или через страницу /admin."
}

if (-not $SkipMigrations) {
    Write-Step "Применение миграций Alembic"
    $alembicExe = Join-Path $VenvDir 'Scripts\alembic.exe'
    if (Test-Path -LiteralPath $alembicExe) {
        & $alembicExe upgrade head
    }
    else {
        & $VenvPython -m alembic upgrade head
    }

    if ($LASTEXITCODE -ne 0) {
        Write-Warn "Миграции не применились (код $LASTEXITCODE)."
        Write-Warn "Если база уже создана, это нормально: при старте приложение выполнит create_all()."
    }
    else {
        Write-Ok "Схема БД актуальна"
    }
}
else {
    Write-Ok "Миграции пропущены (-SkipMigrations)"
}

if ($Run) {
    $appUrl = "http://${BindHost}:${Port}"
    Write-Step "Запуск приложения: $appUrl"
    Write-Host "    Остановка: Ctrl+C" -ForegroundColor DarkGray

    $uvicornArgs = @('-m', 'uvicorn', 'app.main:app', '--host', $BindHost, '--port', "$Port")
    if ($Reload) { $uvicornArgs += '--reload' }

    & $VenvPython @uvicornArgs
    Assert-ExitCode 'Запуск uvicorn'
}
else {
    Write-Step "Сборка завершена"
    Write-Host "Запустить сервер:" -ForegroundColor Green
    Write-Host "    .\build.ps1 -Run"
    Write-Host "    (или: .\.venv\Scripts\python.exe -m uvicorn app.main:app --host $BindHost --port $Port)"
    Write-Host ""
    Write-Host "После запуска откройте http://${BindHost}:${Port}/admin и укажите Keitaro URL и Admin API key."
}
