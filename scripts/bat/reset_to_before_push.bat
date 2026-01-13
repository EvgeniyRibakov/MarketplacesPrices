@echo off
chcp 65001 >nul
cd /d "%~dp0\..\.."
echo ============================================================
echo Восстановление локальной версии ДО проблемного коммита
echo ============================================================
echo.
echo ВНИМАНИЕ: Это действие откатит локальные изменения!
echo.
pause

echo 1. Проверка текущего статуса...
git status
echo.

echo 2. Показываем последние коммиты...
git log --oneline -5
echo.

echo 3. Отмена последнего коммита (soft reset - сохраняет изменения)...
echo Выберите действие:
echo [1] Soft reset (сохранить изменения в staging)
echo [2] Hard reset (удалить все изменения)
echo [3] Отмена
echo.
set /p choice="Ваш выбор (1/2/3): "

if "%choice%"=="1" (
    echo Выполняем soft reset...
    git reset --soft HEAD~1
    echo ✓ Готово. Изменения сохранены в staging area.
) else if "%choice%"=="2" (
    echo Выполняем hard reset...
    git reset --hard HEAD~1
    echo ✓ Готово. Все изменения удалены.
) else (
    echo Отменено.
    exit /b 0
)

echo.
echo 4. Текущий статус:
git status
echo.

echo 5. Последние коммиты:
git log --oneline -5
echo.

echo ============================================================
echo ✅ Готово!
echo ============================================================
pause
