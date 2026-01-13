# Скрипт для установки зависимостей проекта
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "Установка зависимостей проекта..." -ForegroundColor Yellow
Write-Host ""

$pythonCommands = @("python", "py", "python3")

foreach ($cmd in $pythonCommands) {
    try {
        $version = & $cmd --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Найден Python: $cmd" -ForegroundColor Green
            Write-Host "Версия: $version" -ForegroundColor Green
            
            Push-Location (Split-Path -Parent $MyInvocation.MyCommand.Path)\.\..
            
            Write-Host "Обновление pip..." -ForegroundColor Yellow
            & $cmd -m pip install --upgrade pip
            
            Write-Host "Установка зависимостей из requirements.txt..." -ForegroundColor Yellow
            & $cmd -m pip install -r requirements.txt
            
            Pop-Location
            
            Write-Host ""
            Write-Host "Готово!" -ForegroundColor Green
            exit $LASTEXITCODE
        }
    } catch {
        continue
    }
}

Write-Host "Ошибка: Python не найден. Установите Python и добавьте его в PATH." -ForegroundColor Red
exit 1
