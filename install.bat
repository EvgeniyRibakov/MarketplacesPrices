@echo off
REM Скрипт авто-установки для Windows

echo 🚀 Установка Ozon парсера (LIGHT режим)...
echo.

REM Проверяем Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python не найден. Установите Python 3.8+ и повторите.
    pause
    exit /b 1
)

REM Создаем виртуальное окружение
echo 📦 Создание виртуального окружения...
python -m venv venv

REM Активируем виртуальное окружение
echo 🔧 Активация виртуального окружения...
call venv\Scripts\activate.bat

REM Устанавливаем основные зависимости
echo 📥 Установка основных зависимостей (requirements-core.txt)...
python -m pip install --upgrade pip
pip install -r requirements-core.txt

echo.
echo ✅ Установка завершена (LIGHT режим)
echo.
echo 💡 Для FULL режима (с Playwright fallback):
echo    pip install -r requirements-playwright.txt
echo    playwright install chromium
echo.
echo 🚀 Для запуска парсера:
echo    venv\Scripts\activate.bat
echo    python parse_ozon_sellers.py
echo.
pause
