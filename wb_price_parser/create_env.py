"""
Скрипт для создания .env файла из env.example
"""
from pathlib import Path
import shutil

def create_env_file():
    """Создаёт .env файл из env.example если его нет"""
    project_root = Path(__file__).parent
    env_example = project_root / "env.example"
    env_file = project_root / ".env"
    
    if env_file.exists():
        print(f"Файл .env уже существует: {env_file}")
        response = input("Перезаписать? (y/n): ")
        if response.lower() != 'y':
            print("Отменено.")
            return
    
    if not env_example.exists():
        print(f"Ошибка: файл {env_example} не найден!")
        return
    
    try:
        shutil.copy(env_example, env_file)
        print(f"✓ Файл .env создан: {env_file}")
        print("\n⚠ ВАЖНО: Отредактируйте .env и укажите:")
        print("  - WB_BRAND_ID (ID бренда для парсинга)")
        print("  - WB_DEST (регион/ПВЗ)")
        print("  - Другие параметры при необходимости")
    except Exception as e:
        print(f"Ошибка при создании .env: {e}")

if __name__ == "__main__":
    create_env_file()

