"""Модуль для работы с внутренним API каталога брендов Wildberries."""
import asyncio
from typing import List, Dict, Optional
from urllib.parse import urlencode
from curl_cffi.requests import AsyncSession
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
    
    def __init__(self, request_delay: float = 0.1, max_concurrent: int = 5, cookies: Optional[str] = None, 
                 auto_get_cookies: bool = True):
        """Инициализация клиента.
        
        Args:
            request_delay: Задержка между запросами (секунды)
            max_concurrent: Максимальное количество параллельных запросов
            cookies: Опциональные cookies из браузера в формате "name1=value1; name2=value2"
            auto_get_cookies: Автоматически получать cookies из браузера если не переданы
        """
        self.request_delay = request_delay
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.session: Optional[AsyncSession] = None
        self.custom_cookies = cookies
        self.auto_get_cookies = auto_get_cookies
        self._cookies_header: Optional[str] = None
        self._cookies_dict: Dict[str, str] = {}  # Кэш cookies для быстрого доступа
    
    async def __aenter__(self):
        """Асинхронный контекстный менеджер - вход."""
        # Создаем сессию curl_cffi с эмуляцией Chrome 131
        # impersonate эмулирует TLS fingerprint браузера
        self.session = AsyncSession(
            impersonate="chrome131",  # Эмулирует Chrome 131 TLS fingerprint
            timeout=30,
        )
        
        # Если переданы cookies из браузера, добавляем их
        if self.custom_cookies:
            await self._load_custom_cookies()
        elif self.auto_get_cookies:
            # Пробуем автоматически получить cookies из браузера
            await self._load_cookies_from_browser()
        
        # Получаем cookies с главной страницы перед API запросами
        await self._initialize_session()
        
        return self
    
    async def _load_cookies_from_browser(self):
        """Автоматически загружает cookies из браузера Chrome."""
        try:
            # Импортируем в функции, чтобы не было проблем если библиотека не установлена
            import sys
            from pathlib import Path
            # Добавляем путь к корню проекта для импорта
            project_root = Path(__file__).parent.parent.parent
            if str(project_root) not in sys.path:
                sys.path.insert(0, str(project_root))
            
            from src.utils.browser_cookies import get_wb_cookies
            
            logger.info("Попытка автоматического получения cookies из браузера Chrome...")
            
            # Получаем cookies (синхронная функция, но вызываем в executor)
            loop = asyncio.get_event_loop()
            cookies_string = await loop.run_in_executor(None, get_wb_cookies, True)
            
            if cookies_string:
                self.custom_cookies = cookies_string
                await self._load_custom_cookies()
                logger.success("✓ Cookies успешно получены из браузера")
            else:
                logger.warning("Не удалось получить cookies из браузера автоматически")
                
        except ImportError as e:
            logger.warning(f"Библиотеки для работы с браузером не установлены: {e}")
            logger.info("Установите: python -m pip install undetected-chromedriver selenium")
        except Exception as e:
            logger.warning(f"Ошибка при автоматическом получении cookies: {e}")
            logger.debug("Продолжаем без автоматических cookies")
    
    async def _refresh_cookies_from_browser(self):
        """Обновляет cookies из браузера (используется при ошибке 498)."""
        try:
            import sys
            from pathlib import Path
            # Добавляем путь к корню проекта для импорта
            project_root = Path(__file__).parent.parent.parent
            if str(project_root) not in sys.path:
                sys.path.insert(0, str(project_root))
            
            from src.utils.browser_cookies import get_wb_cookies
            
            logger.info("Обновление cookies из браузера...")
            
            loop = asyncio.get_event_loop()
            cookies_string = await loop.run_in_executor(None, get_wb_cookies, True)
            
            if cookies_string:
                self.custom_cookies = cookies_string
                await self._load_custom_cookies()
                logger.success("✓ Cookies обновлены из браузера")
                return True
            else:
                logger.warning("Не удалось обновить cookies из браузера")
                return False
                
        except Exception as e:
            logger.warning(f"Ошибка при обновлении cookies: {e}")
            return False
    
    async def _load_custom_cookies(self):
        """Загружает cookies из строки формата 'name1=value1; name2=value2'."""
        try:
            from http.cookies import SimpleCookie
            
            # Парсим строку cookies
            cookie = SimpleCookie()
            cookie.load(self.custom_cookies)
            
            # Добавляем каждый cookie в словарь
            cookies_dict = {}
            for name, morsel in cookie.items():
                cookies_dict[name] = morsel.value
            
            # Обновляем кэш cookies
            self._cookies_dict.update(cookies_dict)
            
            # Сохраняем cookies для использования в заголовках
            self._cookies_header = "; ".join([f"{name}={value}" for name, value in cookies_dict.items()])
            
            # Проверяем наличие важных cookies
            important_cookies = ["wbx-validation-key", "x_wbaas_token", "_wbauid", "_cp", "routeb"]
            found_important = [c for c in important_cookies if c in cookies_dict]
            missing_important = [c for c in important_cookies if c not in cookies_dict]
            
            logger.info(f"Загружено {len(cookies_dict)} cookies из конфигурации: {', '.join(cookies_dict.keys())}")
            
            if found_important:
                logger.info(f"✓ Найдены важные cookies: {', '.join(found_important)}")
            
            if missing_important:
                logger.warning(f"⚠ Отсутствуют важные cookies: {', '.join(missing_important)}")
                logger.warning("Это может привести к блокировке запросов антибот-защитой")
                
        except Exception as e:
            logger.warning(f"Ошибка при загрузке cookies: {e}")
            logger.exception("Детали ошибки:")
            self._cookies_header = None
    
    async def _initialize_session(self):
        """Инициализирует сессию, получая cookies с главной страницы."""
        try:
            logger.info("Инициализация сессии: получение cookies с главной страницы...")
            
            # Делаем запрос на главную страницу для получения базовых cookies
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
            }
            
            # Добавляем cookies если есть
            if self._cookies_header:
                headers["Cookie"] = self._cookies_header
            
            response = await self.session.get("https://www.wildberries.ru/", headers=headers)
            
            # Обновляем cookies из ответа
            if response.cookies:
                for name, value in response.cookies.items():
                    self._cookies_dict[name] = value
                # Обновляем заголовок cookies
                self._cookies_header = "; ".join([f"{k}={v}" for k, v in self._cookies_dict.items()])
            
            cookies_count = len(self._cookies_dict)
            logger.info(f"Получено cookies с главной страницы: {cookies_count}")
            
            # Небольшая задержка для имитации поведения браузера
            await asyncio.sleep(1.0)
            
            # Пробуем получить токен антибота через разные эндпоинты
            token_urls = [
                "https://www.wildberries.ru/__wbaas/challenges/antibot/token",
                "https://www.wildberries.ru/__wbaas/challenges/antibot/verify"
            ]
            
            for token_url in token_urls:
                try:
                    token_headers = {
                        "Accept": "application/json",
                        "Referer": "https://www.wildberries.ru/",
                    }
                    if self._cookies_header:
                        token_headers["Cookie"] = self._cookies_header
                    
                    token_response = await self.session.get(token_url, headers=token_headers)
                    if token_response.status_code == 200:
                        try:
                            token_data = token_response.json()
                            logger.debug(f"Токен антибота получен с {token_url}")
                            # Сохраняем токен если он есть в ответе
                            if isinstance(token_data, dict) and "token" in token_data:
                                token = token_data["token"]
                                self._cookies_dict["x_wbaas_token"] = token
                                self._cookies_header = "; ".join([f"{k}={v}" for k, v in self._cookies_dict.items()])
                                logger.debug("Токен добавлен в cookies")
                                break
                        except Exception:
                            pass
                    else:
                        logger.debug(f"Токен не получен с {token_url}: статус {token_response.status_code}")
                except Exception as e:
                    logger.debug(f"Ошибка при получении токена с {token_url}: {e}")
                    continue
                        
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
                         page: int, fsupplier: Optional[str] = None, retry_count: int = 0) -> Optional[Dict]:
        """Получает одну страницу каталога бренда."""
        url = self._build_url(brand_id, dest, spp, page, fsupplier)
        max_retries = 2
        
        async with self.semaphore:
            try:
                await asyncio.sleep(self.request_delay)
                
                # Используем кэшированные cookies
                cookies_dict = self._cookies_dict.copy()
                
                # Формируем строку cookies для заголовка
                cookies_string = "; ".join([f"{k}={v}" for k, v in cookies_dict.items()]) if cookies_dict else None
                
                # Обновляем заголовки для API запроса (более реалистичные)
                api_headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                    "Accept": "application/json, text/plain, */*",
                    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Referer": "https://www.wildberries.ru/",
                    "Origin": "https://www.wildberries.ru",
                    "Connection": "keep-alive",
                    "Sec-Fetch-Dest": "empty",
                    "Sec-Fetch-Mode": "cors",
                    "Sec-Fetch-Site": "same-origin",
                    "Cache-Control": "no-cache",
                    "Pragma": "no-cache",
                    "sec-ch-ua": '"Chromium";v="131", "Not_A Brand";v="24"',
                    "sec-ch-ua-mobile": "?0",
                    "sec-ch-ua-platform": '"Windows"',
                }
                
                # Добавляем cookies в заголовки
                if cookies_string:
                    api_headers["Cookie"] = cookies_string
                    logger.debug(f"Отправляем {len(cookies_dict)} cookies в заголовке")
                
                # Логируем ключевые cookies
                important_cookies = ["wbx-validation-key", "x_wbaas_token", "_wbauid", "_cp", "routeb"]
                found_important = [c for c in important_cookies if c in cookies_dict]
                if found_important:
                    logger.debug(f"Найдены важные cookies: {', '.join(found_important)}")
                
                response = await self.session.get(url, headers=api_headers)
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                        # Обновляем cookies из ответа
                        if response.cookies:
                            for name, value in response.cookies.items():
                                self._cookies_dict[name] = value
                            self._cookies_header = "; ".join([f"{k}={v}" for k, v in self._cookies_dict.items()])
                        return data
                    except Exception as e:
                        logger.error(f"Ошибка парсинга JSON ответа: {e}")
                        return None
                elif response.status_code == 498:
                    # Детальная диагностика для статуса 498
                    try:
                        response_text = response.text
                    except:
                        response_text = ""
                    
                    # Проверяем, есть ли в ответе информация о токене
                    if "x_wbaas_token" in response_text.lower() or "antibot" in response_text.lower():
                        logger.warning("Обнаружена антибот-защита. Попытка обновить токен...")
                        
                        # Пробуем получить токен из заголовков ответа
                        wbaas_token_header = response.headers.get("X-Wbaas-Token")
                        if wbaas_token_header and wbaas_token_header != "get":
                            # Обновляем токен в cookies
                            self._cookies_dict["x_wbaas_token"] = wbaas_token_header
                            self._cookies_header = "; ".join([f"{k}={v}" for k, v in self._cookies_dict.items()])
                            logger.info("Токен обновлен из заголовка ответа")
                            
                            # Retry запрос с новым токеном
                            if retry_count < max_retries:
                                logger.info(f"Повторная попытка запроса (попытка {retry_count + 1}/{max_retries})...")
                                await asyncio.sleep(2.0)  # Задержка перед retry
                                return await self._fetch_page(brand_id, dest, spp, page, fsupplier, retry_count + 1)
                    
                    # Проверяем, какие cookies были отправлены
                    sent_cookies = api_headers.get("Cookie", "НЕТ")
                    cookies_count = len(cookies_dict)
                    
                    logger.error(
                        f"Ошибка 498 при запросе страницы {page} для бренда {brand_id}\n"
                        f"URL: {url}\n"
                        f"Отправлено cookies в заголовке: {'ДА' if sent_cookies != 'НЕТ' else 'НЕТ'} ({len(sent_cookies) if sent_cookies != 'НЕТ' else 0} символов)\n"
                        f"Cookies в кэше: {cookies_count} штук\n"
                        f"Response headers: {dict(response.headers)}\n"
                        f"Response body (первые 500 символов): {response_text[:500]}"
                    )
                    
                    # Если это первая попытка, пробуем обновить cookies из браузера
                    if retry_count == 0 and self.auto_get_cookies:
                        logger.warning("Попытка обновить cookies из браузера...")
                        cookies_updated = await self._refresh_cookies_from_browser()
                        
                        if cookies_updated:
                            await asyncio.sleep(2.0)
                            return await self._fetch_page(brand_id, dest, spp, page, fsupplier, retry_count + 1)
                        else:
                            # Если не получилось обновить, пробуем переинициализировать сессию
                            logger.warning("Попытка переинициализации сессии...")
                            await self._initialize_session()
                            await asyncio.sleep(2.0)
                            return await self._fetch_page(brand_id, dest, spp, page, fsupplier, retry_count + 1)
                    elif retry_count == 0 and self.custom_cookies:
                        # Если автоматическое получение отключено, пробуем переинициализировать
                        logger.warning("Попытка переинициализации сессии с обновленными cookies...")
                        await self._initialize_session()
                        await asyncio.sleep(2.0)
                        return await self._fetch_page(brand_id, dest, spp, page, fsupplier, retry_count + 1)
                    
                    return None
                else:
                    logger.warning(
                        f"Ошибка запроса страницы {page}: статус {response.status_code}\n"
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
        
        # Фильтруем товары: обрабатываем только товары из разрешенных кабинетов
        if supplier_id is None:
            # Если supplier_id отсутствует - это баг, пропускаем товар
            return []
        
        if supplier_id not in WBCatalogAPI.CABINET_MAPPING:
            # Пропускаем товары от перекупов (не из разрешенных кабинетов)
            return []
        
        cabinet_name = WBCatalogAPI.CABINET_MAPPING[supplier_id]
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