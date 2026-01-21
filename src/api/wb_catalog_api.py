"""Модуль для работы с внутренним API каталога брендов Wildberries."""
import asyncio
import time
from typing import List, Dict, Optional
from urllib.parse import urlencode, quote
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
                 discounts_api_token: Optional[str] = None):
        """Инициализация клиента.
        
        Args:
            request_delay: Задержка между запросами (секунды)
            max_concurrent: Максимальное количество параллельных запросов
            cookies: Опциональные cookies в формате "name1=value1; name2=value2" (необязательно, 
                    curl_cffi автоматически управляет cookies через сессию)
            discounts_api_token: Токен для авторизации в discounts-prices-api.wildberries.ru
        """
        self.request_delay = request_delay
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.session: Optional[AsyncSession] = None
        self.custom_cookies = cookies
        self._cookies_header: Optional[str] = None
        self._cookies_dict: Dict[str, str] = {}  # Кэш cookies для быстрого доступа
        self.discounts_api_token = discounts_api_token
    
    async def __aenter__(self):
        """Асинхронный контекстный менеджер - вход."""
        # Создаем сессию curl_cffi с эмуляцией Chrome 131
        # impersonate эмулирует TLS fingerprint браузера
        # curl_cffi автоматически управляет cookies через сессию
        self.session = AsyncSession(
            impersonate="chrome131",  # Эмулирует Chrome 131 TLS fingerprint
            timeout=30,
        )
        
        # Если переданы cookies, добавляем их в сессию
        if self.custom_cookies:
            await self._load_custom_cookies()
        
        # Инициализируем сессию (получаем cookies через запросы к WB)
        await self._initialize_session()
        
        return self
    
    
    async def _load_custom_cookies(self):
        """Загружает cookies из строки формата 'name1=value1; name2=value2'.
        
        КРИТИЧНО: Добавляет cookies как в кэш (_cookies_dict), так и в session.cookies
        curl_cffi для автоматической отправки при запросах.
        """
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
            
            # КРИТИЧНО: Добавляем cookies в session.cookies curl_cffi
            # Без этого curl_cffi не будет отправлять cookies автоматически
            if self.session:
                cookies_added_to_session = 0
                for name, value in cookies_dict.items():
                    try:
                        # Добавляем cookie в сессию curl_cffi
                        # Используем домен wildberries.ru для всех cookies
                        self.session.cookies.set(
                            name=name,
                            value=value,
                            domain='.wildberries.ru',  # Поддомены тоже
                            path='/'
                        )
                        cookies_added_to_session += 1
                        logger.debug(f"  • Cookie добавлен в session.cookies: {name}")
                    except Exception as e:
                        logger.warning(f"  • Не удалось добавить cookie {name} в session.cookies: {e}")
                        # Пробуем альтернативный способ - через домен без точки
                        try:
                            self.session.cookies.set(
                                name=name,
                                value=value,
                                domain='wildberries.ru',
                                path='/'
                            )
                            cookies_added_to_session += 1
                            logger.debug(f"  • Cookie {name} добавлен альтернативным способом")
                        except Exception as e2:
                            logger.debug(f"  • Альтернативный способ тоже не сработал для {name}: {e2}")
                
                # Проверяем количество cookies в session.cookies
                session_cookies_count = 0
                if hasattr(self.session, 'cookies'):
                    try:
                        if hasattr(self.session.cookies, 'get_dict'):
                            session_cookies_count = len(self.session.cookies.get_dict())
                        else:
                            # Безопасный подсчет через try-except
                            try:
                                session_cookies_count = sum(1 for _ in self.session.cookies)
                            except:
                                session_cookies_count = 0
                    except:
                        session_cookies_count = 0
                logger.debug(f"✓ Cookies в session.cookies после добавления: {session_cookies_count} (добавлено: {cookies_added_to_session})")
            else:
                logger.warning("⚠️ Сессия еще не создана, cookies будут добавлены позже")
            
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
        """Инициализирует сессию через запрос к главной странице.
        
        curl_cffi автоматически управляет cookies через сессию.
        Если переданы custom_cookies, они добавляются в сессию.
        """
        try:
            logger.info("Инициализация сессии через запрос к главной странице WB...")
            
            # Делаем запрос на главную страницу
            # curl_cffi автоматически сохранит cookies в сессию
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
            
            # НЕ добавляем Cookie заголовок вручную - curl_cffi автоматически отправит cookies из session.cookies
            # Если cookies были загружены в _load_custom_cookies(), они уже в session.cookies
            # Если добавить Cookie заголовок вручную, это может конфликтовать с автоматической отправкой
            
            response = await self.session.get("https://www.wildberries.ru/", headers=headers)
            
            # КРИТИЧНО: Извлекаем cookies даже при ошибке 498 (антибот может вернуть cookies)
            # curl_cffi автоматически сохранил cookies в session.cookies
            # Синхронизируем с нашим кэшем для совместимости
            cookies_before = len(self._cookies_dict)
            
            if hasattr(self.session, 'cookies'):
                for cookie in self.session.cookies:
                    self._cookies_dict[cookie.name] = cookie.value
            
            # Также обновляем из response.cookies (даже при ошибке 498 могут быть cookies)
            if response.cookies:
                for name, value in response.cookies.items():
                    self._cookies_dict[name] = value
            
            # КРИТИЧНО: Парсим Set-Cookie заголовки напрямую (curl_cffi может не обработать при 498)
            if hasattr(response, 'headers'):
                set_cookie_headers = []
                # Пробуем разные способы получения Set-Cookie
                if hasattr(response.headers, 'get_list'):
                    try:
                        set_cookie_headers = response.headers.get_list("Set-Cookie")
                    except:
                        pass
                
                if not set_cookie_headers:
                    # Альтернативный способ
                    set_cookie_headers = [v for k, v in response.headers.items() if k.lower() == 'set-cookie']
                
                if set_cookie_headers:
                    from http.cookies import SimpleCookie
                    for set_cookie in set_cookie_headers:
                        try:
                            cookie = SimpleCookie()
                            cookie.load(set_cookie)
                            for name, morsel in cookie.items():
                                self._cookies_dict[name] = morsel.value
                        except Exception as e:
                            logger.debug(f"Ошибка парсинга Set-Cookie: {e}")
            
            # Обновляем заголовок cookies
            self._cookies_header = "; ".join([f"{k}={v}" for k, v in self._cookies_dict.items()])
            
            cookies_after = len(self._cookies_dict)
            cookies_added = cookies_after - cookies_before
            
            if response.status_code == 498:
                logger.warning(f"⚠️ Запрос к главной странице вернул 498, но получено cookies: {cookies_added}")
            else:
                logger.info(f"✅ Запрос к главной странице успешен (статус {response.status_code}), получено cookies: {cookies_added}")
            
            logger.info(f"Инициализация завершена. Всего cookies в сессии: {cookies_after}")
            
            # Небольшая задержка для имитации поведения браузера
            await asyncio.sleep(0.5)
                        
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
                logger.debug(f"  • URL: {url}")
                logger.debug(f"  • dest в URL: {dest}")
                
                # КРИТИЧНО: curl_cffi автоматически отправляет cookies из session.cookies
                # НЕ добавляем Cookie заголовок вручную - пусть curl_cffi делает это автоматически
                # Это важно для правильной работы с cookies при ошибках
                
                # Синхронизируем cookies из session.cookies с нашим кэшем
                if hasattr(self.session, 'cookies'):
                    try:
                        # curl_cffi может возвращать cookies как словарь или как итерируемый объект
                        if hasattr(self.session.cookies, 'get_dict'):
                            # Если есть метод get_dict, используем его
                            cookies_from_session = self.session.cookies.get_dict()
                            self._cookies_dict.update(cookies_from_session)
                        else:
                            # Иначе итерируемся по cookies
                            for cookie in self.session.cookies:
                                # Проверяем тип: может быть объект cookie или строка
                                if isinstance(cookie, str):
                                    # Если это строка, пропускаем (неправильный формат)
                                    continue
                                elif hasattr(cookie, 'name') and hasattr(cookie, 'value'):
                                    self._cookies_dict[cookie.name] = cookie.value
                                elif isinstance(cookie, tuple) and len(cookie) == 2:
                                    # Может быть кортеж (name, value)
                                    self._cookies_dict[cookie[0]] = cookie[1]
                    except Exception as e:
                        logger.debug(f"Ошибка при синхронизации cookies из session.cookies: {e}")
                
                # Обновляем заголовок для логирования
                self._cookies_header = "; ".join([f"{k}={v}" for k, v in self._cookies_dict.items()])
                
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
                
                # НЕ добавляем Cookie заголовок - curl_cffi сделает это автоматически из session.cookies
                # Проверяем реальное количество cookies в session.cookies (curl_cffi будет их отправлять)
                session_cookies_count = 0
                if hasattr(self.session, 'cookies'):
                    session_cookies_count = len(list(self.session.cookies))
                
                cookies_count = len(self._cookies_dict)
                if session_cookies_count > 0:
                    logger.debug(f"Cookies в сессии curl_cffi: {session_cookies_count} (отправятся автоматически)")
                    logger.debug(f"Cookies в кэше: {cookies_count}")
                else:
                    logger.warning(f"⚠️ Cookies в session.cookies отсутствуют! (в кэше: {cookies_count})")
                
                # Логируем ключевые cookies для диагностики
                important_cookies = ["wbx-validation-key", "x_wbaas_token", "_wbauid", "_cp", "routeb"]
                found_important = [c for c in important_cookies if c in self._cookies_dict]
                if found_important:
                    logger.debug(f"Найдены важные cookies в сессии: {', '.join(found_important)}")
                else:
                    logger.debug(f"⚠️ Важные cookies отсутствуют: {', '.join(important_cookies)}")
                
                response = await self.session.get(url, headers=api_headers)
                elapsed_time = time.time() - start_time
                
                # КРИТИЧНО: Синхронизируем cookies из session.cookies (curl_cffi автоматически управляет)
                cookies_before_sync = len(self._cookies_dict)
                if hasattr(self.session, 'cookies'):
                    try:
                        # curl_cffi может возвращать cookies как словарь или как итерируемый объект
                        if hasattr(self.session.cookies, 'get_dict'):
                            # Если есть метод get_dict, используем его
                            cookies_from_session = self.session.cookies.get_dict()
                            self._cookies_dict.update(cookies_from_session)
                        else:
                            # Иначе итерируемся по cookies
                            for cookie in self.session.cookies:
                                # Проверяем тип: может быть объект cookie или строка
                                if isinstance(cookie, str):
                                    # Если это строка, пропускаем (неправильный формат)
                                    continue
                                elif hasattr(cookie, 'name') and hasattr(cookie, 'value'):
                                    self._cookies_dict[cookie.name] = cookie.value
                                elif isinstance(cookie, tuple) and len(cookie) == 2:
                                    # Может быть кортеж (name, value)
                                    self._cookies_dict[cookie[0]] = cookie[1]
                    except Exception as e:
                        logger.debug(f"Ошибка при синхронизации cookies из session.cookies после запроса: {e}")
                
                # КРИТИЧНО: Обновляем cookies из ответа ДО проверки статуса
                # (даже при ошибке 498 могут быть cookies в ответе)
                if response.cookies:
                    for name, value in response.cookies.items():
                        self._cookies_dict[name] = value
                
                # Также парсим Set-Cookie заголовки напрямую (curl_cffi может не обработать при 498)
                if hasattr(response, 'headers'):
                    set_cookie_headers = []
                    if hasattr(response.headers, 'get_list'):
                        try:
                            set_cookie_headers = response.headers.get_list("Set-Cookie")
                        except:
                            pass
                    
                    if not set_cookie_headers:
                        set_cookie_headers = [v for k, v in response.headers.items() if k.lower() == 'set-cookie']
                    
                    if set_cookie_headers:
                        from http.cookies import SimpleCookie
                        for set_cookie in set_cookie_headers:
                            try:
                                cookie = SimpleCookie()
                                cookie.load(set_cookie)
                                for name, morsel in cookie.items():
                                    self._cookies_dict[name] = morsel.value
                                    logger.debug(f"  • Извлечен cookie из Set-Cookie: {name}")
                            except Exception as e:
                                logger.debug(f"  • Ошибка парсинга Set-Cookie: {e}")
                
                # Обновляем заголовок cookies
                self._cookies_header = "; ".join([f"{k}={v}" for k, v in self._cookies_dict.items()])
                
                cookies_after_sync = len(self._cookies_dict)
                cookies_added = cookies_after_sync - cookies_before_sync
                if cookies_added > 0:
                    logger.debug(f"  • Обновлено cookies после запроса: +{cookies_added} (всего: {cookies_after_sync})")
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                        products_count = len(data.get("products", []))
                        
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
                    response_text = ""
                    try:
                        response_text = response.text[:500] if hasattr(response, 'text') else str(response.content)[:500]
                    except:
                        pass
                    
                    # Проверяем cookies в сессии curl_cffi
                    session_cookies_count = 0
                    if hasattr(self.session, 'cookies'):
                        try:
                            if hasattr(self.session.cookies, 'get_dict'):
                                session_cookies_count = len(self.session.cookies.get_dict())
                            else:
                                # Безопасный подсчет через try-except
                                try:
                                    session_cookies_count = sum(1 for _ in self.session.cookies)
                                except:
                                    session_cookies_count = 0
                        except:
                            session_cookies_count = 0
                    
                    cookies_count = len(self._cookies_dict)
                    
                    # Проверяем наличие важных cookies
                    important_cookies = ["wbx-validation-key", "x_wbaas_token", "_wbauid", "_cp", "routeb"]
                    found_important = [c for c in important_cookies if c in self._cookies_dict]
                    
                    logger.error(
                        f"Ошибка 498 при запросе страницы {page} для продавца {supplier_id}\n"
                        f"URL: {url}\n"
                        f"Cookies в сессии curl_cffi: {session_cookies_count} штук\n"
                        f"Cookies в кэше: {cookies_count} штук\n"
                        f"Важные cookies найдены: {', '.join(found_important) if found_important else 'НЕТ'}\n"
                        f"Response headers: {dict(response.headers)}\n"
                        f"Response body (первые 500 символов): {response_text[:500]}"
                    )
                    
                    # Если это первая попытка, пробуем переинициализировать сессию
                    if retry_count == 0:
                        logger.warning("Попытка переинициализации сессии...")
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
        
        # Загружаем остальные страницы параллельно
        tasks = []
        for page_num in range(2, total_pages + 1):
            tasks.append(self._fetch_page(supplier_id, dest, spp, page_num))
        
        if tasks:
            logger.info(f"📥 Загружаем {len(tasks)} страниц параллельно...")
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for page_num, result in enumerate(results, start=2):
                if isinstance(result, Exception):
                    logger.error(f"❌ Исключение при загрузке страницы {page_num}: {result}")
                    failed_pages += 1
                elif result:
                    products = result.get("products", [])
                    all_products.extend(products)
                    successful_pages += 1
                    logger.info(f"✅ Страница {page_num}: получено {len(products)} товаров")
                else:
                    failed_pages += 1
                    logger.warning(f"⚠️ Страница {page_num}: пустой ответ")
        
        catalog_time = time.time() - catalog_start_time
        logger.success(
            f"✅ Каталог продавца {supplier_id} ({cabinet_name}) загружен за {catalog_time:.2f} сек. "
            f"Всего товаров: {len(all_products)}, страниц: {successful_pages}/{total_pages}, "
            f"ошибок: {failed_pages}"
        )
        
        return all_products
    
    async def fetch_discounted_prices(self, nm_ids: List[int]) -> Dict[int, float]:
        """Получает discountedPrice для списка артикулов через discounts-prices-api."""
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
                        
                        # Отслеживаем, какие товары получили данные
                        found_nm_ids = set()
                        
                        for good in list_goods:
                            nm_id = good.get("nmID")
                            if not nm_id:
                                continue
                            
                            found_nm_ids.add(nm_id)
                            sizes = good.get("sizes", [])
                            
                            if not sizes:
                                # Товар без размеров - используем discountedPrice на уровне товара
                                discounted_price = good.get("discountedPrice")
                                if discounted_price is not None:
                                    all_results[nm_id] = {None: discounted_price}
                                else:
                                    # Товар есть в ответе, но нет discountedPrice
                                    logger.debug(
                                        f"⚠️ Товар {nm_id} есть в ответе API, но нет discountedPrice"
                                    )
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
                                else:
                                    # Товар есть в ответе, но нет discountedPrice для размеров
                                    logger.debug(
                                        f"⚠️ Товар {nm_id} есть в ответе API, но нет discountedPrice для размеров"
                                    )
                        
                        # Логируем товары, которые не были найдены в ответе
                        missing_nm_ids = set(batch) - found_nm_ids
                        if missing_nm_ids:
                            logger.warning(
                                f"⚠️ Батч {batch_num}: {len(missing_nm_ids)} товаров не найдено в ответе API "
                                f"(примеры: {list(missing_nm_ids)[:5]})"
                            )
                        
                        logger.success(
                            f"✅ Батч {batch_num}: получено данных для {len(list_goods)} товаров "
                            f"из {len(batch)} запрошенных за {elapsed_time:.2f} сек"
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
                                found_nm_ids_retry = set()
                                
                                for good in list_goods:
                                    nm_id = good.get("nmID")
                                    if not nm_id:
                                        continue
                                    
                                    found_nm_ids_retry.add(nm_id)
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
                                
                                missing_nm_ids_retry = set(batch) - found_nm_ids_retry
                                if missing_nm_ids_retry:
                                    logger.warning(
                                        f"⚠️ Батч {batch_num} (retry): {len(missing_nm_ids_retry)} товаров не найдено в ответе API"
                                    )
                    
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