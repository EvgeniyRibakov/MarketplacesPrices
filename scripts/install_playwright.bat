@echo off
REM Скрипт для установки Playwright и браузеров
echo ======================================================================
echo Установка Playwright и браузеров для обхода антиботов Ozon
echo ======================================================================
echo.

REM Устанавливаем Playwright и playwright-stealth
echo [1/2] Установка библиотек Playwright...
python -m pip install playwright playwright-stealth

if %ERRORLEVEL% NEQ 0 (
    echo ОШИБКА: Не удалось установить библиотеки Playwright
    pause
    exit /b 1
)

echo.
echo [2/2] Установка браузеров Playwright...
python -m playwright install chromium

if %ERRORLEVEL% NEQ 0 (
    echo ОШИБКА: Не удалось установить браузеры Playwright
    pause
    exit /b 1
)

echo.
echo ======================================================================
echo ✅ Установка завершена успешно!
echo ======================================================================
echo.
pause
