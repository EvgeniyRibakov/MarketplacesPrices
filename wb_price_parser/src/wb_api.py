"""
Асинхронный клиент для работы с внутренним API Wildberries
"""
import asyncio
import aiohttp
import logging
from typing import List, Dict, Optional, Any
from dataclasses import dataclass

from .config import Config
from .utils import build_wb_catalog_url, convert_price_to_rubles, retry_with_backoff, sanitize_for_logging


@dataclass
class WBProduct:
    """Временная структура для товара из JSON API"""
    id: int
    nm_id: int
    name: str
    price_basic: float
    price_product: float
    price_card: Optional[float] = None
    product_url: Optional[str] = None
    brand: Optional[str] = None
    supplier_article: Optional[str] = None


class WBAPIClient:
    """Асинхронный клиент для работы с внутренним API WB"""
    
    def __init__(self, config: Config, logger: Optional[logging.Logger] = None):
        """
        Инициализация клиента
        
        Args:
            config: Конфигурация проекта
            logger: Логгер (опционально)
        """
        self.config = config
        self.logger = logger or logging.getLogger(__name__)
        self.session: Optional[aiohttp.ClientSession] = None
        self.semaphore = asyncio.Semaphore(config.concurrency)
        self.error_count = 0
        self.max_errors_before_backoff = 10
        
        # Заголовки для запросов
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Accept-Language": "ru-RU,ru;q=0.9",
        }
    
    async def __aenter__(self):
        """Асинхронный контекстный менеджер - вход"""
        timeout = aiohttp.ClientTimeout(total=self.config.request_timeout)
        self.session = aiohttp.ClientSession(
            headers=self.headers,
            timeout=timeout
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Асинхронный контекстный менеджер - выход"""
        if self.session:
            await self.session.close()
    
    @retry_with_backoff(max_retries=3, base_delay=1.0)
    async def _fetch_page(self, page: int) -> Dict[str, Any]:
        """
        Запрос одной страницы каталога
        
        Args:
            page: Номер страницы
        
        Returns:
            JSON ответ от API
        """
        url = build_wb_catalog_url(
            brand_id=self.config.wb_brand_id,
            dest=self.config.wb_dest,
            spp=self.config.wb_spp,
            page=page
        )
        
        async with self.semaphore:
            try:
                # Задержка между запросами
                if self.config.request_delay > 0:
                    await asyncio.sleep(self.config.request_delay)
                
                self.logger.debug(f"Запрос страницы {page}: {url}")
                
                async with self.session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.error_count = 0  # Сброс счётчика ошибок при успехе
                        return data
                    elif response.status == 429:
                        # Rate limit - увеличиваем задержку
                        self.logger.warning(f"Rate limit на странице {page}, увеличиваем задержку")
                        await asyncio.sleep(5)
                        raise aiohttp.ClientResponseError(
                            request_info=response.request_info,
                            history=response.history,
                            status=429
                        )
                    else:
                        error_text = await response.text()
                        self.logger.error(
                            f"Ошибка {response.status} на странице {page}: "
                            f"{sanitize_for_logging(error_text)}"
                        )
                        response.raise_for_status()
                        return {}
            except asyncio.TimeoutError:
                self.logger.error(f"Timeout при запросе страницы {page}")
                raise
            except aiohttp.ClientError as e:
                self.error_count += 1
                if self.error_count >= self.max_errors_before_backoff:
                    self.logger.warning(
                        f"Много ошибок ({self.error_count}), уменьшаем concurrency"
                    )
                    # Можно уменьшить concurrency здесь
                raise
    
    def _parse_product(self, item: Dict[str, Any]) -> Optional[WBProduct]:
        """
        Парсинг одного товара из JSON ответа
        
        Args:
            item: Элемент из JSON массива товаров
        
        Returns:
            WBProduct или None если данные некорректны
        """
        try:
            # Извлекаем основные поля
            product_id = item.get("id") or item.get("nmId")
            nm_id = item.get("nmId") or item.get("id")
            name = item.get("name") or item.get("title", "")
            
            # Извлекаем цены
            price_data = item.get("price", {})
            price_basic_kopecks = price_data.get("basic", 0)
            price_product_kopecks = price_data.get("product", 0)
            price_card_kopecks = price_data.get("card") or price_data.get("priceCard")
            
            # Конвертируем в рубли
            price_basic = convert_price_to_rubles(price_basic_kopecks)
            price_product = convert_price_to_rubles(price_product_kopecks)
            price_card = convert_price_to_rubles(price_card_kopecks) if price_card_kopecks else None
            
            # URL товара
            product_url = None
            if "link" in item:
                product_url = item["link"]
            elif "url" in item:
                product_url = item["url"]
            elif nm_id:
                # Формируем URL по nmId
                product_url = f"https://www.wildberries.ru/catalog/{nm_id}/detail.aspx"
            
            # Артикул поставщика
            supplier_article = item.get("supplierArticle") or item.get("vendorCode") or str(nm_id)
            
            return WBProduct(
                id=product_id,
                nm_id=nm_id,
                name=name,
                price_basic=price_basic,
                price_product=price_product,
                price_card=price_card,
                product_url=product_url,
                brand=item.get("brand"),
                supplier_article=supplier_article
            )
        except (KeyError, ValueError, TypeError) as e:
            self.logger.warning(f"Ошибка парсинга товара: {e}, данные: {item.get('id', 'unknown')}")
            return None
    
    async def fetch_all_products(self) -> List[WBProduct]:
        """
        Получение всех товаров со всех страниц каталога
        
        Returns:
            Список всех товаров
        """
        all_products = []
        page = 1
        max_pages = 1000  # Защита от бесконечного цикла
        
        self.logger.info("Начинаем сбор товаров с API WB...")
        
        while page <= max_pages:
            try:
                data = await self._fetch_page(page)
                
                # Проверяем структуру ответа
                products_data = data.get("data", {}).get("products", [])
                if not products_data:
                    # Пробуем другие варианты структуры
                    products_data = data.get("products", [])
                if not products_data:
                    products_data = data.get("data", [])
                
                if not products_data:
                    self.logger.info(f"Страница {page} пуста, завершаем сбор")
                    break
                
                # Парсим товары со страницы
                page_products = []
                for item in products_data:
                    product = self._parse_product(item)
                    if product:
                        page_products.append(product)
                
                all_products.extend(page_products)
                self.logger.info(
                    f"Страница {page}: получено {len(page_products)} товаров "
                    f"(всего: {len(all_products)})"
                )
                
                # Проверяем, есть ли ещё страницы
                # Обычно API возвращает информацию о пагинации
                total_pages = (
                    data.get("data", {}).get("totalPages") or
                    data.get("totalPages") or
                    data.get("data", {}).get("pages") or
                    0
                )
                
                if total_pages > 0 and page >= total_pages:
                    break
                
                # Если на странице меньше товаров чем ожидалось, возможно это последняя
                if len(products_data) < 30:  # Обычно 30 товаров на странице
                    break
                
                page += 1
                
            except Exception as e:
                self.logger.error(f"Ошибка при получении страницы {page}: {e}")
                # Пробуем следующую страницу
                page += 1
                if page > 10:  # Защита от множественных ошибок
                    break
        
        self.logger.info(f"Сбор завершён. Всего получено товаров: {len(all_products)}")
        return all_products
    
    async def fetch_page(self, page: int) -> List[WBProduct]:
        """
        Получение товаров с одной страницы (для discovery и тестирования)
        
        Args:
            page: Номер страницы
        
        Returns:
            Список товаров со страницы
        """
        data = await self._fetch_page(page)
        
        products_data = data.get("data", {}).get("products", [])
        if not products_data:
            products_data = data.get("products", [])
        if not products_data:
            products_data = data.get("data", [])
        
        products = []
        for item in products_data:
            product = self._parse_product(item)
            if product:
                products.append(product)
        
        return products


