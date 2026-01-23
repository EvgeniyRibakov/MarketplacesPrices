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
        
        КРИТИЧНО: Используем публичный entrypoint API как основной источник данных,
        так как он содержит почти все нужные цены покупателя (цена со скидкой, зачёркнутая цена),
        которых нет в официальном Seller API.
        
        Объединяет данные из двух источников:
        1. Публичный каталог (entrypoint API) - текущие цены покупателя (ОСНОВНОЙ ИСТОЧНИК)
        2. Seller API - цены продавца без акций (дополнительный источник)
        
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
        
        # Шаг 1: Получаем товары из публичного каталога (ОСНОВНОЙ ИСТОЧНИК)
        logger.info("📦 Шаг 1/2: Получение товаров из публичного каталога (entrypoint API)...")
        catalog_start = time.time()
        
        # Читаем режим из .env (если не передан явно)
        import os
        mode = os.getenv('OZON_MODE', 'full').lower().strip()
        mode = mode if mode in ('light', 'full') else 'full'
        
        # Читаем лимит товаров для тестового режима
        test_limit = os.getenv('OZON_TEST_LIMIT')
        max_products = None
        if test_limit:
            try:
                max_products = int(test_limit)
                logger.info(f"🧪 Тестовый режим: ограничение до {max_products} товаров")
            except ValueError:
                logger.warning(f"⚠️ Неверное значение OZON_TEST_LIMIT: {test_limit}. Игнорируем.")
        
        async with OzonCatalogAPI(
            request_delay=1.0, 
            max_concurrent=3,
            cookies=self.cookies,
            auto_get_cookies=True if not self.cookies else False,
            mode=mode
        ) as catalog_api:
            catalog_products = await catalog_api.fetch_seller_catalog(seller_id, seller_name, max_products=max_products)
        
        catalog_time = time.time() - catalog_start
        
        logger.info(
            f"✅ Получено {len(catalog_products)} товаров из публичного каталога "
            f"за {catalog_time:.2f} сек"
        )
        
        if not catalog_products:
            logger.warning("⚠️ Не получено товаров из публичного каталога")
            # Пробуем получить хотя бы через Seller API
            logger.info("📦 Попытка получить товары через Seller API...")
            async with OzonSellerAPI(self.client_id, self.api_key, 
                                     request_delay=self.request_delay) as seller_api:
                # Получаем цены из /v5/product/info/prices
                seller_items = await seller_api.fetch_product_prices()
                if seller_items:
                    logger.info(f"✅ Получено {len(seller_items)} товаров из Seller API (/v5/product/info/prices)")
                    
                    # Получаем названия товаров из /v3/product/info/list
                    # Сначала парсим product_id из ответа /v5/product/info/prices
                    product_ids = []
                    for item in seller_items:
                        parsed = OzonSellerAPI.parse_price_item(item)
                        product_id = parsed.get("product_id")
                        if product_id:
                            # product_id может быть строкой или числом
                            try:
                                product_id_int = int(product_id) if isinstance(product_id, str) else product_id
                                product_ids.append(product_id_int)
                            except (ValueError, TypeError):
                                pass
                    
                    if product_ids:
                        logger.info(f"📝 Запрашиваем названия товаров для {len(product_ids)} товаров...")
                        product_info_list = await seller_api.fetch_products_by_product_id(product_ids)
                        
                        # Создаём маппинг product_id -> название
                        # В parse_product_info_item product_id возвращается как "product_id" (из item.get("id"))
                        product_names = {}
                        for info_item in product_info_list:
                            product_id = info_item.get("product_id")  # Это уже распарсенный product_id из parse_product_info_item
                            name = info_item.get("name")
                            if product_id and name:
                                # Приводим product_id к строке для сравнения
                                product_id_key = str(product_id)
                                product_names[product_id_key] = name
                        
                        logger.info(f"✅ Получено названий для {len(product_names)} товаров")
                    else:
                        product_names = {}
                    
                    # Формируем результаты
                    for item in seller_items:
                        parsed = OzonSellerAPI.parse_price_item(item)
                        product_id = parsed.get("product_id")
                        # Приводим product_id к строке для поиска в словаре
                        product_id_key = str(product_id) if product_id else None
                        product_name = product_names.get(product_id_key) if product_id_key and product_names else None
                        
                        result = {
                            "product_id": product_id,
                            "product_id_seller": product_id,  # Для совместимости
                            "offer_id": parsed.get("offer_id"),
                            "product_name": product_name,
                            "cabinet_id": seller_id,
                            "cabinet_name": cabinet_name,
                            "price_seller": parsed.get("seller_price"),
                            "price_old": parsed.get("old_price"),
                            "price_min": parsed.get("min_price"),
                            "currency": parsed.get("currency", "RUB"),
                            "price_current": None,  # Нет данных из публичного каталога
                            "price_original": parsed.get("old_price"),
                            "discount_percent": None,
                            "source_catalog": None,
                            "source_seller": "seller_api",
                        }
                        all_results.append(result)
            return all_results
        
        # ============================================================
        # ПРОБЛЕМА СОПОСТАВЛЕНИЯ:
        # ============================================================
        # Entrypoint API (F12) возвращает:
        #   - "sku" - глобальный идентификатор товара на Ozon
        #   - "offer_id" (может быть, если извлечён из структуры)
        #
        # Seller API возвращает:
        #   - "product_id" - идентификатор товара в кабинете продавца (МОЖЕТ ОТЛИЧАТЬСЯ от SKU!)
        #   - "offer_id" - артикул продавца (уникален для каждого продавца)
        #
        # ВАЖНО: SKU из entrypoint API ≠ product_id из Seller API!
        # ============================================================
        
        # Создаем маппинг SKU -> данные из каталога
        catalog_by_sku = {}
        # Также создаём маппинг по offer_id (если есть)
        catalog_by_offer_id = {}
        
        for product in catalog_products:
            sku = product.get("sku")  # Глобальный SKU из entrypoint API
            offer_id = product.get("offer_id")  # Артикул продавца (если извлечён)
            
            if sku:
                catalog_by_sku[sku] = product
            if offer_id:
                catalog_by_offer_id[offer_id] = product
        
        # Для запроса в Seller API используем SKU (пробуем, может сработать)
        # Но НЕ ОЖИДАЕМ, что product_id из ответа совпадёт с SKU!
        product_ids_for_api = list(catalog_by_sku.keys())
        
        logger.info(f"📊 Уникальных SKU для запроса в Seller API: {len(product_ids_for_api)}")
        
        # Шаг 2: Сопоставление SKU с product_id и offer_id через Seller API
        # Используем /v3/product/info/list для правильного сопоставления
        import os
        account_type = os.getenv('OZON_ACCOUNT_TYPE', 'foreign').lower().strip()
        account_type = account_type if account_type in ('my', 'foreign') else 'foreign'
        
        # Индексы для сопоставления данных из Seller API
        # Ключ: SKU из entrypoint API → значение: {product_id, offer_id, ...}
        seller_info_by_sku = {}
        seller_prices_by_offer_id = {}  # Для цен из /v5/product/info/prices
        seller_api_time = 0.0
        
        # ВСЕГДА пытаемся вызвать Seller API (даже для foreign)
        # Если товары не принадлежат кабинету, API вернет пустой ответ - это нормально
        logger.info("💰 Шаг 2/3: Сопоставление SKU с product_id и offer_id через Seller API...")
        if account_type == 'foreign':
            logger.info("   • OZON_ACCOUNT_TYPE=foreign: пробуем Seller API, но данные могут быть пустыми")
            logger.info("   • (Seller API возвращает данные только для товаров вашего кабинета)")
        
        if product_ids_for_api:
            async with OzonSellerAPI(self.client_id, self.api_key, 
                                     request_delay=self.request_delay) as seller_api:
                # Авто-диагностика: тестовый запрос с 1 SKU
                logger.debug("🔍 Авто-диагностика: тестовый запрос с 1 SKU...")
                test_sku = product_ids_for_api[0]
                test_items = await seller_api.fetch_products_by_sku([test_sku])
                
                if not test_items or len(test_items) == 0:
                    logger.warning(
                        f"⚠️ Seller API диагностика: 0 товаров найдено для тестового SKU {test_sku}"
                    )
                    logger.warning(
                        "   • SKU из публичного каталога не принадлежат вашему кабинету"
                    )
                    logger.info("   • Пропускаем Seller API, используем только данные из каталога")
                    seller_api_time = 0.0
                else:
                    logger.success(
                        f"✅ Seller API диагностика: найдено {len(test_items)} товаров, "
                        f"продолжаем основной запрос"
                    )
                    
                    # Основной запрос: получаем product_id и offer_id по SKU
                    seller_api_start = time.time()
                    seller_items = await seller_api.fetch_products_by_sku(product_ids_for_api)
                    
                    # Индексируем по SKU (основной ключ для сопоставления)
                    for item in seller_items:
                        parsed = OzonSellerAPI.parse_product_info_item(item)
                        sku = parsed.get("sku")
                        if sku:
                            seller_info_by_sku[sku] = parsed
                    
                    seller_api_time = time.time() - seller_api_start
                    
                    logger.info(
                        f"✅ Сопоставлено {len(seller_info_by_sku)} товаров "
                        f"за {seller_api_time:.2f} сек"
                    )
                    logger.info(
                        f"   • SKU → product_id и offer_id успешно сопоставлены"
                    )
                    
                    # Дополнительно: получаем цены через /v5/product/info/prices
                    # Используем product_id из сопоставления
                    if seller_info_by_sku:
                        logger.info("💰 Шаг 2.5/3: Получение цен продавца через /v5/product/info/prices...")
                        product_ids_from_mapping = [
                            int(info["product_id"]) 
                            for info in seller_info_by_sku.values() 
                            if info.get("product_id")
                        ]
                        
                        if product_ids_from_mapping:
                            price_items = await seller_api.fetch_product_prices(
                                product_ids=product_ids_from_mapping
                            )
                            
                            # Индексируем цены по offer_id
                            for item in price_items:
                                parsed = OzonSellerAPI.parse_price_item(item)
                                offer_id = parsed.get("offer_id")
                                if offer_id:
                                    seller_prices_by_offer_id[offer_id] = parsed
                            
                            logger.info(
                                f"✅ Получено цен для {len(seller_prices_by_offer_id)} товаров"
                            )
        else:
                logger.warning("⚠️ Нет SKU для запроса в Seller API")
                seller_api_time = 0.0
        
        # Шаг 3: Объединяем данные
        logger.info("🔗 Шаг 3/3: Объединение данных из двух источников...")
        logger.info(f"   • Товаров из публичного API: {len(catalog_by_sku)}")
        logger.info(f"   • Товаров сопоставлено через /v3/product/info/list: {len(seller_info_by_sku)}")
        logger.info(f"   • Товаров с ценами из /v5/product/info/prices: {len(seller_prices_by_offer_id)}")
        logger.info(f"   • Ключ сопоставления: SKU (через /v3/product/info/list)")
        
        matched_count = 0
        not_matched_count = 0
        
        # СОПОСТАВЛЕНИЕ: используем SKU как ключ
        # seller_info_by_sku содержит сопоставление: SKU → {product_id, offer_id}
        for sku, catalog_data in catalog_by_sku.items():
            # Получаем product_id и offer_id из сопоставления по SKU
            seller_info = seller_info_by_sku.get(sku, {})
            product_id_from_seller = seller_info.get("product_id")
            offer_id_from_seller = seller_info.get("offer_id")
            
            # Получаем цены по offer_id (если есть)
            seller_price_data = {}
            if offer_id_from_seller:
                seller_price_data = seller_prices_by_offer_id.get(offer_id_from_seller, {})
            
            # Создаем объединенную запись
            # offer_id: приоритет из /v3/product/info/list, fallback на публичный API
            offer_id = offer_id_from_seller or catalog_data.get("offer_id")
            
            # Зачёркнутая цена: приоритет из Seller API (old_price из v5), fallback на каталог
            # Это одно и то же поле, но из разных источников - используем более точное (Seller API)
            old_price_from_seller = seller_price_data.get("old_price")
            old_price_from_catalog = catalog_data.get("original_price")
            # Приоритет: Seller API (более точное), fallback: каталог
            final_old_price = old_price_from_seller if old_price_from_seller is not None else old_price_from_catalog
            
            # Пересчитываем скидку, если она не найдена, но есть обе цены
            current_price = catalog_data.get("current_price")
            discount_percent = catalog_data.get("discount_percent")
            if discount_percent is None and current_price is not None and final_old_price is not None:
                if final_old_price > 0 and final_old_price > current_price:
                    discount_percent = round(((final_old_price - current_price) / final_old_price) * 100, 1)
            
            result = {
                # Основные данные
                "product_id": sku,  # SKU из публичного API (глобальный идентификатор)
                "product_id_seller": product_id_from_seller,  # ID товара в кабинете продавца
                "offer_id": offer_id,  # Артикул продавца (из /v3/product/info/list или публичного API)
                "product_name": catalog_data.get("product_name", ""),
                "cabinet_id": seller_id,
                "cabinet_name": cabinet_name,
                
                # Цены из публичного каталога (что видит покупатель) - ОСНОВНЫЕ ДАННЫЕ
                "price_current": current_price,  # Цена со скидкой
                "price_original": final_old_price,  # Зачёркнутая цена (приоритет: Seller API old_price, fallback: каталог)
                "discount_percent": discount_percent,
                
                # Цены из Seller API (цены продавца) - ДОПОЛНИТЕЛЬНЫЕ ДАННЫЕ
                "price_seller": seller_price_data.get("seller_price"),  # Цена продавца (без акций)
                "price_old": final_old_price,  # Зачёркнутая цена (то же, что price_original - из Seller API old_price)
                "price_min": seller_price_data.get("min_price"),  # Минимальная цена
                
                # Источники данных
                "source_catalog": "catalog_api",
                "source_seller": "seller_api_v3" if seller_info else None,
            }
            
            all_results.append(result)
            
            if seller_info:
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
                f"⚠️ {not_matched_count} товар(ов) не найдены в Seller API. "
                f"Возможно, они не принадлежат этому продавцу или недоступны через API."
            )
        
        return all_results
