"""Скрипт для организации файлов по папкам."""
import shutil
from pathlib import Path

# Структура папок
STRUCTURE = {
    "docs": [
        "README_BRANDS_PARSING.md",
        "GIT_INSTRUCTIONS.md",
        "FIX_REBASE_README.md",
        "RESTORE_FILES_INSTRUCTIONS.md",
        "RESTORE_LOCAL_VERSION.md",
        "RESTORATION_COMPLETE.md",
        "FILES_CHECKLIST.md",
    ],
    "scripts": [
        "check_and_run.py",
        "git_commit_push.py",
        "fix_rebase_and_push.py",
        "restore_files.py",
        "restore_from_commit.py",
        "verify_files.py",
        "organize_structure.py",
    ],
    "scripts/bat": [
        "git_commit_push.bat",
        "fix_rebase_and_push.bat",
        "restore_files.bat",
        "restore_from_commit.bat",
        "reset_to_before_push.bat",
        "find_and_restore_commit.bat",
    ],
}

def main():
    """Организует файлы по папкам."""
    project_root = Path(__file__).parent.parent
    
    print("=" * 70)
    print("Организация файлов по папкам")
    print("=" * 70)
    print()
    
    moved = []
    errors = []
    
    # Создаём папки и перемещаем файлы
    for folder, files in STRUCTURE.items():
        folder_path = project_root / folder
        folder_path.mkdir(parents=True, exist_ok=True)
        print(f"Создана папка: {folder}")
        
        for file_name in files:
            source = project_root / file_name
            dest = folder_path / file_name
            
            if source.exists():
                try:
                    shutil.move(str(source), str(dest))
                    print(f"  ✓ {file_name} -> {folder}/")
                    moved.append((file_name, folder))
                except Exception as e:
                    print(f"  ✗ {file_name} - ошибка: {e}")
                    errors.append((file_name, str(e)))
            else:
                print(f"  ⚠ {file_name} - не найден")
    
    print()
    print("=" * 70)
    print(f"Перемещено файлов: {len(moved)}")
    if errors:
        print(f"Ошибок: {len(errors)}")
    print("=" * 70)
    
    if moved:
        print("\nПеремещённые файлы:")
        for file_name, folder in moved:
            print(f"  {file_name} -> {folder}/")
    
    if errors:
        print("\nОшибки:")
        for file_name, error in errors:
            print(f"  {file_name}: {error}")
    
    return 0 if not errors else 1

if __name__ == "__main__":
    import sys
    sys.exit(main())
