"""Скрипт для проверки окружения и запуска парсера."""
import sys
import subprocess
import os
from pathlib import Path

def check_python():
    """Проверяет версию Python."""
    print(f"Python версия: {sys.version}")
    print(f"Python путь: {sys.executable}")
    return True

def check_dependencies():
    """Проверяет наличие необходимых библиотек."""
    required = ['aiohttp', 'pandas', 'openpyxl', 'loguru', 'dotenv']
    missing = []
    
    for lib in required:
        try:
            __import__(lib)
            print(f"✓ {lib}")
        except ImportError:
            print(f"✗ {lib} - не установлен")
            missing.append(lib)
    
    if missing:
        print(f"\nУстановите недостающие библиотеки:")
        print(f"pip install {' '.join(missing)}")
        return False
    
    return True

def run_parser():
    """Запускает парсер брендов."""
    print("\n" + "="*70)
    print("Запуск парсера брендов...")
    print("="*70 + "\n")
    
    script_path = Path(__file__).parent / "parse_brands.py"
    
    if not script_path.exists():
        print(f"Ошибка: файл {script_path} не найден")
        return 1
    
    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=Path(__file__).parent,
            check=False
        )
        return result.returncode
    except Exception as e:
        print(f"Ошибка при запуске: {e}")
        return 1

if __name__ == "__main__":
    print("Проверка окружения...")
    print("-" * 70)
    
    check_python()
    print()
    
    print("Проверка зависимостей...")
    print("-" * 70)
    if not check_dependencies():
        sys.exit(1)
    
    print("\nВсе зависимости установлены!")
    
    # Запускаем парсер
    sys.exit(run_parser())
