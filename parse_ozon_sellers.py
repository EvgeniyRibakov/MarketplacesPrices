"""Скрипт для парсинга цен продавцов Ozon."""
import asyncio
import sys
from pathlib import Path
from typing import Dict, List

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from loguru import logger
from src.parsers.ozon_parser import OzonParser

try:
    from src.utils.logger import setup_logger
except ImportError:
    def setup_logger(logs_dir, debug=False):
        logger.info("Логирование настроено")


def load_env_config() -> Dict:
    """Загружает конфигурацию из .env файла."""
    try:
        from dotenv import load_dotenv
        import os
        
        env_file = project_root / ".env"
        if env_file.exists():
            load_dotenv(env_file)
        
        # Собираем cookies из .env (если указаны вручную)
        cookies_parts = []
        cookie_names = [
            "sessionid",
            "csrf-token",
            "OZON_SESSION_ID",
            "OZON_CSRF_TOKEN"
        ]
        
        for cookie_name in cookie_names:
            cookie_value = os.getenv(f"OZON_COOKIE_{cookie_name.replace('-', '_').upper()}")
            if cookie_value:
                cookies_parts.append(f"{cookie_name}={cookie_value}")
        
        # Также поддерживаем полную строку cookies
        full_cookies = os.getenv("OZON_COOKIES")
        if full_cookies:
            cookies_string = full_cookies
        elif cookies_parts:
            cookies_string = "; ".join(cookies_parts)
        else:
            cookies_string = None
        
        return {
            "ozon_client_id": int(os.getenv("OZON_CLIENT_ID", "0")),
            "ozon_api_key": os.getenv("OZON_API_KEY", ""),
            "ozon_seller_id": int(os.getenv("OZON_SELLER_ID_COSMO", "176640")),
            "ozon_seller_name": os.getenv("OZON_SELLER_NAME_COSMO", "cosmo-beauty"),
            "ozon_cookies": cookies_string,
        }
    except Exception as e:
        logger.error(f"Ошибка при загрузке конфигурации: {e}")
        return {
            "ozon_client_id": 0,
            "ozon_api_key": "",
            "ozon_seller_id": 176640,
            "ozon_seller_name": "cosmo-beauty",
        }


async def parse_seller():
    """Парсит продавца Ozon."""
    import time
    
    logs_dir = project_root / "logs"
    logs_dir.mkdir(exist_ok=True)
    setup_logger(logs_dir, debug=True)
    
    total_start_time = time.time()
    
    logger.info("=" * 70)
    logger.info("🚀 Парсинг цен продавца Ozon")
    logger.info("=" * 70)
    
    config_start = time.time()
    config = load_env_config()
    config_time = time.time() - config_start
    
    # Проверяем конфигурацию
    client_id = config["ozon_client_id"]
    api_key = config["ozon_api_key"]
    seller_id = config["ozon_seller_id"]
    seller_name = config["ozon_seller_name"]
    
    if not client_id or not api_key:
        logger.error(
            "❌ Не найдены OZON_CLIENT_ID или OZON_API_KEY в .env файле. "
            "Добавьте их в .env файл."
        )
        return []
    
    logger.info(
        f"✅ Конфигурация загружена за {config_time:.2f} сек:\n"
        f"  • Client ID: {client_id}\n"
        f"  • Seller ID: {seller_id} ({seller_name})"
    )
    
    cookies = config.get("ozon_cookies")
    
    if cookies:
        logger.info("✅ Используются cookies из .env файла")
    else:
        logger.info("ℹ️ Cookies не указаны в .env - будет попытка автоматического получения")
    
    parser = OzonParser(
        client_id=client_id,
        api_key=api_key,
        request_delay=0.5,
        cookies=cookies
    )
    
    try:
        results = await parser.parse_seller_catalog(
            seller_id=seller_id,
            seller_name=seller_name
        )
        
        total_time = time.time() - total_start_time
        
        logger.info("\n" + "=" * 70)
        logger.info("📊 ИТОГОВАЯ СТАТИСТИКА ПАРСИНГА")
        logger.info("=" * 70)
        logger.info(f"⏱️  Общее время выполнения: {total_time:.2f} сек ({total_time/60:.2f} мин)")
        logger.info(f"📦 Всего получено записей: {len(results)}")
        logger.info("=" * 70)
        
        return results
        
    except Exception as e:
        elapsed_time = time.time() - total_start_time
        logger.error(
            f"❌ Ошибка при парсинге продавца {seller_id} "
            f"(время до ошибки: {elapsed_time:.2f} сек): {e}"
        )
        logger.exception("Детали ошибки:")
        return []


def export_results(results: List[Dict], output_dir: Path):
    """Экспортирует результаты в Excel."""
    import time
    
    if not results:
        logger.warning("⚠️ Нет данных для экспорта")
        return
    
    export_start_time = time.time()
    logger.info("💾 Начинаем экспорт результатов в Excel...")
    
    try:
        import pandas as pd
        from datetime import datetime
        from openpyxl.utils import get_column_letter
        
        df = pd.DataFrame(results)
        
        # Переименовываем столбцы для русского интерфейса
        rename_mapping = {
            'product_id': 'SKU',
            'offer_id': 'Артикул продавца',
            'product_name': 'Название товара',
            'cabinet_id': 'ID кабинета',
            'cabinet_name': 'Кабинет',
            'price_current': 'Цена покупателя',
            'price_original': 'Зачёркнутая цена (каталог)',
            'discount_percent': 'Скидка %',
            'price_seller': 'Цена продавца',
            'price_old': 'Зачёркнутая цена (API)',
            'price_min': 'Минимальная цена',
        }
        
        for old_name, new_name in rename_mapping.items():
            if old_name in df.columns:
                df = df.rename(columns={old_name: new_name})
        
        # Удаляем технические столбцы
        columns_to_remove = ['source_catalog', 'source_seller']
        for col in columns_to_remove:
            if col in df.columns:
                df = df.drop(columns=[col])
        
        # Определяем порядок столбцов для экспорта
        desired_order = [
            'SKU',
            'Артикул продавца',
            'Название товара',
            'ID кабинета',
            'Кабинет',
            'Цена покупателя',
            'Зачёркнутая цена (каталог)',
            'Скидка %',
            'Цена продавца',
            'Зачёркнутая цена (API)',
            'Минимальная цена',
        ]
        
        # Оставляем только существующие столбцы в нужном порядке
        existing_columns = [col for col in desired_order if col in df.columns]
        # Добавляем остальные столбцы (если есть), которые не в списке
        other_columns = [col for col in df.columns if col not in desired_order]
        df = df[existing_columns + other_columns]
        
        # Сортируем по названию товара
        if 'Название товара' in df.columns:
            df = df.sort_values('Название товара', ascending=True)
        
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"ozon_seller_prices_{timestamp}.xlsx"
        
        with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Prices')
            
            worksheet = writer.sheets['Prices']
            
            # Автоматическая настройка ширины столбцов
            for idx, col in enumerate(df.columns, 1):
                max_length = max(
                    df[col].astype(str).map(len).max(),
                    len(str(col))
                )
                col_letter = get_column_letter(idx)
                worksheet.column_dimensions[col_letter].width = min(max_length + 2, 50)
        
        export_time = time.time() - export_start_time
        
        logger.success(
            f"✅ Результаты сохранены в: {output_file} (время экспорта: {export_time:.2f} сек)"
        )
        logger.info(f"📊 Всего строк: {len(df)}")
        logger.info(f"📋 Колонки: {', '.join(df.columns.tolist())}")
        
        # Статистика по заполненности полей
        if 'Цена покупателя' in df.columns:
            filled = df['Цена покупателя'].notna().sum()
            logger.info(
                f"💰 Заполнено цен покупателя: {filled} из {len(df)} "
                f"({filled/len(df)*100:.1f}%)"
            )
        
        if 'Цена продавца' in df.columns:
            filled = df['Цена продавца'].notna().sum()
            logger.info(
                f"💰 Заполнено цен продавца: {filled} из {len(df)} "
                f"({filled/len(df)*100:.1f}%)"
            )
        
        if 'Зачёркнутая цена (каталог)' in df.columns:
            filled = df['Зачёркнутая цена (каталог)'].notna().sum()
            logger.info(
                f"💰 Заполнено зачёркнутых цен (каталог): {filled} из {len(df)} "
                f"({filled/len(df)*100:.1f}%)"
            )
        
    except Exception as e:
        export_time = time.time() - export_start_time
        logger.error(
            f"❌ Ошибка при экспорте результатов (время до ошибки: {export_time:.2f} сек): {e}"
        )
        logger.exception("Детали ошибки:")


async def main():
    """Основная функция."""
    import time
    
    main_start_time = time.time()
    
    try:
        results = await parse_seller()
        
        parse_time = time.time() - main_start_time
        
        logger.info("\n" + "=" * 70)
        logger.success(
            f"✅ Парсинг завершен. Всего записей: {len(results)} "
            f"(время парсинга: {parse_time:.2f} сек)"
        )
        logger.info("=" * 70)
        
        export_start = time.time()
        output_dir = project_root / "output"
        export_results(results, output_dir)
        export_time = time.time() - export_start
        
        total_time = time.time() - main_start_time
        
        logger.info("\n" + "=" * 70)
        logger.info("🎉 ПРОЦЕСС ЗАВЕРШЕН УСПЕШНО")
        logger.info("=" * 70)
        logger.info(f"⏱️  Общее время выполнения: {total_time:.2f} сек ({total_time/60:.2f} мин)")
        logger.info(f"  • Парсинг: {parse_time:.2f} сек")
        logger.info(f"  • Экспорт: {export_time:.2f} сек")
        logger.info(f"📦 Всего записей: {len(results)}")
        logger.info("=" * 70)
        
        return 0
        
    except KeyboardInterrupt:
        elapsed_time = time.time() - main_start_time
        logger.warning(
            f"⚠️ Прервано пользователем (время работы: {elapsed_time:.2f} сек)"
        )
        return 1
        
    except Exception as e:
        elapsed_time = time.time() - main_start_time
        logger.error(
            f"❌ Критическая ошибка (время до ошибки: {elapsed_time:.2f} сек): {e}"
        )
        logger.exception("Детали ошибки:")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
