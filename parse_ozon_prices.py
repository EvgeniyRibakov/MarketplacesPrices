"""Скрипт для парсинга цен товаров через Ozon Seller API /v5/product/info/prices."""
import asyncio
import sys
import time
from pathlib import Path
from typing import Dict, List
from datetime import datetime

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from loguru import logger
from src.api.ozon_seller_api import OzonSellerAPI

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
        
        return {
            "ozon_client_id": int(os.getenv("OZON_CLIENT_ID", "0")),
            "ozon_api_key": os.getenv("OZON_API_KEY", ""),
        }
    except Exception as e:
        logger.error(f"Ошибка при загрузке конфигурации: {e}")
        return {
            "ozon_client_id": 0,
            "ozon_api_key": "",
        }


async def parse_all_prices(client_id: int, api_key: str, limit: int = 1000) -> List[Dict]:
    """Парсит все цены товаров через Seller API /v5/product/info/prices.
    
    Args:
        client_id: Client ID продавца
        api_key: API ключ продавца
        limit: Количество товаров за запрос (max 1000)
    
    Returns:
        Список всех товаров с ценами
    """
    total_start_time = time.time()
    
    logger.info("=" * 70)
    logger.info("🚀 Парсинг цен товаров через Ozon Seller API")
    logger.info("=" * 70)
    logger.info(f"📋 Эндпоинт: /v5/product/info/prices")
    logger.info(f"📦 Лимит на страницу: {limit}")
    logger.info("=" * 70)
    
    all_results = []
    
    async with OzonSellerAPI(
        client_id=client_id,
        api_key=api_key,
        request_delay=0.5,
        max_concurrent=1  # Последовательно для стабильности
    ) as seller_api:
        # Запрашиваем ВСЕ товары (без фильтров)
        all_results = await seller_api.fetch_product_prices(
            offer_ids=None,
            product_ids=None,
            limit=limit
        )
    
    total_time = time.time() - total_start_time
    
    logger.info("\n" + "=" * 70)
    logger.info("📊 ИТОГОВАЯ СТАТИСТИКА ПАРСИНГА")
    logger.info("=" * 70)
    logger.info(f"⏱️  Общее время выполнения: {total_time:.2f} сек ({total_time/60:.2f} мин)")
    logger.info(f"📦 Всего получено товаров: {len(all_results)}")
    logger.info("=" * 70)
    
    return all_results


def export_to_excel(results: List[Dict], output_dir: Path):
    """Экспортирует результаты в Excel файл.
    
    Args:
        results: Список товаров с ценами
        output_dir: Директория для сохранения файла
    """
    if not results:
        logger.warning("⚠️ Нет данных для экспорта")
        return None
    
    export_start_time = time.time()
    logger.info("💾 Начинаем экспорт результатов в Excel...")
    
    try:
        import pandas as pd
        from openpyxl.utils import get_column_letter
        
        # Преобразуем вложенные структуры в плоский формат для Excel
        parsed_data = []
        
        # Логируем структуру первого товара для диагностики
        if results:
            logger.info(f"🔍 Структура первого товара: {list(results[0].keys())}")
            # Показываем первые несколько полей для понимания структуры
            first_item_preview = {k: str(v)[:100] if not isinstance(v, (int, float, str, type(None))) else v 
                                 for k, v in list(results[0].items())[:10]}
            logger.info(f"🔍 Первый товар (первые 10 полей): {first_item_preview}")
        else:
            logger.warning("⚠️ Seller API вернул 0 товаров. Возможные причины:")
            logger.warning("   1. OZON_CLIENT_ID и OZON_API_KEY не соответствуют кабинету с товарами")
            logger.warning("   2. В кабинете нет товаров")
            logger.warning("   3. API ключ неверный или истек")
            logger.warning("   → Проверьте credentials в .env файле")
        
        for item in results:
            row = {
                'product_id': item.get('product_id'),
                'offer_id': item.get('offer_id'),  # Это и есть "Артикул продавца"
            }
            
            # Логируем если offer_id отсутствует (только для первых 3 товаров, чтобы не засорять логи)
            if not row['offer_id'] and len([r for r in parsed_data if not r.get('offer_id')]) < 3:
                logger.warning(f"⚠️ Товар {row['product_id']}: offer_id отсутствует в Seller API")
                logger.debug(f"   Доступные ключи: {list(item.keys())[:15]}")
            
            # Парсим price (основная цена) - реальная структура из API
            price_data = item.get('price', {})
            if price_data:
                # Основные поля цены
                row['price'] = price_data.get('price')
                row['price_currency'] = price_data.get('currency_code')
                row['old_price'] = price_data.get('old_price')  # Зачёркнутая цена внутри price
                row['min_price'] = price_data.get('min_price')  # Минимальная цена внутри price
                row['marketing_seller_price'] = price_data.get('marketing_seller_price')
                row['retail_price'] = price_data.get('retail_price')
                row['net_price'] = price_data.get('net_price')
                row['vat'] = price_data.get('vat')
                row['auto_action_enabled'] = price_data.get('auto_action_enabled')
                row['auto_add_to_ozon_actions_list_enabled'] = price_data.get('auto_add_to_ozon_actions_list_enabled')
            
            # Дополнительные данные товара
            row['acquiring'] = item.get('acquiring')
            row['volume_weight'] = item.get('volume_weight')
            
            # Комиссии (если нужны)
            commissions = item.get('commissions', {})
            if commissions:
                row['sales_percent_fbo'] = commissions.get('sales_percent_fbo')
                row['sales_percent_fbs'] = commissions.get('sales_percent_fbs')
                row['sales_percent_rfbs'] = commissions.get('sales_percent_rfbs')
                row['sales_percent_fbp'] = commissions.get('sales_percent_fbp')
            
            # Индексы цен (если нужны)
            price_indexes = item.get('price_indexes', {})
            if price_indexes:
                row['color_index'] = price_indexes.get('color_index')
                ozon_index = price_indexes.get('ozon_index_data', {})
                if ozon_index:
                    row['ozon_index_value'] = ozon_index.get('price_index_value')
                    row['ozon_index_min_price'] = ozon_index.get('min_price')
            
            parsed_data.append(row)
        
        df = pd.DataFrame(parsed_data)
        
        # Переименовываем столбцы для читаемости
        rename_mapping = {
            'product_id': 'SKU (product_id)',
            'offer_id': 'Артикул продавца',
            'price': 'Цена',
            'price_currency': 'Валюта',
            'old_price': 'Зачёркнутая цена',
            'old_price_currency': 'Валюта (зачёркнутая)',
            'min_price': 'Минимальная цена',
            'min_price_currency': 'Валюта (минимальная)',
            'marketing_seller_price': 'Маркетинговая цена продавца',
            'retail_price': 'Розничная цена',
            'net_price': 'Чистая цена',
            'vat': 'НДС',
            'auto_action_enabled': 'Авто-действия включены',
            'auto_add_to_ozon_actions_list_enabled': 'Авто-добавление в акции',
            'acquiring': 'Эквайринг',
            'volume_weight': 'Объёмный вес',
            'sales_percent_fbo': 'Комиссия FBO (%)',
            'sales_percent_fbs': 'Комиссия FBS (%)',
            'sales_percent_rfbs': 'Комиссия RFBS (%)',
            'sales_percent_fbp': 'Комиссия FBP (%)',
            'color_index': 'Индекс цвета',
            'ozon_index_value': 'Индекс Ozon',
            'ozon_index_min_price': 'Мин. цена по индексу Ozon',
        }
        
        for old_name, new_name in rename_mapping.items():
            if old_name in df.columns:
                df = df.rename(columns={old_name: new_name})
        
        # Определяем порядок столбцов (важные сначала)
        priority_columns = [
            'SKU (product_id)',
            'Артикул продавца',
            'Цена',
            'Валюта',
            'Зачёркнутая цена',
            'Минимальная цена',
        ]
        
        # Сортируем столбцы: сначала приоритетные, потом остальные
        existing_priority = [col for col in priority_columns if col in df.columns]
        other_columns = [col for col in df.columns if col not in priority_columns]
        df = df[existing_priority + other_columns]
        
        # Создаем имя файла с timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        output_file = output_dir / f"ozon_prices_{timestamp}.xlsx"
        
        # Сохраняем в Excel
        with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Prices')
            
            # Автоматически настраиваем ширину столбцов
            worksheet = writer.sheets['Prices']
            for idx, col in enumerate(df.columns, 1):
                max_length = max(
                    df[col].astype(str).map(len).max(),
                    len(str(col))
                )
                # Ограничиваем максимальную ширину
                adjusted_width = min(max_length + 2, 50)
                worksheet.column_dimensions[get_column_letter(idx)].width = adjusted_width
        
        export_time = time.time() - export_start_time
        
        logger.success(
            f"✅ Результаты экспортированы в Excel за {export_time:.2f} сек"
        )
        logger.info(f"📁 Файл: {output_file.absolute()}")
        logger.info(f"📊 Записей: {len(df)}")
        logger.info(f"📋 Столбцов: {len(df.columns)}")
        
        return output_file
        
    except ImportError as e:
        logger.error(f"❌ Не установлены необходимые библиотеки: {e}")
        logger.info("Установите: pip install pandas openpyxl")
        return None
    except Exception as e:
        logger.error(f"❌ Ошибка при экспорте в Excel: {e}")
        logger.exception("Детали ошибки:")
        return None


async def main():
    """Главная функция."""
    # Настройка логирования
    logs_dir = project_root / "logs"
    logs_dir.mkdir(exist_ok=True)
    setup_logger(logs_dir, debug=True)
    
    # Загрузка конфигурации
    config = load_env_config()
    client_id = config["ozon_client_id"]
    api_key = config["ozon_api_key"]
    
    if not client_id or not api_key:
        logger.error(
            "❌ Не найдены OZON_CLIENT_ID или OZON_API_KEY в .env файле. "
            "Добавьте их в .env файл."
        )
        return
    
    logger.info(
        f"✅ Конфигурация загружена:\n"
        f"  • Client ID: {client_id}"
    )
    
    # Парсинг цен
    try:
        results = await parse_all_prices(
            client_id=client_id,
            api_key=api_key,
            limit=1000  # Максимум по API
        )
        
        # Экспорт в Excel
        output_dir = project_root / "output"
        output_dir.mkdir(exist_ok=True)
        
        output_file = export_to_excel(results, output_dir)
        
        if output_file:
            logger.success("\n" + "=" * 70)
            logger.success("✅ ПАРСИНГ ЗАВЕРШЕН УСПЕШНО")
            logger.success("=" * 70)
            logger.success(f"📁 Файл сохранен: {output_file.absolute()}")
            logger.success("=" * 70)
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        logger.exception("Детали ошибки:")


if __name__ == "__main__":
    asyncio.run(main())
