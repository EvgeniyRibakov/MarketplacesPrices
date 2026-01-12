@echo off
chcp 65001 >nul
echo ============================================================
echo Исправление rebase и пуш в main
echo ============================================================
echo.

echo 1. Проверка статуса...
git status
echo.

echo 2. Завершение rebase (если идет)...
git rebase --continue
if errorlevel 1 (
    echo Проблема с rebase. Пробуем прервать...
    git rebase --abort
    echo Rebase прерван. Переходим к обычному коммиту.
    echo.
)

echo 3. Переключение на ветку main...
git checkout main
if errorlevel 1 (
    echo Ошибка переключения на main
    pause
    exit /b 1
)

echo 4. Получение последних изменений из main...
git pull origin main
echo.

echo 5. Проверка, есть ли незакоммиченные изменения...
git status
echo.

echo 6. Добавление всех изменений...
git add .
echo.

echo 7. Создание коммита...
git commit -m "Добавлен парсинг цен по брендам через внутренний API WB

- Создан модуль src/api/wb_catalog_api.py для работы с внутренним endpoint
- Добавлен метод parse_brand_catalog() в WildberriesParser
- Создан скрипт parse_brands.py для парсинга всех брендов
- Добавлена утилита logger.py для настройки логирования
- Обновлена конфигурация брендов в brands_config.json
- Добавлены скрипты для запуска (run_parse_brands.bat, run_parse_brands.ps1)"
echo.

echo 8. Отправка изменений в main...
git push origin main
echo.

echo ============================================================
echo ✅ Готово!
echo ============================================================
pause
