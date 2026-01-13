@echo off
chcp 65001 >nul
cd /d "%~dp0\..\.."
echo ============================================================
echo Поиск и восстановление из коммита с файлами парсинга
echo ============================================================
echo.

echo 1. Ищем коммиты с файлом wb_catalog_api.py...
git log --all --oneline -- src/api/wb_catalog_api.py
echo.

echo 2. Ищем коммиты с файлом parse_brands.py...
git log --all --oneline -- parse_brands.py
echo.

echo 3. Ищем коммиты с файлом brands_config.json...
git log --all --oneline -- brands_config.json
echo.

echo 4. Показываем последние 10 коммитов для выбора...
git log --oneline -10
echo.

set /p commit_hash="Введите хеш коммита для восстановления (или нажмите Enter для HEAD~1): "

if "%commit_hash%"=="" (
    set commit_hash=HEAD~1
)

echo.
echo 5. Восстанавливаем файлы из коммита %commit_hash%...
echo.

git checkout %commit_hash% -- src/api/wb_catalog_api.py 2>nul && echo ✓ src/api/wb_catalog_api.py || echo ✗ Не найден
git checkout %commit_hash% -- src/parsers/wb_parser.py 2>nul && echo ✓ src/parsers/wb_parser.py || echo ✗ Не найден
git checkout %commit_hash% -- src/utils/logger.py 2>nul && echo ✓ src/utils/logger.py || echo ✗ Не найден
git checkout %commit_hash% -- parse_brands.py 2>nul && echo ✓ parse_brands.py || echo ✗ Не найден
git checkout %commit_hash% -- run_parse_brands.bat 2>nul && echo ✓ run_parse_brands.bat || echo ✗ Не найден
git checkout %commit_hash% -- run_parse_brands.ps1 2>nul && echo ✓ run_parse_brands.ps1 || echo ✗ Не найден
git checkout %commit_hash% -- brands_config.json 2>nul && echo ✓ brands_config.json || echo ✗ Не найден

echo.
echo 6. Проверка статуса...
git status

echo.
echo ============================================================
echo ✅ Готово!
echo ============================================================
pause
