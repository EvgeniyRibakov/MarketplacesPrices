"""Тестовый скрипт для проверки официальных эндпоинтов Seller API.

Тестирует:
1. /v3/product/info/list - сопоставление SKU с product_id и offer_id
2. /v5/product/info/prices - получение цен по product_id или offer_id
"""
import asyncio
import sys
import time
from pathlib import Path
from typing import List, Dict

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from loguru import logger
from src.api.ozon_seller_api import OzonSellerAPI

try:
    from dotenv import load_dotenv
    import os
    
    env_file = project_root / ".env"
    if env_file.exists():
        load_dotenv(env_file)
    
    CLIENT_ID = int(os.getenv('OZON_CLIENT_ID', '0'))
    API_KEY = os.getenv('OZON_API_KEY', '')
except Exception as e:
    logger.error(f"Ошибка загрузки конфигурации: {e}")
    sys.exit(1)


async def test_v3_product_info_list(seller_api: OzonSellerAPI, sku_list: List[int]):
    """Тест эндпоинта /v3/product/info/list."""
    logger.info("=" * 70)
    logger.info("🧪 ТЕСТ 1: /v3/product/info/list")
    logger.info("=" * 70)
    logger.info(f"📋 Тестируем {len(sku_list)} SKU")
    logger.info(f"📋 Первые 5 SKU: {sku_list[:5]}")
    
    try:
        start_time = time.time()
        results = await seller_api.fetch_products_by_sku(sku_list)
        elapsed = time.time() - start_time
        
        logger.success(f"✅ Получено {len(results)} товаров за {elapsed:.2f} сек")
        
        if results:
            logger.info("\n📊 Примеры результатов:")
            for i, item in enumerate(results[:3], 1):
                parsed = OzonSellerAPI.parse_product_info_item(item)
                logger.info(
                    f"  {i}. SKU: {parsed.get('sku')} → "
                    f"product_id: {parsed.get('product_id')}, "
                    f"offer_id: {parsed.get('offer_id')}"
                )
            
            # Статистика
            with_offer_id = sum(1 for item in results if OzonSellerAPI.parse_product_info_item(item).get('offer_id'))
            logger.info(f"\n📈 Статистика:")
            logger.info(f"  • Всего товаров: {len(results)}")
            logger.info(f"  • С offer_id: {with_offer_id}")
            logger.info(f"  • Без offer_id: {len(results) - with_offer_id}")
        else:
            logger.warning("⚠️ Товары не найдены. Возможные причины:")
            logger.warning("  • SKU не принадлежат вашему кабинету")
            logger.warning("  • Неверный Client-Id или Api-Key")
            logger.warning("  • Товары не существуют в Seller API")
        
        return results
        
    except Exception as e:
        logger.error(f"❌ Ошибка при тесте /v3/product/info/list: {e}")
        logger.exception("Детали ошибки:")
        return []


async def test_v5_product_info_prices(seller_api: OzonSellerAPI, product_ids: List[int] = None, offer_ids: List[str] = None):
    """Тест эндпоинта /v5/product/info/prices."""
    logger.info("\n" + "=" * 70)
    logger.info("🧪 ТЕСТ 2: /v5/product/info/prices")
    logger.info("=" * 70)
    
    if product_ids:
        logger.info(f"📋 Тестируем по product_ids: {len(product_ids)} товаров")
        logger.info(f"📋 Первые 5 product_ids: {product_ids[:5]}")
    elif offer_ids:
        logger.info(f"📋 Тестируем по offer_ids: {len(offer_ids)} товаров")
        logger.info(f"📋 Первые 5 offer_ids: {offer_ids[:5]}")
    else:
        logger.info("📋 Тестируем без фильтров (все товары)")
    
    try:
        start_time = time.time()
        results = await seller_api.fetch_product_prices(
            product_ids=product_ids,
            offer_ids=offer_ids
        )
        elapsed = time.time() - start_time
        
        logger.success(f"✅ Получено {len(results)} товаров за {elapsed:.2f} сек")
        
        if results:
            logger.info("\n📊 Примеры результатов:")
            for i, item in enumerate(results[:3], 1):
                parsed = OzonSellerAPI.parse_price_item(item)
                logger.info(
                    f"  {i}. product_id: {parsed.get('product_id')}, "
                    f"offer_id: {parsed.get('offer_id')}, "
                    f"цена: {parsed.get('seller_price')}"
                )
        else:
            logger.warning("⚠️ Товары не найдены")
        
        return results
        
    except Exception as e:
        logger.error(f"❌ Ошибка при тесте /v5/product/info/prices: {e}")
        logger.exception("Детали ошибки:")
        return []


async def main():
    """Основная функция тестирования."""
    logger.info("=" * 70)
    logger.info("🚀 ТЕСТИРОВАНИЕ ОФИЦИАЛЬНЫХ ЭНДПОИНТОВ SELLER API")
    logger.info("=" * 70)
    logger.info(f"📋 Client ID: {CLIENT_ID}")
    logger.info(f"📋 API Key: {'*' * 20 if API_KEY else 'НЕ УКАЗАН'}")
    
    if not CLIENT_ID or not API_KEY:
        logger.error("❌ OZON_CLIENT_ID или OZON_API_KEY не указаны в .env")
        return
    
    # SKU из логов парсинга (товары из публичного каталога продавца)
    # Взяты из logs/parser_2026-01-23.log
    test_sku_list = [
        2806667822,
        2834701779,
        720770058,
        2995769137,
        648770151,
        743340156,
        1317355297,
        3122830222,
        2796490206,
        1115748930,
        1847047586,
        839958861,
        3404814588,
        1431518121,
        1451298896,
        3409714412,
        3409631052,
        1847041612,
        2806667612,
        3138645223,
        1847029764,
        838129629,
    ]
    
    logger.info(f"\n📋 Тестируем {len(test_sku_list)} SKU из публичного каталога")
    logger.info(f"📋 Первые 10 SKU: {test_sku_list[:10]}")
    logger.info(f"⚠️ ВАЖНО: Эти SKU из публичного каталога продавца 176640")
    logger.info(f"⚠️ Если OZON_CLIENT_ID={CLIENT_ID} не соответствует этому продавцу, товары не будут найдены")
    logger.info(f"⚠️ Для теста используйте SKU товаров из ВАШЕГО кабинета!")
    
    async with OzonSellerAPI(
        client_id=CLIENT_ID,
        api_key=API_KEY,
        request_delay=0.3,  # Уменьшено для теста
        max_concurrent=20  # Увеличено до 20
    ) as seller_api:
        
        # ТЕСТ 1: /v3/product/info/list
        v3_results = await test_v3_product_info_list(seller_api, test_sku_list)
        
        # Извлекаем product_id и offer_id из результатов v3
        product_ids_from_v3 = []
        offer_ids_from_v3 = []
        
        for item in v3_results:
            parsed = OzonSellerAPI.parse_product_info_item(item)
            product_id = parsed.get("product_id")
            offer_id = parsed.get("offer_id")
            
            if product_id:
                product_ids_from_v3.append(int(product_id))
            if offer_id:
                offer_ids_from_v3.append(str(offer_id))
        
        # ТЕСТ 2: /v5/product/info/prices (по product_id)
        if product_ids_from_v3:
            logger.info(f"\n📋 Тестируем /v5/product/info/prices по {len(product_ids_from_v3)} product_ids")
            await test_v5_product_info_prices(seller_api, product_ids=product_ids_from_v3[:10])  # Первые 10 для теста
        
        # ТЕСТ 3: /v5/product/info/prices (по offer_id)
        if offer_ids_from_v3:
            logger.info(f"\n📋 Тестируем /v5/product/info/prices по {len(offer_ids_from_v3)} offer_ids")
            await test_v5_product_info_prices(seller_api, offer_ids=offer_ids_from_v3[:10])  # Первые 10 для теста
        
        # ТЕСТ 4: /v5/product/info/prices (без фильтров - все товары)
        logger.info(f"\n📋 Тестируем /v5/product/info/prices без фильтров (все товары кабинета)")
        all_prices = await test_v5_product_info_prices(seller_api)
        if all_prices:
            logger.info(f"✅ Всего товаров в кабинете: {len(all_prices)}")
            
            # Показываем примеры с offer_id
            with_offer_id = [item for item in all_prices[:10] if item.get('offer_id')]
            if with_offer_id:
                logger.info(f"\n📊 Примеры товаров с offer_id (первые {len(with_offer_id)}):")
                for i, item in enumerate(with_offer_id[:5], 1):
                    parsed = OzonSellerAPI.parse_price_item(item)
                    logger.info(
                        f"  {i}. product_id: {parsed.get('product_id')}, "
                        f"offer_id: {parsed.get('offer_id')}, "
                        f"цена: {parsed.get('seller_price')}"
                    )
    
    logger.info("\n" + "=" * 70)
    logger.info("✅ ТЕСТИРОВАНИЕ ЗАВЕРШЕНО")
    logger.info("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
