"""Скрипт для восстановления файлов из конкретного коммита."""
import subprocess
import sys
from pathlib import Path

def run_git_command(cmd: list):
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
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        
        return result.returncode == 0, result.stdout
    except Exception as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        return False, ""

def main():
    """Основная функция."""
    project_root = Path(__file__).parent.parent
    
    print("=" * 70)
    print("Восстановление файлов из git истории")
    print("=" * 70)
    print()
    
    # Показываем последние коммиты
    print("1. Последние коммиты:")
    print("-" * 70)
    success, output = run_git_command(["log", "--oneline", "-10"])
    
    if not success:
        print("Ошибка при получении истории коммитов")
        return 1
    
    print()
    
    # Ищем коммит с файлами парсинга брендов
    print("2. Поиск коммита с файлами парсинга брендов...")
    print("-" * 70)
    
    files_to_find = [
        "src/api/wb_catalog_api.py",
        "parse_brands.py",
        "brands_config.json"
    ]
    
    commit_hash = None
    
    for file_path in files_to_find:
        success, output = run_git_command(["log", "--all", "--oneline", "--", file_path])
        if success and output.strip():
            commit_hash = output.split('\n')[0].split()[0] if output.strip() else None
            if commit_hash:
                print(f"Найден коммит с {file_path}: {commit_hash}")
                break
    
    if not commit_hash:
        print("Не удалось найти коммит с нужными файлами")
        print("Попробуем восстановить из HEAD~1 (предыдущий коммит)")
        commit_hash = "HEAD~1"
    
    print(f"\nИспользуем коммит: {commit_hash}")
    print()
    
    # Показываем что будет восстановлено
    print("3. Файлы в этом коммите:")
    print("-" * 70)
    run_git_command(["ls-tree", "-r", "--name-only", commit_hash])
    print()
    
    # Восстанавливаем файлы
    print("4. Восстановление файлов...")
    print("-" * 70)
    
    files_to_restore = [
        "src/api/wb_catalog_api.py",
        "src/parsers/wb_parser.py",
        "src/utils/logger.py",
        "parse_brands.py",
        "run_parse_brands.bat",
        "run_parse_brands.ps1",
        "brands_config.json",
    ]
    
    restored = []
    failed = []
    
    for file_path in files_to_restore:
        print(f"Восстанавливаем: {file_path}...", end=" ")
        
        success, _ = run_git_command(["checkout", commit_hash, "--", file_path])
        
        if success:
            if (project_root / file_path).exists():
                print("✓")
                restored.append(file_path)
            else:
                print("✗ (файл не создан)")
                failed.append(file_path)
        else:
            print("✗ (не найден в коммите)")
            failed.append(file_path)
    
    print()
    print("=" * 70)
    print(f"Восстановлено: {len(restored)}/{len(files_to_restore)}")
    print("=" * 70)
    
    if restored:
        print("\nУспешно восстановлены:")
        for f in restored:
            print(f"  ✓ {f}")
    
    if failed:
        print("\nНе удалось восстановить:")
        for f in failed:
            print(f"  ✗ {f}")
    
    print("\n5. Текущий статус:")
    print("-" * 70)
    run_git_command(["status"], check=False)
    
    return 0 if not failed else 1

if __name__ == "__main__":
    sys.exit(main())
