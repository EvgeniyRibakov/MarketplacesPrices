"""Парсер цен для Ozon."""
from typing import Dict, List, Optional
from loguru import logger
from src.api.ozon_seller_api import OzonSellerAPI
from src.api.ozon_catalog_api import OzonCatalogAPI


class OzonParser:
    """Парсер цен для Ozon."""
    
    def __init__(self, client_id: int, api_key: str, request_delay: float = 0.5, 
                 cookies: Optional[str] = None):
        """Инициализация парсера.
        
        Args:
            client_id: Client ID продавца (число)
            api_key: API ключ продавца
            request_delay: Задержка между запросами
            cookies: Опциональные cookies в формате "name1=value1; name2=value2"
        """
        self.client_id = client_id
        self.api_key = api_key
        self.request_delay = request_delay
        self.cookies = cookies
    
    async def parse_seller_catalog(self, seller_id: int, seller_name: str) -> List[Dict]:
        """Парсинг каталога продавца через публичный API и Seller API.
        
        Объединяет данные из двух источников:
        1. Публичный каталог (entrypoint API) - текущие цены покупателя
        2. Seller API - цены продавца без акций
        
        Args:
            seller_id: ID продавца
            seller_name: Название продавца (из URL, например "cosmo-beauty")
        
        Returns:
            Список товаров с полными данными о ценах
        """
        import time
        parse_start_time = time.time()
        
        cabinet_name = OzonCatalogAPI.CABINET_MAPPING.get(seller_id, f"UNKNOWN_{seller_id}")
        
        logger.info(
            f"🚀 Начинаем парсинг каталога продавца {seller_id} ({cabinet_name})..."
        )
        
        all_results = []
        
        # Шаг 1: Получаем товары из публичного каталога
        logger.info("📦 Шаг 1/2: Получение товаров из публичного каталога...")
        catalog_start = time.time()
        
        async with OzonCatalogAPI(
            request_delay=1.0, 
            max_concurrent=3,
            cookies=self.cookies,
            auto_get_cookies=True if not self.cookies else False
        ) as catalog_api:
            catalog_products = await catalog_api.fetch_seller_catalog(seller_id, seller_name)
        
        catalog_time = time.time() - catalog_start
        
        logger.info(
            f"✅ Получено {len(catalog_products)} товаров из публичного каталога "
            f"за {catalog_time:.2f} сек"
        )
        
        if not catalog_products:
            logger.warning("⚠️ Не получено товаров из публичного каталога")
            return []
        
        # Создаем маппинг SKU -> данные из каталога
        catalog_by_sku = {}
        product_ids_for_api = []
        
        for product in catalog_products:
            sku = product.get("sku")
            if sku:
                catalog_by_sku[sku] = product
                product_ids_for_api.append(sku)
        
        logger.info(f"📊 Уникальных SKU для запроса в Seller API: {len(product_ids_for_api)}")
        
        # Шаг 2: Получаем цены продавца через Seller API
        logger.info("💰 Шаг 2/2: Получение цен продавца через Seller API...")
        seller_api_start = time.time()
        
        seller_prices_by_sku = {}
        
        async with OzonSellerAPI(self.client_id, self.api_key, 
                                 request_delay=self.request_delay) as seller_api:
            # Получаем цены по product_id (SKU)
            seller_items = await seller_api.fetch_product_prices(
                product_ids=product_ids_for_api
            )
            
            # Парсим и индексируем по SKU
            for item in seller_items:
                parsed = OzonSellerAPI.parse_price_item(item)
                sku = parsed.get("product_id")
                if sku:
                    seller_prices_by_sku[sku] = parsed
        
        seller_api_time = time.time() - seller_api_start
        
        logger.info(
            f"✅ Получено цен продавца для {len(seller_prices_by_sku)} товаров "
            f"за {seller_api_time:.2f} сек"
        )
        
        # Шаг 3: Объединяем данные
        logger.info("🔗 Шаг 3/3: Объединение данных из двух источников...")
        
        matched_count = 0
        not_matched_count = 0
        
        for sku, catalog_data in catalog_by_sku.items():
            seller_data = seller_prices_by_sku.get(sku, {})
            
            # Создаем объединенную запись
            result = {
                # Основные данные
                "product_id": sku,
                "offer_id": seller_data.get("offer_id"),
                "product_name": catalog_data.get("product_name", ""),
                "cabinet_id": seller_id,
                "cabinet_name": cabinet_name,
                
                # Цены из публичного каталога (что видит покупатель)
                "price_current": catalog_data.get("current_price"),  # Цена со скидкой
                "price_original": catalog_data.get("original_price"),  # Зачёркнутая цена
                "discount_percent": catalog_data.get("discount_percent"),
                
                # Цены из Seller API (цены продавца)
                "price_seller": seller_data.get("seller_price"),  # Цена продавца (без акций)
                "price_old": seller_data.get("old_price"),  # Зачёркнутая (из API продавца)
                "price_min": seller_data.get("min_price"),  # Минимальная цена
                
                # Источники данных
                "source_catalog": "catalog_api",
                "source_seller": "seller_api" if seller_data else None,
            }
            
            all_results.append(result)
            
            if seller_data:
                matched_count += 1
            else:
                not_matched_count += 1
        
        total_time = time.time() - parse_start_time
        
        logger.success(
            f"✅ Парсинг завершен за {total_time:.2f} сек:\n"
            f"  • Всего товаров: {len(all_results)}\n"
            f"  • С данными из Seller API: {matched_count}\n"
            f"  • Только из каталога: {not_matched_count}"
        )
        
        if not_matched_count > 0:
            logger.warning(
                f"⚠️ {not_matched_count} товаров не найдены в Seller API. "
                f"Возможно, они не принадлежат этому продавцу или недоступны через API."
            )
        
        return all_results
