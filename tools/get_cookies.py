"""Скрипт для локального получения cookies Ozon через Playwright и сохранения в файл.

Использование:
    python tools/get_cookies.py
    
Или с параметрами:
    python tools/get_cookies.py --output cookies/ozon_cookies.json --headless false
"""
import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

# Добавляем корень проекта в путь
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from loguru import logger
from src.utils.playwright_cookies import get_ozon_cookies_playwright


async def save_cookies_to_file(
    output_path: Path,
    headless: bool = True,
    seller_url: Optional[str] = None
) -> bool:
    """Получает cookies через Playwright и сохраняет в JSON файл.
    
    Args:
        output_path: Путь к файлу для сохранения cookies
        headless: Запускать браузер в headless режиме
        seller_url: URL продавца для получения специфичных cookies (опционально)
    
    Returns:
        True если успешно, False если ошибка
    """
    try:
        logger.info("🚀 Начинаем получение cookies Ozon через Playwright...")
        logger.info(f"   • Headless режим: {'включен' if headless else 'выключен'}")
        logger.info(f"   • Файл для сохранения: {output_path}")
        
        # Получаем cookies через Playwright
        cookies_string = await get_ozon_cookies_playwright(headless=headless)
        
        if not cookies_string:
            logger.error("❌ Не удалось получить cookies через Playwright")
            return False
        
        # Парсим строку cookies в словарь
        cookies_dict = {}
        for cookie_pair in cookies_string.split("; "):
            if "=" in cookie_pair:
                name, value = cookie_pair.split("=", 1)
                cookies_dict[name] = value
        
        if not cookies_dict:
            logger.error("❌ Получены пустые cookies")
            return False
        
        # Создаем директорию если не существует
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Сохраняем в JSON
        cookies_data = {
            "cookies": cookies_dict,
            "cookies_string": cookies_string,
            "count": len(cookies_dict),
            "cookie_names": list(cookies_dict.keys())
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(cookies_data, f, indent=2, ensure_ascii=False)
        
        logger.success(f"✅ Cookies успешно сохранены в {output_path}")
        logger.info(f"   • Всего cookies: {len(cookies_dict)}")
        logger.info(f"   • Имена cookies: {', '.join(list(cookies_dict.keys())[:10])}{'...' if len(cookies_dict) > 10 else ''}")
        
        return True
        
    except ImportError as e:
        logger.error(f"❌ Playwright не установлен: {e}")
        logger.info("Установите зависимости:")
        logger.info("  pip install playwright playwright-stealth")
        logger.info("  playwright install chromium")
        return False
    except Exception as e:
        logger.error(f"❌ Ошибка при получении cookies: {e}")
        logger.debug("Детали ошибки:", exc_info=True)
        return False


def main():
    """Главная функция для запуска из командной строки."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Получение cookies Ozon через Playwright и сохранение в файл"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="cookies/ozon_cookies.json",
        help="Путь к файлу для сохранения cookies (по умолчанию: cookies/ozon_cookies.json)"
    )
    parser.add_argument(
        "--headless",
        type=str,
        default="true",
        choices=["true", "false"],
        help="Запускать браузер в headless режиме (по умолчанию: true)"
    )
    
    args = parser.parse_args()
    
    output_path = Path(args.output)
    headless = args.headless.lower() == "true"
    
    # Запускаем асинхронную функцию
    success = asyncio.run(save_cookies_to_file(output_path, headless=headless))
    
    if success:
        logger.info("\n" + "="*60)
        logger.info("✅ Cookies успешно получены и сохранены!")
        logger.info(f"   Файл: {output_path.absolute()}")
        logger.info("\n💡 Теперь вы можете использовать эти cookies на сервере:")
        logger.info(f"   • Скопируйте файл {output_path} на сервер")
        logger.info(f"   • Или установите OZON_COOKIES_PATH={output_path} в .env")
        logger.info("="*60)
        sys.exit(0)
    else:
        logger.error("\n❌ Не удалось получить cookies")
        sys.exit(1)


if __name__ == "__main__":
    main()
