"""Скрипт для проверки наличия всех необходимых файлов."""
from pathlib import Path

REQUIRED_FILES = [
    # Основные модули
    "src/api/wb_catalog_api.py",
    "src/parsers/wb_parser.py",
    "src/utils/logger.py",
    
    # Скрипты (в корне)
    "parse_brands.py",
    "run_parse_brands.bat",
    "run_parse_brands.ps1",
    
    # Конфигурация (в корне)
    "brands_config.json",
    
    # Документация (в docs/)
    "docs/README_BRANDS_PARSING.md",
    "docs/GIT_INSTRUCTIONS.md",
    
    # Инициализация пакетов
    "src/__init__.py",
    "src/api/__init__.py",
    "src/parsers/__init__.py",
    "src/utils/__init__.py",
]

def main():
    """Проверяет наличие всех файлов."""
    project_root = Path(__file__).parent.parent
    
    print("=" * 70)
    print("Проверка наличия файлов для парсинга брендов")
    print("=" * 70)
    print()
    
    missing = []
    present = []
    
    for file_path in REQUIRED_FILES:
        full_path = project_root / file_path
        if full_path.exists():
            print(f"✓ {file_path}")
            present.append(file_path)
        else:
            print(f"✗ {file_path} - ОТСУТСТВУЕТ")
            missing.append(file_path)
    
    print()
    print("=" * 70)
    print(f"Найдено: {len(present)}/{len(REQUIRED_FILES)}")
    print(f"Отсутствует: {len(missing)}/{len(REQUIRED_FILES)}")
    print("=" * 70)
    
    if missing:
        print("\n⚠️  Отсутствующие файлы:")
        for f in missing:
            print(f"  - {f}")
        return 1
    else:
        print("\n✅ Все файлы на месте!")
        return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())
