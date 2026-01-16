@echo off
chcp 65001 >nul
echo ========================================
echo   Запуск парсера цен Ozon
echo ========================================
echo.

REM Проверяем наличие Python
where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ОШИБКА] Python не найден в PATH
    echo Установите Python с https://www.python.org/downloads/
    echo При установке отметьте "Add Python to PATH"
    pause
    exit /b 1
)

REM Переходим в корневую директорию проекта
cd /d "%~dp0\.."

echo Запуск парсера...
echo.

python parse_ozon_sellers.py

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================
    echo   Парсинг завершен успешно!
    echo ========================================
) else (
    echo.
    echo ========================================
    echo   Ошибка при выполнении парсинга
    echo ========================================
)

echo.
pause
