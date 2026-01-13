@echo off
chcp 65001 >nul
echo Установка зависимостей проекта...
echo.
cd /d "%~dp0\.."
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
echo.
echo Готово!
pause
