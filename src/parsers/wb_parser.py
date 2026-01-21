"""Парсер цен для Wildberries."""
from typing import Dict, List, Optional
from pathlib import Path
from loguru import logger
from src.api.wb_catalog_api import WBCatalogAPI
try:
    from src.api.wb_api import WildberriesAPI
    from src.utils.articles_reader import read_wb_articles, find_articles_file
except ImportError:
    # Для обратной совместимости
    WildberriesAPI = None
    read_wb_articles = None
    find_articles_file = None


class WildberriesParser:
    """Парсер цен для Wildberries."""
    
    def __init__(self, api_key: str, cabinet_name: str, cabinet_id: str, request_delay: float = 0.5):
        """Инициализация парсера.
        
        Args:
            api_key: API ключ Wildberries
            cabinet_name: Название кабинета
            cabinet_id: ID кабинета
            request_delay: Задержка между запросами
        """
        self.cabinet_name = cabinet_name
        self.cabinet_id = cabinet_id
        if WildberriesAPI:
            self.api = WildberriesAPI(api_key, request_delay=request_delay)
        else:
            self.api = None
    
    def parse_basic_prices(self, articles_file_path: Optional[Path] = None) -> List[Dict]:
        """Парсинг базовых цен через официальное API (требует API ключ)."""
        if not self.api:
            logger.warning("WildberriesAPI не доступен - требуется API ключ")
            return []
        
        logger.info(f"Начинаем парсинг базовых цен для кабинета {self.cabinet_name}...")
        
        # Читаем артикулы из Articles.xlsx
        if not articles_file_path and find_articles_file:
            articles_file_path = find_articles_file()
        
        if not articles_file_path:
            logger.error("Не удалось найти файл Articles.xlsx")
            return []
        
        logger.info(f"Читаем артикулы из {articles_file_path}...")
        if read_wb_articles:
            vendor_codes = read_wb_articles(articles_file_path)
        else:
            logger.error("read_wb_articles не доступен")
            return []
        
        if not vendor_codes:
            logger.warning(f"Не найдено артикулов в файле Articles.xlsx")
            return []
        
        logger.info(f"Найдено артикулов для обработки: {len(vendor_codes)}")
        
        # Разбиваем на батчи по 100 артикулов (лимит API)
        batch_size = 100
        all_results = []
        
        for i in range(0, len(vendor_codes), batch_size):
            batch = vendor_codes[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (len(vendor_codes) + batch_size - 1) // batch_size
            
            logger.info(f"Обработка батча {batch_num}/{total_batches} ({len(batch)} артикулов)...")
            
            # Получаем цены по артикулам через закреплённый эндпоинт
            prices_data = self.api.get_prices_by_articles(batch)
            
            if not prices_data:
                logger.warning(f"Не удалось получить цены для батча {batch_num}")
                continue
            
            # Обрабатываем полученные данные о ценах
            for price_item in prices_data:
                vendor_code = price_item.get("vendorCode") or price_item.get("vendor_code")
                nm_id = price_item.get("nmID") or price_item.get("nmId")
                
                # Структура API: данные о ценах находятся в массиве sizes
                sizes = price_item.get("sizes", [])
                
                if sizes:
                    for size in sizes:
                        base_price = size.get("price")
                        discounted_price = size.get("discountedPrice")
                        club_discounted_price = size.get("clubDiscountedPrice")
                        size_id = size.get("sizeID")
                        tech_size_name = size.get("techSizeName", "")
                        
                        all_results.append({
                            "cabinet": self.cabinet_name,
                            "cabinet_id": self.cabinet_id,
                            "nm_id": nm_id,
                            "vendor_code": vendor_code,
                            "size_id": size_id,
                            "size_name": tech_size_name,
                            "base_price": base_price,
                            "discounted_price": discounted_price,
                            "club_discounted_price": club_discounted_price,
                        })
        
        logger.success(f"Обработано товаров: {len(all_results)}")
        return all_results
    
    def parse_card_prices(self) -> List[Dict]:
        """Парсинг цен с WB-картой через XPath (существующее решение).
        
        Returns:
            Список товаров с ценами с картой
        """
        logger.info(f"Начинаем парсинг цен с WB-картой для кабинета {self.cabinet_name}...")
        
        # TODO: Адаптировать существующее XPath-решение
        logger.warning("Парсинг цен с WB-картой ещё не реализован")
        return []
    
    def parse_spp_prices(self) -> List[Dict]:
        """Парсинг цен после СПП (чёрная цена) - требует research.
        
        Returns:
            Список товаров с ценами после СПП
        """
        logger.info(f"Начинаем парсинг цен после СПП для кабинета {self.cabinet_name}...")
        
        # TODO: Research - найти API или XPath для получения цены после СПП
        logger.warning("Парсинг цен после СПП требует research - не реализован")
        return []
    
    async def parse_brand_catalog(self, brand_id: int, brand_name: str, 
                                  dest: int, spp: int = 30,
                                  fsupplier: Optional[str] = None,
                                  cookies: Optional[str] = None) -> List[Dict]:
        """Парсинг каталога бренда через внутренний API.
        
        Args:
            brand_id: ID бренда
            brand_name: Название бренда
            dest: ID региона/ПВЗ
            spp: Параметр spp (обычно 30)
            fsupplier: Фильтр по кабинетам (опционально)
            cookies: Cookies из браузера в формате "name1=value1; name2=value2"
        
        Returns:
            Список товаров с ценами из каталога бренда
        """
        import time
        parse_start_time = time.time()
        logger.info(f"🚀 Начинаем парсинг каталога бренда {brand_name} (ID: {brand_id})...")
        
        all_results = []
        total_products = 0
        filtered_products = 0
        
        async with WBCatalogAPI(request_delay=0.1, max_concurrent=5, cookies=cookies) as api:
            fetch_start = time.time()
            products = await api.fetch_brand_catalog(
                brand_id=brand_id,
                dest=dest,
                spp=spp,
                fsupplier=fsupplier
            )
            fetch_time = time.time() - fetch_start
            
            total_products = len(products)
            logger.info(
                f"📦 Получено {total_products} товаров из API за {fetch_time:.2f} сек. "
                f"Начинаем парсинг и фильтрацию..."
            )
            
            parse_products_start = time.time()
            for product in products:
                parsed_items = WBCatalogAPI.parse_product(product, brand_id, brand_name)
                if parsed_items:
                    all_results.extend(parsed_items)
                else:
                    filtered_products += 1
            
            parse_products_time = time.time() - parse_products_start
        
        total_time = time.time() - parse_start_time
        
        logger.success(
            f"✅ Бренд {brand_name}: обработано {len(all_results)} записей "
            f"(отфильтровано {filtered_products} товаров от перекупов, "
            f"всего товаров из API: {total_products}). "
            f"Время парсинга: {parse_products_time:.2f} сек, "
            f"общее время: {total_time:.2f} сек"
        )
        
        return all_results
    
    async def parse_seller_catalog(self, supplier_id: int, dest: int, spp: int = 30,
                                   cookies: Optional[str] = None) -> List[Dict]:
        """Парсинг каталога продавца через внутренний API.
        
        Args:
            supplier_id: ID продавца (supplier_id)
            dest: ID региона/ПВЗ
            spp: Параметр spp (обычно 30)
            cookies: Опциональные cookies в формате "name1=value1; name2=value2" 
                    (необязательно, но рекомендуется для обхода антибота)
        
        Returns:
            Список товаров с ценами из каталога продавца
        """
        import time
        from src.api.wb_catalog_api import WBCatalogAPI
        
        parse_start_time = time.time()
        cabinet_name = WBCatalogAPI.CABINET_MAPPING.get(supplier_id, f"UNKNOWN_{supplier_id}")
        logger.info(f"🚀 Начинаем парсинг каталога продавца {supplier_id} ({cabinet_name})...")
        
        all_results = []
        total_products = 0
        
        async with WBCatalogAPI(request_delay=0.1, max_concurrent=5, cookies=cookies) as api:
            fetch_start = time.time()
            products = await api.fetch_seller_catalog(
                supplier_id=supplier_id,
                dest=dest,
                spp=spp
            )
            fetch_time = time.time() - fetch_start
            
            total_products = len(products)
            logger.info(
                f"📦 Получено {total_products} товаров из API за {fetch_time:.2f} сек. "
                f"Начинаем парсинг..."
            )
            
            parse_products_start = time.time()
            for product in products:
                parsed_items = WBCatalogAPI.parse_product(product, supplier_id)
                if parsed_items:
                    all_results.extend(parsed_items)
            
            parse_products_time = time.time() - parse_products_start
        
        total_time = time.time() - parse_start_time
        
        logger.success(
            f"✅ Продавец {supplier_id} ({cabinet_name}): обработано {len(all_results)} записей "
            f"(всего товаров из API: {total_products}). "
            f"Время парсинга: {parse_products_time:.2f} сек, "
            f"общее время: {total_time:.2f} сек"
        )
        
        return all_results
