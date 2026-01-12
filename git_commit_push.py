"""Скрипт для коммита и пуша изменений через Python."""
import subprocess
import sys
from pathlib import Path

def run_git_command(cmd: list):
    """Выполняет git команду."""
    try:
        result = subprocess.run(
            ["git"] + cmd,
            cwd=Path(__file__).parent,
            capture_output=True,
            text=True,
            encoding="utf-8"
        )
        
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        
        return result.returncode == 0
    except Exception as e:
        print(f"Ошибка при выполнении git команды: {e}", file=sys.stderr)
        return False

def main():
    """Основная функция."""
    print("=" * 70)
    print("Git операции: коммит и пуш изменений")
    print("=" * 70)
    print()
    
    # Проверяем статус
    print("1. Проверка статуса репозитория...")
    print("-" * 70)
    if not run_git_command(["status"]):
        print("Ошибка: не удалось выполнить git status")
        return 1
    
    print()
    
    # Добавляем все изменения
    print("2. Добавление всех изменений...")
    print("-" * 70)
    if not run_git_command(["add", "."]):
        print("Ошибка: не удалось выполнить git add")
        return 1
    
    print("✓ Изменения добавлены")
    print()
    
    # Коммитим
    print("3. Создание коммита...")
    print("-" * 70)
    commit_message = """Добавлен парсинг цен по брендам через внутренний API WB

- Создан модуль src/api/wb_catalog_api.py для работы с внутренним endpoint
- Добавлен метод parse_brand_catalog() в WildberriesParser
- Создан скрипт parse_brands.py для парсинга всех брендов
- Добавлена утилита logger.py для настройки логирования
- Обновлена конфигурация брендов в brands_config.json
- Добавлены скрипты для запуска (run_parse_brands.bat, run_parse_brands.ps1)
"""
    
    if not run_git_command(["commit", "-m", commit_message]):
        print("Ошибка: не удалось выполнить git commit")
        print("Возможно, нет изменений для коммита")
        return 1
    
    print("✓ Коммит создан")
    print()
    
    # Пушим в main
    print("4. Отправка изменений в ветку main...")
    print("-" * 70)
    if not run_git_command(["push", "origin", "main"]):
        print("Ошибка: не удалось выполнить git push")
        print("Возможно, нужно настроить remote или есть конфликты")
        return 1
    
    print("✓ Изменения отправлены в main")
    print()
    
    print("=" * 70)
    print("✅ Все операции выполнены успешно!")
    print("=" * 70)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
