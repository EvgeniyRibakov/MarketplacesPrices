"""Модуль для работы с внутренним API каталога брендов Wildberries."""
import asyncio
import time
from typing import List, Dict, Optional
from urllib.parse import urlencode
from curl_cffi.requests import AsyncSession
from loguru import logger


class WBCatalogAPI:
    """Клиент для работы с внутренним API каталога продавцов WB."""
    
    BASE_URL = "https://www.wildberries.ru/__internal/u-catalog/sellers/v4/catalog"
    
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
                 auto_get_cookies: bool = True, discounts_api_token: Optional[str] = None):
        """Инициализация клиента.
        
        Args:
            request_delay: Задержка между запросами (секунды)
            max_concurrent: Максимальное количество параллельных запросов
            cookies: Опциональные cookies из браузера в формате "name1=value1; name2=value2"
            auto_get_cookies: Автоматически получать cookies из браузера если не переданы
            discounts_api_token: Токен для авторизации в discounts-prices-api.wildberries.ru
        """
        self.request_delay = request_delay
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.session: Optional[AsyncSession] = None
        self.custom_cookies = cookies
        self.auto_get_cookies = auto_get_cookies
        self._cookies_header: Optional[str] = None
        self._cookies_dict: Dict[str, str] = {}  # Кэш cookies для быстрого доступа
        self.discounts_api_token = discounts_api_token
    
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
    
    def _build_url(self, supplier_id: int, dest: int, spp: int = 30, 
                   page: int = 1) -> str:
        """Строит URL для запроса каталога продавца."""
        params = {
            "ab_testing": "false",
            "appType": "1",
            "curr": "rub",
            "dest": str(dest),
            "hide_dtype": "9",
            "hide_vflags": "4294967296",
            "lang": "ru",
            "page": str(page),
            "sort": "popular",
            "spp": str(spp),
            "supplier": str(supplier_id),
        }
        
        query_string = urlencode(params)
        return f"{self.BASE_URL}?{query_string}"
    
    async def _fetch_page(self, supplier_id: int, dest: int, spp: int, 
                         page: int, retry_count: int = 0) -> Optional[Dict]:
        """Получает одну страницу каталога продавца."""
        url = self._build_url(supplier_id, dest, spp, page)
        max_retries = 2
        start_time = time.time()
        
        async with self.semaphore:
            try:
                await asyncio.sleep(self.request_delay)
                
                logger.debug(f"📥 Запрос страницы {page} для продавца {supplier_id}...")
                
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
                elapsed_time = time.time() - start_time
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                        products_count = len(data.get("products", []))
                        # Обновляем cookies из ответа
                        if response.cookies:
                            for name, value in response.cookies.items():
                                self._cookies_dict[name] = value
                            self._cookies_header = "; ".join([f"{k}={v}" for k, v in self._cookies_dict.items()])
                        
                        logger.info(
                            f"✅ Страница {page}: успешно загружена за {elapsed_time:.2f} сек. "
                            f"Получено товаров: {products_count}"
                        )
                        return data
                    except Exception as e:
                        logger.error(
                            f"❌ Ошибка парсинга JSON ответа для страницы {page} "
                            f"(время: {elapsed_time:.2f} сек): {e}"
                        )
                        return None
                elif response.status_code == 429:
                    # Rate limiting - слишком много запросов
                    # Используем exponential backoff для retry
                    wait_time = min(2.0 * (2 ** retry_count), 30.0)  # Максимум 30 секунд
                    
                    if retry_count < max_retries:
                        logger.warning(
                            f"⚠️ Rate limit (429) при запросе страницы {page} "
                            f"(время: {elapsed_time:.2f} сек). "
                            f"Повтор через {wait_time:.1f} сек (попытка {retry_count + 1}/{max_retries})..."
                        )
                        await asyncio.sleep(wait_time)
                        return await self._fetch_page(supplier_id, dest, spp, page, retry_count + 1)
                    else:
                        logger.error(
                            f"❌ Rate limit (429) при запросе страницы {page} после {max_retries} попыток "
                            f"(время: {elapsed_time:.2f} сек). Пропускаем страницу."
                        )
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
                                return await self._fetch_page(supplier_id, dest, spp, page, retry_count + 1)
                    
                    # Проверяем, какие cookies были отправлены
                    sent_cookies = api_headers.get("Cookie", "НЕТ")
                    cookies_count = len(cookies_dict)
                    
                    logger.error(
                        f"Ошибка 498 при запросе страницы {page} для продавца {supplier_id}\n"
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
                            return await self._fetch_page(supplier_id, dest, spp, page, retry_count + 1)
                        else:
                            # Если не получилось обновить, пробуем переинициализировать сессию
                            logger.warning("Попытка переинициализации сессии...")
                            await self._initialize_session()
                            await asyncio.sleep(2.0)
                            return await self._fetch_page(supplier_id, dest, spp, page, retry_count + 1)
                    elif retry_count == 0 and self.custom_cookies:
                        # Если автоматическое получение отключено, пробуем переинициализировать
                        logger.warning("Попытка переинициализации сессии с обновленными cookies...")
                        await self._initialize_session()
                        await asyncio.sleep(2.0)
                        return await self._fetch_page(supplier_id, dest, spp, page, retry_count + 1)
                    
                    return None
                else:
                    logger.warning(
                        f"⚠️ Ошибка запроса страницы {page}: статус {response.status_code} "
                        f"(время: {elapsed_time:.2f} сек)\n"
                        f"URL: {url}"
                    )
                    return None
                        
            except asyncio.TimeoutError:
                elapsed_time = time.time() - start_time
                logger.error(
                    f"❌ Таймаут при запросе страницы {page} "
                    f"(время ожидания: {elapsed_time:.2f} сек)"
                )
                return None
            except Exception as e:
                elapsed_time = time.time() - start_time
                logger.error(
                    f"❌ Исключение при запросе страницы {page} "
                    f"(время: {elapsed_time:.2f} сек): {e}"
                )
                logger.exception("Детали исключения:")
                return None
    
    async def fetch_seller_catalog(self, supplier_id: int, dest: int, spp: int = 30) -> List[Dict]:
        """Получает весь каталог продавца (все страницы)."""
        catalog_start_time = time.time()
        cabinet_name = self.CABINET_MAPPING.get(supplier_id, f"UNKNOWN_{supplier_id}")
        logger.info(f"🚀 Начинаем загрузку каталога продавца {supplier_id} ({cabinet_name})...")
        
        all_products = []
        page = 1
        successful_pages = 0
        failed_pages = 0
        
        first_page_start = time.time()
        first_page = await self._fetch_page(supplier_id, dest, spp, page)
        first_page_time = time.time() - first_page_start
        
        if not first_page:
            logger.error(
                f"❌ Не удалось получить первую страницу для продавца {supplier_id} "
                f"(время: {first_page_time:.2f} сек)"
            )
            return []
        
        products = first_page.get("products", [])
        total = first_page.get("total", 0)
        all_products.extend(products)
        successful_pages += 1
        
        logger.info(
            f"✅ Страница 1: получено {len(products)} товаров из {total} всего "
            f"(время: {first_page_time:.2f} сек)"
        )
        
        products_per_page = len(products)
        if products_per_page > 0:
            total_pages = (total + products_per_page - 1) // products_per_page
        else:
            total_pages = 1
        
        logger.info(f"📄 Всего страниц для загрузки: {total_pages}")
        
        if total_pages > 1:
            # Загружаем страницы батчами, чтобы избежать rate limiting
            batch_size = 2  # Уменьшили до 2 для снижения 429 ошибок
            total_batches = ((total_pages - 1) + batch_size - 1) // batch_size
            
            logger.info(
                f"📦 Загрузка страниц батчами: размер батча {batch_size}, "
                f"всего батчей {total_batches}"
            )
            
            for batch_num, batch_start in enumerate(range(2, total_pages + 1, batch_size), 1):
                batch_start_time = time.time()
                batch_end = min(batch_start + batch_size, total_pages + 1)
                batch_pages = list(range(batch_start, batch_end))
                
                logger.info(
                    f"📦 Батч {batch_num}/{total_batches}: загрузка страниц {batch_start}-{batch_end-1}..."
                )
                
                tasks = []
                for page_num in batch_pages:
                    task = self._fetch_page(supplier_id, dest, spp, page_num)
                    tasks.append((page_num, task))
                
                # Выполняем батч параллельно
                batch_results = await asyncio.gather(
                    *[task for _, task in tasks],
                    return_exceptions=True
                )
                
                batch_time = time.time() - batch_start_time
                batch_successful = 0
                batch_failed = 0
                
                # Обрабатываем результаты батча
                for (page_num, _), result in zip(tasks, batch_results):
                    if isinstance(result, Exception):
                        logger.error(
                            f"❌ Ошибка при загрузке страницы {page_num}: {result}"
                        )
                        failed_pages += 1
                        batch_failed += 1
                        continue
                    
                    if result:
                        page_products = result.get("products", [])
                        all_products.extend(page_products)
                        successful_pages += 1
                        batch_successful += 1
                    else:
                        failed_pages += 1
                        batch_failed += 1
                
                logger.info(
                    f"✅ Батч {batch_num}/{total_batches} завершен за {batch_time:.2f} сек: "
                    f"успешно {batch_successful}, ошибок {batch_failed}"
                )
                
                # Увеличили задержку между батчами для снижения нагрузки
                if batch_end <= total_pages:
                    await asyncio.sleep(1.0)
        
        catalog_time = time.time() - catalog_start_time
        
        logger.success(
            f"✅ Каталог продавца {supplier_id} ({cabinet_name}) загружен: "
            f"всего товаров {len(all_products)}, "
            f"страниц успешно {successful_pages}, "
            f"страниц с ошибками {failed_pages}, "
            f"время загрузки {catalog_time:.2f} сек"
        )
        
        return all_products
    
    @staticmethod
    def parse_product(product: Dict, supplier_id: int) -> List[Dict]:
        """Парсит товар из JSON ответа API продавца."""
        results = []
        
        product_id = product.get("id")
        product_name = product.get("name", "")
        product_supplier_id = product.get("supplierId")
        supplier_name = product.get("supplier", "")
        
        # Проверяем, что supplier_id товара совпадает с запрашиваемым
        # (при парсинге страницы продавца все товары должны быть от этого продавца)
        if product_supplier_id is None:
            # Если supplier_id отсутствует - это баг, пропускаем товар
            logger.warning(f"⚠️ Товар {product_id} не имеет supplier_id, пропускаем")
            return []
        
        if product_supplier_id != supplier_id:
            # Товар от другого продавца - это не должно происходить при парсинге страницы продавца
            logger.warning(
                f"⚠️ Несоответствие supplier_id: ожидали {supplier_id}, получили {product_supplier_id} "
                f"для товара {product_id}, пропускаем"
            )
            return []
        
        # Получаем название кабинета
        cabinet_name = WBCatalogAPI.CABINET_MAPPING.get(supplier_id, f"UNKNOWN_{supplier_id}")
        cabinet_id = supplier_id
        
        # Извлекаем brand_id и brand_name из товара, если есть
        brand_id = product.get("brandId") or product.get("brand") or None
        brand_name = product.get("brandName") or product.get("brand") or ""
        
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
                "source_price_basic": "api-seller-catalog",
                "source_price_product": "api-seller-catalog",
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
                    "source_price_basic": "api-seller-catalog",
                    "source_price_product": "api-seller-catalog",
                    "source_price_card": None,
                })
        
        return results
    
    async def fetch_discounted_prices(self, nm_ids: List[int]) -> Dict[int, Dict]:
        """Получает discountedPrice для списка артикулов через официальный discounts API.
        
        Args:
            nm_ids: Список артикулов (nmID) товаров (до 1000 за запрос)
        
        Returns:
            Словарь {nm_id: {size_id: discountedPrice}} для каждого товара и размера
        """
        if not nm_ids:
            return {}
        
        DISCOUNTS_API_URL = "https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter"
        
        # Разбиваем на батчи по 1000 (лимит API)
        batch_size = 1000
        all_results = {}
        
        for i in range(0, len(nm_ids), batch_size):
            batch = nm_ids[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (len(nm_ids) + batch_size - 1) // batch_size
            
            logger.info(
                f"📊 Запрос discountedPrice: батч {batch_num}/{total_batches} "
                f"({len(batch)} артикулов)..."
            )
            
            start_time = time.time()
            
            try:
                async with self.semaphore:
                    # Формируем заголовки
                    headers = {
                        "Content-Type": "application/json",
                    }
                    
                    # Добавляем Authorization токен, если есть
                    if self.discounts_api_token:
                        headers["Authorization"] = f"Bearer {self.discounts_api_token}"
                    elif self._cookies_header:
                        # Fallback на cookies, если токен не указан
                        headers["Cookie"] = self._cookies_header
                    
                    # POST запрос с массивом nmList
                    response = await self.session.post(
                        DISCOUNTS_API_URL,
                        json={"nmList": batch},
                        headers=headers,
                        timeout=30
                    )
                    
                    elapsed_time = time.time() - start_time
                    
                    if response.status_code == 200:
                        data = response.json()
                        
                        if data.get("error"):
                            logger.warning(
                                f"⚠️ API вернул ошибку для батча {batch_num}: "
                                f"{data.get('errorText', 'Unknown error')}"
                            )
                            continue
                        
                        list_goods = data.get("data", {}).get("listGoods", [])
                        
                        for good in list_goods:
                            nm_id = good.get("nmID")
                            if not nm_id:
                                continue
                            
                            sizes = good.get("sizes", [])
                            
                            if not sizes:
                                # Товар без размеров - используем discountedPrice на уровне товара
                                discounted_price = good.get("discountedPrice")
                                if discounted_price is not None:
                                    all_results[nm_id] = {None: discounted_price}
                            else:
                                # Товар с размерами - для каждого размера свой discountedPrice
                                # Сохраняем как по sizeID, так и по techSizeName для гибкого сопоставления
                                size_prices = {}
                                size_prices_by_name = {}
                                for size in sizes:
                                    size_id = size.get("sizeID")
                                    tech_size_name = size.get("techSizeName")
                                    discounted_price = size.get("discountedPrice")
                                    if discounted_price is not None:
                                        if size_id:
                                            size_prices[size_id] = discounted_price
                                        if tech_size_name:
                                            size_prices_by_name[tech_size_name] = discounted_price
                                
                                if size_prices:
                                    # Сохраняем оба маппинга для гибкого сопоставления
                                    all_results[nm_id] = {
                                        "_by_id": size_prices,
                                        "_by_name": size_prices_by_name
                                    }
                        
                        logger.success(
                            f"✅ Батч {batch_num}: получено данных для {len(list_goods)} товаров "
                            f"за {elapsed_time:.2f} сек"
                        )
                    
                    elif response.status_code == 429:
                        elapsed_time = time.time() - start_time
                        logger.warning(
                            f"⚠️ Rate limit (429) для батча {batch_num} "
                            f"(время: {elapsed_time:.2f} сек). Ожидание 0.6 сек..."
                        )
                        await asyncio.sleep(0.6)  # Минимальная задержка на грани фола
                        # Повторяем запрос один раз
                        async with self.semaphore:
                            headers = {
                                "Content-Type": "application/json",
                            }
                            if self.discounts_api_token:
                                headers["Authorization"] = f"Bearer {self.discounts_api_token}"
                            elif self._cookies_header:
                                headers["Cookie"] = self._cookies_header
                            
                            response = await self.session.post(
                                DISCOUNTS_API_URL,
                                json={"nmList": batch},
                                headers=headers,
                                timeout=30
                            )
                            if response.status_code == 200:
                                data = response.json()
                                list_goods = data.get("data", {}).get("listGoods", [])
                                for good in list_goods:
                                    nm_id = good.get("nmID")
                                    if not nm_id:
                                        continue
                                    sizes = good.get("sizes", [])
                                    if not sizes:
                                        discounted_price = good.get("discountedPrice")
                                        if discounted_price is not None:
                                            all_results[nm_id] = {None: discounted_price}
                                    else:
                                        size_prices = {}
                                        size_prices_by_name = {}
                                        for size in sizes:
                                            size_id = size.get("sizeID")
                                            tech_size_name = size.get("techSizeName")
                                            discounted_price = size.get("discountedPrice")
                                            if discounted_price is not None:
                                                if size_id:
                                                    size_prices[size_id] = discounted_price
                                                if tech_size_name:
                                                    size_prices_by_name[tech_size_name] = discounted_price
                                        if size_prices:
                                            all_results[nm_id] = {
                                                "_by_id": size_prices,
                                                "_by_name": size_prices_by_name
                                            }
                    
                    else:
                        elapsed_time = time.time() - start_time
                        logger.error(
                            f"❌ Ошибка запроса discountedPrice для батча {batch_num}: "
                            f"статус {response.status_code} (время: {elapsed_time:.2f} сек)"
                        )
                        try:
                            error_text = response.text[:200]
                            logger.debug(f"Ответ сервера: {error_text}")
                        except:
                            pass
                    
                    # Минимальная задержка между запросами (на грани фола: 10 запросов за 6 сек = 0.6 сек)
                    if i + batch_size < len(nm_ids):
                        await asyncio.sleep(0.6)
            
            except asyncio.TimeoutError:
                elapsed_time = time.time() - start_time
                logger.error(
                    f"❌ Таймаут при запросе discountedPrice для батча {batch_num} "
                    f"(время ожидания: {elapsed_time:.2f} сек)"
                )
            except Exception as e:
                elapsed_time = time.time() - start_time
                logger.error(
                    f"❌ Исключение при запросе discountedPrice для батча {batch_num} "
                    f"(время: {elapsed_time:.2f} сек): {e}"
                )
                logger.exception("Детали исключения:")
        
        logger.info(
            f"📊 Получено discountedPrice для {len(all_results)} товаров "
            f"из {len(nm_ids)} запрошенных"
        )
        
        return all_results