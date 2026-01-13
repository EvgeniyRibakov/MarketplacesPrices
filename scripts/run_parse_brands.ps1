# Скрипт для запуска парсинга брендов
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$pythonCommands = @("python", "py", "python3")

foreach ($cmd in $pythonCommands) {
    try {
        $version = & $cmd --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Найден Python: $cmd" -ForegroundColor Green
            Write-Host "Версия: $version" -ForegroundColor Green
            Write-Host "Запускаем parse_brands.py..." -ForegroundColor Yellow
            Push-Location (Split-Path -Parent $MyInvocation.MyCommand.Path)\.\..
            & $cmd parse_brands.py
            Pop-Location
            exit $LASTEXITCODE
        }
    } catch {
        continue
    }
}

Write-Host "Ошибка: Python не найден. Установите Python и добавьте его в PATH." -ForegroundColor Red
exit 1
