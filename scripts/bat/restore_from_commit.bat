@echo off
chcp 65001 >nul
cd /d "%~dp0\..\.."
echo ============================================================
echo Восстановление файлов из git истории
echo ============================================================
echo.

echo 1. Последние коммиты:
git log --oneline -10
echo.

echo 2. Поиск коммита с файлами парсинга брендов...
git log --all --oneline -- src/api/wb_catalog_api.py | head -n 1
echo.

echo 3. Восстановление файлов из последнего коммита с этими файлами...
echo.

echo Восстанавливаем src/api/wb_catalog_api.py...
git checkout HEAD -- src/api/wb_catalog_api.py 2>nul || git checkout HEAD~1 -- src/api/wb_catalog_api.py 2>nul || git checkout HEAD~2 -- src/api/wb_catalog_api.py 2>nul || echo Не найден

echo Восстанавливаем src/parsers/wb_parser.py...
git checkout HEAD -- src/parsers/wb_parser.py 2>nul || git checkout HEAD~1 -- src/parsers/wb_parser.py 2>nul || git checkout HEAD~2 -- src/parsers/wb_parser.py 2>nul || echo Не найден

echo Восстанавливаем src/utils/logger.py...
git checkout HEAD -- src/utils/logger.py 2>nul || git checkout HEAD~1 -- src/utils/logger.py 2>nul || git checkout HEAD~2 -- src/utils/logger.py 2>nul || echo Не найден

echo Восстанавливаем parse_brands.py...
git checkout HEAD -- parse_brands.py 2>nul || git checkout HEAD~1 -- parse_brands.py 2>nul || git checkout HEAD~2 -- parse_brands.py 2>nul || echo Не найден

echo Восстанавливаем run_parse_brands.bat...
git checkout HEAD -- run_parse_brands.bat 2>nul || git checkout HEAD~1 -- run_parse_brands.bat 2>nul || git checkout HEAD~2 -- run_parse_brands.bat 2>nul || echo Не найден

echo Восстанавливаем run_parse_brands.ps1...
git checkout HEAD -- run_parse_brands.ps1 2>nul || git checkout HEAD~1 -- run_parse_brands.ps1 2>nul || git checkout HEAD~2 -- run_parse_brands.ps1 2>nul || echo Не найден

echo Восстанавливаем brands_config.json...
git checkout HEAD -- brands_config.json 2>nul || git checkout HEAD~1 -- brands_config.json 2>nul || git checkout HEAD~2 -- brands_config.json 2>nul || echo Не найден

echo.
echo 4. Проверка статуса...
git status

echo.
echo ============================================================
echo Если файлы не восстановились, попробуйте:
echo git log --all --oneline -- src/api/wb_catalog_api.py
echo git checkout [HASH] -- src/api/wb_catalog_api.py
echo ============================================================
pause
