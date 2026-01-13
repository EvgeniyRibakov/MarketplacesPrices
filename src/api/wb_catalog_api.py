"""Модуль для работы с внутренним API каталога брендов Wildberries."""
import asyncio
from typing import List, Dict, Optional
from urllib.parse import urlencode
import aiohttp
from loguru import logger


class WBCatalogAPI:
    """Клиент для работы с внутренним API каталога брендов WB."""
    
    BASE_URL = "https://www.wildberries.ru/__internal/u-catalog/brands/v4/catalog"
    
    # Маппинг supplierId -> название кабинета
    CABINET_MAPPING = {
        53607: "MAU",
        121614: "MAB",
        174711: "MMA",
        224650: "COSMO",
        1140223: "DREAMLAB",
        4428365: "BEAUTYLAB"
    }
    
    def __init__(self, request_delay: float = 0.1, max_concurrent: int = 5, cookies: Optional[str] = None):
        """Инициализация клиента.
        
        Args:
            request_delay: Задержка между запросами (секунды)
            max_concurrent: Максимальное количество параллельных запросов
            cookies: Опциональные cookies из браузера в формате "name1=value1; name2=value2"
        """
        self.request_delay = request_delay
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.session: Optional[aiohttp.ClientSession] = None
        self.custom_cookies = cookies
        self._cookies_header: Optional[str] = None
    
    async def __aenter__(self):
        """Асинхронный контекстный менеджер - вход."""
        # Полный User-Agent современного браузера Chrome
        user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
        
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            cookie_jar=aiohttp.CookieJar(unsafe=True),
            headers={
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
            }
        )
        
        # Если переданы cookies из браузера, добавляем их
        if self.custom_cookies:
            await self._load_custom_cookies()
        
        # Получаем cookies с главной страницы перед API запросами
        await self._initialize_session()
        
        return self
    
    async def _load_custom_cookies(self):
        """Загружает cookies из строки формата 'name1=value1; name2=value2'."""
        try:
            from http.cookies import SimpleCookie
            from yarl import URL
            
            # Парсим строку cookies
            cookie = SimpleCookie()
            cookie.load(self.custom_cookies)
            
            # Добавляем каждый cookie в jar
            cookies_dict = {}
            for name, morsel in cookie.items():
                cookies_dict[name] = morsel.value
            
            # Добавляем cookies в jar используя объект URL
            url = URL("https://www.wildberries.ru")
            self.session.cookie_jar.update_cookies(cookies_dict, url)
            
            # Сохраняем cookies для использования в заголовках (на случай если jar не сработает)
            self._cookies_header = "; ".join([f"{name}={value}" for name, value in cookies_dict.items()])
            
            logger.info(f"Загружено {len(cookies_dict)} cookies из конфигурации: {', '.join(cookies_dict.keys())}")
        except Exception as e:
            logger.warning(f"Ошибка при загрузке cookies: {e}")
            logger.exception("Детали ошибки:")
            self._cookies_header = None
    
    async def _initialize_session(self):
        """Инициализирует сессию, получая cookies с главной страницы."""
        try:
            logger.info("Инициализация сессии: получение cookies с главной страницы...")
            
            # Делаем запрос на главную страницу для получения базовых cookies
            async with self.session.get("https://www.wildberries.ru/") as response:
                cookies_count = len(self.session.cookie_jar)
                logger.info(f"Получено cookies с главной страницы: {cookies_count}")
                
                # Небольшая задержка для имитации поведения браузера
                await asyncio.sleep(0.5)
                
                # Пробуем получить токен антибота (может не сработать без JS)
                try:
                    token_url = "https://www.wildberries.ru/__wbaas/challenges/antibot/token"
                    async with self.session.get(token_url) as token_response:
                        if token_response.status == 200:
                            logger.debug("Токен антибота получен")
                        else:
                            logger.debug(f"Токен не получен: статус {token_response.status}")
                except:
                    pass  # Игнорируем ошибки получения токена
                        
        except Exception as e:
            logger.warning(f"Не удалось инициализировать сессию: {e}, продолжаем...")
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Асинхронный контекстный менеджер - выход."""
        if self.session:
            await self.session.close()
    
    def _build_url(self, brand_id: int, dest: int, spp: int = 30, 
                   page: int = 1, fsupplier: Optional[str] = None) -> str:
        """Строит URL для запроса каталога бренда."""
        params = {
            "ab_testing": "false",
            "appType": "1",
            "brand": str(brand_id),
            "curr": "rub",
            "dest": str(dest),
            "hide_dtype": "9",
            "hide_vflags": "4294967296",
            "lang": "ru",
            "page": str(page),
            "sort": "popular",
            "spp": str(spp),
        }
        
        if fsupplier:
            params["fsupplier"] = fsupplier
        
        query_string = urlencode(params)
        return f"{self.BASE_URL}?{query_string}"
    
    async def _fetch_page(self, brand_id: int, dest: int, spp: int, 
                         page: int, fsupplier: Optional[str] = None) -> Optional[Dict]:
        """Получает одну страницу каталога бренда."""
        url = self._build_url(brand_id, dest, spp, page, fsupplier)
        
        async with self.semaphore:
            try:
                await asyncio.sleep(self.request_delay)
                
                # Обновляем заголовки для API запроса
                api_headers = {
                    "Accept": "application/json, text/plain, */*",
                    "Referer": "https://www.wildberries.ru/",
                    "Origin": "https://www.wildberries.ru",
                    "Sec-Fetch-Dest": "empty",
                    "Sec-Fetch-Mode": "cors",
                    "Sec-Fetch-Site": "same-origin",
                }
                
                # Добавляем cookies в заголовки, если они есть (на случай если cookie_jar не сработает)
                if self._cookies_header:
                    api_headers["Cookie"] = self._cookies_header
                
                async with self.session.get(url, headers=api_headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data
                    elif response.status == 498:
                        # Детальная диагностика для статуса 498
                        response_text = await response.text()
                        logger.error(
                            f"Ошибка 498 при запросе страницы {page} для бренда {brand_id}\n"
                            f"URL: {url}\n"
                            f"Response headers: {dict(response.headers)}\n"
                            f"Response body (первые 500 символов): {response_text[:500]}"
                        )
                        return None
                    else:
                        logger.warning(
                            f"Ошибка запроса страницы {page}: статус {response.status}\n"
                            f"URL: {url}"
                        )
                        return None
                        
            except asyncio.TimeoutError:
                logger.error(f"Таймаут при запросе страницы {page}")
                return None
            except Exception as e:
                logger.error(f"Ошибка при запросе страницы {page}: {e}")
                logger.exception("Детали исключения:")
                return None
    
    async def fetch_brand_catalog(self, brand_id: int, dest: int, spp: int = 30,
                                 fsupplier: Optional[str] = None) -> List[Dict]:
        """Получает весь каталог бренда (все страницы)."""
        logger.info(f"Начинаем загрузку каталога бренда {brand_id}...")
        
        all_products = []
        page = 1
        
        first_page = await self._fetch_page(brand_id, dest, spp, page, fsupplier)
        
        if not first_page:
            logger.error(f"Не удалось получить первую страницу для бренда {brand_id}")
            return []
        
        products = first_page.get("products", [])
        total = first_page.get("total", 0)
        all_products.extend(products)
        
        logger.info(f"Страница 1: получено {len(products)} товаров, всего: {total}")
        
        products_per_page = len(products)
        if products_per_page > 0:
            total_pages = (total + products_per_page - 1) // products_per_page
        else:
            total_pages = 1
        
        if total_pages > 1:
            tasks = []
            for page_num in range(2, total_pages + 1):
                task = self._fetch_page(brand_id, dest, spp, page_num, fsupplier)
                tasks.append(task)
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for page_num, result in enumerate(results, start=2):
                if isinstance(result, Exception):
                    logger.error(f"Ошибка при загрузке страницы {page_num}: {result}")
                    continue
                
                if result:
                    page_products = result.get("products", [])
                    all_products.extend(page_products)
                    logger.info(f"Страница {page_num}: получено {len(page_products)} товаров")
        
        logger.success(f"Бренд {brand_id}: всего получено {len(all_products)} товаров")
        return all_products
    
    @staticmethod
    def parse_product(product: Dict, brand_id: int, brand_name: str) -> List[Dict]:
        """Парсит товар из JSON ответа API."""
        results = []
        
        product_id = product.get("id")
        product_name = product.get("name", "")
        supplier_id = product.get("supplierId")
        supplier_name = product.get("supplier", "")
        
        cabinet_name = WBCatalogAPI.CABINET_MAPPING.get(supplier_id, f"UNKNOWN_{supplier_id}")
        cabinet_id = supplier_id
        
        sizes = product.get("sizes", [])
        
        if not sizes:
            price_data = product.get("price", {})
            results.append({
                "brand_id": brand_id,
                "brand_name": brand_name,
                "product_id": product_id,
                "product_name": product_name,
                "cabinet_id": cabinet_id,
                "cabinet_name": cabinet_name,
                "supplier_id": supplier_id,
                "supplier_name": supplier_name,
                "size_id": None,
                "size_name": None,
                "price_basic": price_data.get("basic", 0) / 100 if price_data.get("basic") else None,
                "price_product": price_data.get("product", 0) / 100 if price_data.get("product") else None,
                "price_card": None,
                "source_price_basic": "api-catalog",
                "source_price_product": "api-catalog",
                "source_price_card": None,
            })
        else:
            for size in sizes:
                price_data = size.get("price", {})
                size_id = size.get("optionId")
                size_name = size.get("name", "") or size.get("origName", "")
                
                results.append({
                    "brand_id": brand_id,
                    "brand_name": brand_name,
                    "product_id": product_id,
                    "product_name": product_name,
                    "cabinet_id": cabinet_id,
                    "cabinet_name": cabinet_name,
                    "supplier_id": supplier_id,
                    "supplier_name": supplier_name,
                    "size_id": size_id,
                    "size_name": size_name,
                    "price_basic": price_data.get("basic", 0) / 100 if price_data.get("basic") else None,
                    "price_product": price_data.get("product", 0) / 100 if price_data.get("product") else None,
                    "price_card": None,
                    "source_price_basic": "api-catalog",
                    "source_price_product": "api-catalog",
                    "source_price_card": None,
                })
        
        return results
