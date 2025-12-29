"""
Скрипт для запуска из корня проекта
"""
import sys
from pathlib import Path

# Добавляем src в путь
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))

if __name__ == "__main__":
    from src.main import main
    import asyncio
    asyncio.run(main())

