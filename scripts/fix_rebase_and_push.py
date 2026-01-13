"""Скрипт для исправления rebase и пуша в main."""
import subprocess
import sys
from pathlib import Path

def run_git_command(cmd: list, check=True):
    """Выполняет git команду."""
    try:
        project_root = Path(__file__).parent.parent
        result = subprocess.run(
            ["git"] + cmd,
            cwd=project_root,
            capture_output=True,
            text=True,
            encoding="utf-8"
        )
        
        if result.stdout:
            print(result.stdout)
        if result.stderr and result.returncode != 0:
            print(result.stderr, file=sys.stderr)
        
        if check and result.returncode != 0:
            return False
        
        return True
    except Exception as e:
        print(f"Ошибка при выполнении git команды: {e}", file=sys.stderr)
        return False

def main():
    """Основная функция."""
    project_root = Path(__file__).parent.parent
    
    print("=" * 70)
    print("Исправление rebase и пуш в main")
    print("=" * 70)
    print()
    
    # Проверяем статус
    print("1. Проверка статуса...")
    print("-" * 70)
    run_git_command(["status"], check=False)
    print()
    
    # Пробуем завершить rebase, если идет
    print("2. Проверка rebase...")
    print("-" * 70)
    status_result = subprocess.run(
        ["git", "status"],
        cwd=project_root,
        capture_output=True,
        text=True,
        encoding="utf-8"
    )
    
    if "rebase" in status_result.stdout.lower():
        print("Обнаружен активный rebase. Завершаем...")
        if not run_git_command(["rebase", "--continue"], check=False):
            print("Не удалось завершить rebase. Прерываем...")
            run_git_command(["rebase", "--abort"], check=False)
    else:
        print("Активного rebase не обнаружено")
    print()
    
    # Переключаемся на main
    print("3. Переключение на ветку main...")
    print("-" * 70)
    if not run_git_command(["checkout", "main"]):
        print("Ошибка: не удалось переключиться на main")
        return 1
    print("✓ Переключено на main")
    print()
    
    # Получаем последние изменения
    print("4. Получение последних изменений из main...")
    print("-" * 70)
    run_git_command(["pull", "origin", "main"], check=False)
    print()
    
    # Проверяем статус
    print("5. Проверка изменений...")
    print("-" * 70)
    run_git_command(["status"], check=False)
    print()
    
    # Добавляем изменения
    print("6. Добавление всех изменений...")
    print("-" * 70)
    run_git_command(["add", "."])
    print("✓ Изменения добавлены")
    print()
    
    # Коммитим
    print("7. Создание коммита...")
    print("-" * 70)
    commit_message = """Добавлен парсинг цен по брендам через внутренний API WB

- Создан модуль src/api/wb_catalog_api.py для работы с внутренним endpoint
- Добавлен метод parse_brand_catalog() в WildberriesParser
- Создан скрипт parse_brands.py для парсинга всех брендов
- Добавлена утилита logger.py для настройки логирования
- Обновлена конфигурация брендов в brands_config.json
- Организована структура проекта (docs/, scripts/)
"""
    
    if not run_git_command(["commit", "-m", commit_message], check=False):
        print("Нет изменений для коммита или ошибка коммита")
    else:
        print("✓ Коммит создан")
    print()
    
    # Пушим
    print("8. Отправка изменений в main...")
    print("-" * 70)
    if not run_git_command(["push", "origin", "main"]):
        print("Ошибка при отправке изменений")
        return 1
    
    print("✓ Изменения отправлены в main")
    print()
    
    print("=" * 70)
    print("✅ Все операции выполнены успешно!")
    print("=" * 70)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
