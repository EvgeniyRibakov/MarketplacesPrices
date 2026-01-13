"""Скрипт для восстановления удалённых файлов из git истории."""
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
    print("Восстановление удалённых файлов из git истории")
    print("=" * 70)
    print()
    
    # Список файлов для восстановления
    files_to_restore = [
        "src/api/wb_catalog_api.py",
        "src/parsers/wb_parser.py",
        "src/utils/logger.py",
        "parse_brands.py",
        "run_parse_brands.bat",
        "run_parse_brands.ps1",
        "brands_config.json",
    ]
    
    print("1. Поиск последнего коммита с этими файлами...")
    print("-" * 70)
    
    # Ищем коммит, где были эти файлы
    success, output = run_git_command(["log", "--all", "--oneline", "--", "src/api/wb_catalog_api.py"])
    
    if not success or not output.strip():
        print("Файлы не найдены в истории git. Нужно пересоздать их.")
        return 1
    
    # Берём первый коммит из списка
    commit_hash = output.split('\n')[0].split()[0] if output.strip() else None
    
    if not commit_hash:
        print("Не удалось найти коммит с файлами")
        return 1
    
    print(f"Найден коммит: {commit_hash}")
    print()
    
    print("2. Восстановление файлов...")
    print("-" * 70)
    
    restored = []
    failed = []
    
    for file_path in files_to_restore:
        print(f"Восстанавливаем: {file_path}...", end=" ")
        
        # Пробуем восстановить из коммита
        success, _ = run_git_command(["checkout", commit_hash, "--", file_path])
        
        if success:
            # Проверяем, что файл действительно восстановился
            if (project_root / file_path).exists():
                print("✓")
                restored.append(file_path)
            else:
                print("✗ (файл не создан)")
                failed.append(file_path)
        else:
            print("✗")
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
        print("\nЭти файлы нужно будет пересоздать вручную.")
    
    print("\n3. Проверка статуса...")
    print("-" * 70)
    run_git_command(["status"], check=False)
    
    return 0 if not failed else 1

if __name__ == "__main__":
    sys.exit(main())
