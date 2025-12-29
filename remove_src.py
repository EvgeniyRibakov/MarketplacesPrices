import shutil
import os
from pathlib import Path

# Удаляем папку src
src_path = Path('src')
if src_path.exists():
    try:
        shutil.rmtree(src_path)
        print("✓ Папка src удалена")
    except Exception as e:
        print(f"Ошибка при удалении src: {e}")

# Удаляем временные скрипты
scripts_to_remove = ['remove_src.py', 'complete_git_operations.py']
for script in scripts_to_remove:
    script_path = Path(script)
    if script_path.exists():
        try:
            script_path.unlink()
            print(f"✓ Удалён скрипт: {script}")
        except Exception as e:
            print(f"Ошибка при удалении {script}: {e}")

print("\nГотово! Теперь выполните вручную:")
print("  git add -A")
print("  git commit -m 'chore: очистка main ветки'")
print("  git push origin main")

