"""Модуль для работы с публичным API каталога продавца Ozon (entrypoint)."""
import asyncio
import time
from typing import List, Dict, Optional
from urllib.parse import urlencode, quote
from curl_cffi.requests import AsyncSession
from curl_cffi.requests.exceptions import DNSError, RequestException
from loguru import logger
from src.exceptions import OzonAntibotException


class OzonCatalogAPI:
    """Клиент для работы с публичным API каталога продавца Ozon."""
    
    BASE_URL = "https://www.ozon.ru/api/entrypoint-api.bx/page/json/v2"
    
    # Маппинг seller_id -> название кабинета
    CABINET_MAPPING = {
        176640: "COSMO_BEAUTY",
    }
    
    def __init__(self, request_delay: float = 3.0, max_concurrent: int = 2, 
                 auto_get_cookies: bool = True, cookies: Optional[str] = None,
                 proxy: Optional[str] = None):
        """Инициализация клиента.
        
        Args:
            request_delay: Задержка между запросами (секунды) - рекомендуется 3-5 сек для обхода антибота
            max_concurrent: Максимальное количество параллельных запросов
            auto_get_cookies: Автоматически получать cookies из браузера если не переданы
            cookies: Опциональные cookies из браузера в формате "name1=value1; name2=value2"
            proxy: Опциональный прокси-сервер в формате "http://host:port" или "socks5://host:port"
        """
        self.request_delay = request_delay
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.session: Optional[AsyncSession] = None
        self.auto_get_cookies = auto_get_cookies
        self.custom_cookies = cookies
        self.proxy = proxy
        self._cookies_header: Optional[str] = None
        self._cookies_dict: Dict[str, str] = {}
        self._antibot_triggered_count: int = 0  # Счетчик срабатываний антибота
    
    async def __aenter__(self):
        """Асинхронный контекстный менеджер - вход."""
        # Создаем сессию curl_cffi с эмуляцией Chrome 131
        # Используем более полную эмуляцию браузера
        self.session = AsyncSession(
            impersonate="chrome131",
            timeout=30,
            # Дополнительные параметры для лучшей эмуляции браузера
            verify=True,  # Проверка SSL сертификатов
            allow_redirects=True,  # Следовать редиректам как браузер
        )
        
        # Загружаем cookies если нужно
        if self.custom_cookies:
            await self._load_custom_cookies()
        elif self.auto_get_cookies:
            # Пробуем автоматически получить cookies из браузера (как в WB парсере)
            await self._load_cookies_from_browser()
        
        # Инициализируем сессию с главной страницы (получаем cookies через curl_cffi)
        init_success = await self._initialize_session()
        if not init_success:
            logger.warning("⚠️ Инициализация сессии не удалась, продолжаем без cookies")
        
        return self
    
    async def _load_cookies_from_browser(self):
        """Автоматически загружает cookies из браузера Chrome (как в WB парсере)."""
        try:
            # Импортируем в функции, чтобы не было проблем если библиотека не установлена
            import sys
            from pathlib import Path
            # Добавляем путь к корню проекта для импорта
            project_root = Path(__file__).parent.parent.parent
            if str(project_root) not in sys.path:
                sys.path.insert(0, str(project_root))
            
            from src.utils.browser_cookies import get_ozon_cookies
            
            logger.info("Попытка автоматического получения cookies Ozon из браузера Chrome...")
            
            # Получаем cookies (синхронная функция, но вызываем в executor)
            loop = asyncio.get_event_loop()
            cookies_string = await loop.run_in_executor(None, get_ozon_cookies, True)
            
            if cookies_string:
                self.custom_cookies = cookies_string
                await self._load_custom_cookies()
                logger.success("✓ Cookies Ozon успешно получены из браузера")
            else:
                logger.warning("Не удалось получить cookies Ozon из браузера автоматически")
                logger.info("Продолжаем с получением cookies через curl_cffi...")
                
        except ImportError as e:
            logger.warning(f"Библиотеки для работы с браузером не установлены: {e}")
            logger.info("Установите: python -m pip install undetected-chromedriver selenium")
            logger.info("Продолжаем с получением cookies через curl_cffi...")
        except Exception as e:
            logger.warning(f"Ошибка при автоматическом получении cookies Ozon: {e}")
            logger.debug("Детали ошибки:", exc_info=True)
            logger.info("Продолжаем с получением cookies через curl_cffi...")
    
    async def _load_custom_cookies(self):
        """Загружает cookies из строки формата 'name1=value1; name2=value2'."""
        try:
            from http.cookies import SimpleCookie
            
            cookie = SimpleCookie()
            cookie.load(self.custom_cookies)
            
            cookies_dict = {}
            for name, morsel in cookie.items():
                cookies_dict[name] = morsel.value
            
            self._cookies_dict.update(cookies_dict)
            self._cookies_header = "; ".join([f"{name}={value}" for name, value in cookies_dict.items()])
            
            # Конвертируем keys() в список для слайсинга
            cookie_names = list(cookies_dict.keys())
            preview_names = ', '.join(cookie_names[:5])
            logger.info(f"Загружено {len(cookies_dict)} cookies из конфигурации: {preview_names}...")
                
        except Exception as e:
            logger.warning(f"Ошибка при загрузке cookies: {e}")
            self._cookies_header = None
    
    async def _initialize_session(self):
        """Инициализирует сессию, получая cookies с главной страницы через curl_cffi."""
        try:
            logger.info("Инициализация сессии: получение cookies с главной страницы Ozon через curl_cffi...")
            
            # Полный набор заголовков для максимальной эмуляции браузера Chrome
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept-Encoding": "gzip, deflate, br, zstd",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
                "DNT": "1",  # Do Not Track - браузеры обычно отправляют
                "Cache-Control": "max-age=0",  # Браузер обычно отправляет это при первой загрузке
            }
            
            # Добавляем cookies если есть (из браузера)
            if self._cookies_header:
                headers["Cookie"] = self._cookies_header
            
            # ДЕТАЛЬНОЕ ЛОГИРОВАНИЕ: Инициализация сессии
            logger.debug(f"🔍 ДИАГНОСТИКА: Инициализация сессии:")
            logger.debug(f"  • URL: https://www.ozon.ru/")
            logger.debug(f"  • Cookies перед запросом: {list(self._cookies_dict.keys())}")
            logger.debug(f"  • Cookies header: {self._cookies_header[:200] if self._cookies_header else 'НЕТ'}...")
            
            # Делаем запрос на главную страницу Ozon с обработкой DNS ошибок
            max_retries = 3
            response = None
            
            for attempt in range(max_retries):
                try:
                    # Делаем запрос с полной эмуляцией браузера
                    response = await self.session.get(
                        "https://www.ozon.ru/", 
                        headers=headers,
                        allow_redirects=True,  # Следовать редиректам как браузер
                    )
                    
                    # Принимаем ответ даже при 403 (можем получить cookies)
                    if response.status_code in [200, 403]:
                        if response.status_code == 403:
                            logger.warning(f"⚠️ Получен 403 при инициализации (попытка {attempt + 1}/{max_retries}), но продолжаем для получения cookies")
                        break  # Успешно получили ответ
                        
                except DNSError as e:
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 2
                        logger.warning(f"⚠️ DNS ошибка при инициализации (попытка {attempt + 1}/{max_retries}). Повтор через {wait_time} сек...")
                        logger.debug(f"  • DNS ошибка: {e}")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        logger.error(f"❌ DNS ошибка при инициализации после {max_retries} попыток: {e}")
                        logger.error("  • Проверьте интернет-соединение и DNS настройки")
                        logger.error("  • Возможно, проблема с curl_cffi на Windows")
                        return False
                except RequestException as e:
                    logger.warning(f"⚠️ Ошибка запроса при инициализации: {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2)
                        continue
                    else:
                        return False
            
            if not response:
                logger.error("❌ Не удалось получить ответ при инициализации")
                return False
            
            # ДЕТАЛЬНОЕ ЛОГИРОВАНИЕ: Ответ при инициализации
            logger.debug(f"🔍 ДИАГНОСТИКА: Ответ при инициализации:")
            logger.debug(f"  • Status code: {response.status_code}")
            logger.debug(f"  • Content-Type: {response.headers.get('Content-Type', 'НЕТ')}")
            
            # Извлекаем ВСЕ cookies из jar сессии curl_cffi
            # curl_cffi хранит cookies в session.cookies (CookieJar)
            all_cookies = {}
            
            # Получаем все cookies из jar для домена ozon.ru
            if hasattr(self.session, 'cookies') and self.session.cookies:
                try:
                    # Используем get_dict() для получения всех cookies как словаря
                    # curl_cffi поддерживает get_dict() для CookieJar
                    cookies_dict = self.session.cookies.get_dict(domain='ozon.ru')
                    all_cookies.update(cookies_dict)
                    
                    # Также получаем cookies для .ozon.ru (с точкой)
                    cookies_dict_dot = self.session.cookies.get_dict(domain='.ozon.ru')
                    all_cookies.update(cookies_dict_dot)
                    
                    # Логируем полученные cookies
                    for cookie_name in all_cookies:
                        logger.debug(f"Получен cookie из jar: {cookie_name}")
                        
                except AttributeError:
                    # Если get_dict() не поддерживается, используем итерацию
                    for cookie in self.session.cookies:
                        try:
                            domain = getattr(cookie, 'domain', '') or cookie.domain
                            if 'ozon.ru' in domain or domain == '' or domain is None:
                                cookie_name = getattr(cookie, 'name', None) or cookie.name
                                cookie_value = getattr(cookie, 'value', None) or cookie.value
                                if cookie_name and cookie_value:
                                    all_cookies[cookie_name] = cookie_value
                                    logger.debug(f"Получен cookie из jar: {cookie_name} (домен: {domain})")
                        except Exception as e:
                            logger.debug(f"Ошибка при извлечении cookie: {e}")
                            continue
            
            # Также добавляем cookies из response.cookies (новые cookies из Set-Cookie)
            if response.cookies:
                for name, value in response.cookies.items():
                    all_cookies[name] = value
                    logger.debug(f"Получен cookie из Set-Cookie: {name}")
            
            # Обновляем словарь cookies (объединяем с существующими)
            self._cookies_dict.update(all_cookies)
            
            # Формируем заголовок cookies из ВСЕХ собранных cookies
            if self._cookies_dict:
                self._cookies_header = "; ".join([f"{k}={v}" for k, v in self._cookies_dict.items()])
            
            cookies_count = len(self._cookies_dict)
            cookie_names = list(self._cookies_dict.keys())
            logger.info(f"✅ Получено {cookies_count} cookies с главной страницы Ozon: {', '.join(cookie_names[:10])}{'...' if len(cookie_names) > 10 else ''}")
            
            # Делаем несколько запросов для получения максимального количества cookies
            # Стратегия: главная → категория → страница продавца
            urls_to_visit = [
                ("https://www.ozon.ru/", "главная страница"),
                ("https://www.ozon.ru/category/", "категории"),
                ("https://www.ozon.ru/seller/cosmo-beauty-176640/", "страница продавца"),
            ]
            
            for url_to_visit, description in urls_to_visit:
                try:
                    logger.debug(f"Делаем запрос на {description} ({url_to_visit}) для получения дополнительных cookies...")
                    
                    # Создаем заголовки для каждой страницы с правильными Referer
                    page_headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
                        "Accept-Encoding": "gzip, deflate, br, zstd",
                        "Connection": "keep-alive",
                        "Upgrade-Insecure-Requests": "1",
                        "Sec-Fetch-Dest": "document",
                        "Sec-Fetch-Mode": "navigate",
                        "Sec-Fetch-Site": "same-origin" if url_to_visit != "https://www.ozon.ru/" else "none",
                        "Sec-Fetch-User": "?1",
                        "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
                        "sec-ch-ua-mobile": "?0",
                        "sec-ch-ua-platform": '"Windows"',
                        "DNT": "1",
                        "Cache-Control": "max-age=0",
                    }
                    
                    # Добавляем Referer для всех страниц кроме главной
                    if url_to_visit != "https://www.ozon.ru/":
                        page_headers["Referer"] = "https://www.ozon.ru/"
                    
                    # Добавляем текущие cookies
                    if self._cookies_header:
                        page_headers["Cookie"] = self._cookies_header
                
                    # Делаем запрос с обработкой DNS ошибок
                    page_response = None
                    try:
                        page_response = await self.session.get(url_to_visit, headers=page_headers)
                    except DNSError as e:
                        logger.debug(f"  • DNS ошибка при запросе {description}: {e}, пропускаем")
                        page_response = None
                    except RequestException as e:
                        logger.debug(f"  • Ошибка запроса {description}: {e}, пропускаем")
                        page_response = None
                    
                    if not page_response:
                        logger.debug(f"  • Не удалось получить ответ с {description}, пропускаем")
                        continue
                    
                    # Извлекаем cookies из ответа
                    if page_response.cookies:
                        for name, value in page_response.cookies.items():
                            if name not in self._cookies_dict:
                                self._cookies_dict[name] = value
                                logger.debug(f"  • Получен новый cookie с {description}: {name}")
                    
                    # Небольшая задержка между запросами
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    logger.debug(f"  • Ошибка при запросе {description}: {e}, продолжаем")
                    continue
            
            # После всех запросов извлекаем ВСЕ cookies из jar
            try:
                if hasattr(self.session, 'cookies') and self.session.cookies:
                    # Извлекаем все cookies из jar для всех посещенных страниц
                    all_jar_cookies = {}
                    try:
                        all_jar_cookies = self.session.cookies.get_dict(domain='ozon.ru')
                        all_jar_cookies_dot = self.session.cookies.get_dict(domain='.ozon.ru')
                        all_jar_cookies.update(all_jar_cookies_dot)
                    except AttributeError:
                        # Fallback на итерацию
                        for cookie in self.session.cookies:
                            try:
                                domain = getattr(cookie, 'domain', '') or cookie.domain
                                if 'ozon.ru' in domain or domain == '' or domain is None:
                                    cookie_name = getattr(cookie, 'name', None) or cookie.name
                                    cookie_value = getattr(cookie, 'value', None) or cookie.value
                                    if cookie_name and cookie_value:
                                        all_jar_cookies[cookie_name] = cookie_value
                            except Exception:
                                continue
                    
                    # Объединяем с существующими cookies
                    new_cookies_count = 0
                    for cookie_name, cookie_value in all_jar_cookies.items():
                        if cookie_name not in self._cookies_dict:
                            self._cookies_dict[cookie_name] = cookie_value
                            new_cookies_count += 1
                            logger.debug(f"  • Получен новый cookie из jar: {cookie_name}")
                    
                    if new_cookies_count > 0:
                        logger.info(f"✅ Получено еще {new_cookies_count} cookies из jar после всех запросов")
                
                # Обновляем заголовок cookies
                if self._cookies_dict:
                    self._cookies_header = "; ".join([f"{k}={v}" for k, v in self._cookies_dict.items()])
                
                total_cookies = len(self._cookies_dict)
                logger.info(f"📊 Всего cookies для Ozon: {total_cookies}")
                
            except Exception as e:
                logger.debug(f"Ошибка при извлечении cookies из jar: {e}")
            
            # Небольшая задержка для имитации поведения браузера
            await asyncio.sleep(1.0)
            
            return True  # Успешная инициализация
                        
        except Exception as e:
            logger.warning(f"Не удалось инициализировать сессию: {e}, продолжаем...")
            logger.debug("Детали ошибки:", exc_info=True)
            return False  # Неудачная инициализация
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Асинхронный контекстный менеджер - выход."""
        if self.session:
            await self.session.close()
    
    def _log_cookies_diagnostic(self):
        """Диагностическое логирование cookies (Perplexity Fix #4)."""
        logger.debug("🔍 Детальная диагностика cookies:")
        logger.debug(f"  • Источник cookies: {'Браузер (auto)' if self.auto_get_cookies else 'Ручные'}")
        logger.debug(f"  • Количество cookies: {len(self._cookies_dict)}")
        logger.debug(f"  • Имена cookies: {list(self._cookies_dict.keys())}")
        logger.debug(f"  • Длина cookies header: {len(self._cookies_header) if self._cookies_header else 0}")
        
        # Показываем первые 50 символов каждого cookie для проверки валидности
        for name, value in list(self._cookies_dict.items())[:5]:  # Первые 5 cookies
            logger.debug(f"  • {name}: {value[:50]}{'...' if len(value) > 50 else ''}")
    
    def _build_url(self, seller_id: int, seller_name: str, page: int = 1, 
                   paginator_token: Optional[str] = None,
                   search_page_state: Optional[str] = None) -> str:
        """Строит URL для запроса каталога продавца.
        
        Args:
            seller_id: ID продавца
            seller_name: Название продавца (из URL)
            page: Номер страницы
            paginator_token: Токен пагинации (для следующих страниц)
            search_page_state: Токен состояния поиска
        
        Returns:
            URL для запроса
        """
        # Базовый URL страницы продавца
        seller_url = f"/seller/{seller_name}-{seller_id}/"
        
        # Параметры для URL
        params = {
            'page': str(page)
        }
        
        if page > 1:
            params['layout_page_index'] = str(page)
        
        if paginator_token:
            params['paginator_token'] = str(paginator_token)
        
        if search_page_state:
            params['search_page_state'] = search_page_state
        
        # Формируем query string
        query_string = '&'.join([f"{k}={quote(str(v))}" for k, v in params.items()])
        
        # Полный URL для entrypoint API
        full_seller_url = f"{seller_url}?{query_string}"
        
        # URL для API
        api_url = f"{self.BASE_URL}?url={quote(full_seller_url)}"
        
        # ДЕТАЛЬНОЕ ЛОГИРОВАНИЕ: Построение URL
        logger.debug(f"🔍 ДИАГНОСТИКА: Построение URL:")
        logger.debug(f"  • seller_id: {seller_id}")
        logger.debug(f"  • seller_name: {seller_name}")
        logger.debug(f"  • page: {page}")
        logger.debug(f"  • paginator_token: {paginator_token}")
        logger.debug(f"  • search_page_state: {search_page_state}")
        logger.debug(f"  • seller_url: {seller_url}")
        logger.debug(f"  • query_string: {query_string}")
        logger.debug(f"  • full_seller_url: {full_seller_url}")
        logger.debug(f"  • api_url: {api_url}")
        
        return api_url
    
    async def _fetch_page(self, seller_id: int, seller_name: str, page: int, 
                         paginator_token: Optional[str] = None,
                         search_page_state: Optional[str] = None,
                         retry_count: int = 0) -> Optional[Dict]:
        """Получает одну страницу каталога продавца."""
        url = self._build_url(seller_id, seller_name, page, paginator_token, search_page_state)
        max_retries = 2
        start_time = time.time()
        
        async with self.semaphore:
            try:
                await asyncio.sleep(self.request_delay)
                
                logger.debug(f"📥 Запрос страницы {page} для продавца {seller_id}...")
                
                # ДЕТАЛЬНОЕ ЛОГИРОВАНИЕ: Cookies перед запросом
                logger.debug(f"🔍 ДИАГНОСТИКА: Cookies перед запросом:")
                logger.debug(f"  • Всего cookies в словаре: {len(self._cookies_dict)}")
                logger.debug(f"  • Cookies: {list(self._cookies_dict.keys())}")
                logger.debug(f"  • Cookies header: {self._cookies_header[:200] if self._cookies_header else 'НЕТ'}...")
                
                # Полный набор заголовков для API запроса с максимальной эмуляцией браузера
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                    "Accept": "application/json, text/plain, */*",
                    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
                    "Accept-Encoding": "gzip, deflate, br, zstd",
                    "Referer": f"https://www.ozon.ru/seller/{seller_name}-{seller_id}/",  # Более точный Referer - страница продавца
                    "Origin": "https://www.ozon.ru",
                    "Connection": "keep-alive",
                    "Sec-Fetch-Dest": "empty",
                    "Sec-Fetch-Mode": "cors",
                    "Sec-Fetch-Site": "same-origin",
                    "Cache-Control": "no-cache",
                    "Pragma": "no-cache",
                    "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
                    "sec-ch-ua-mobile": "?0",
                    "sec-ch-ua-platform": '"Windows"',
                    "DNT": "1",
                }
                
                # Добавляем cookies если есть
                if self._cookies_header:
                    headers["Cookie"] = self._cookies_header
                
                # ДЕТАЛЬНОЕ ЛОГИРОВАНИЕ: URL и заголовки запроса
                logger.debug(f"🔍 ДИАГНОСТИКА: Детали запроса:")
                logger.debug(f"  • URL: {url}")
                logger.debug(f"  • Method: GET")
                logger.debug(f"  • Headers count: {len(headers)}")
                logger.debug(f"  • Cookie header present: {'ДА' if 'Cookie' in headers else 'НЕТ'}")
                logger.debug(f"  • Cookie header length: {len(headers.get('Cookie', ''))}")
                if 'Cookie' in headers:
                    cookie_header = headers['Cookie']
                    logger.debug(f"  • Cookie header (первые 300 символов): {cookie_header[:300]}...")
                    logger.debug(f"  • Cookie header (полный): {cookie_header}")
                logger.debug(f"  • User-Agent: {headers.get('User-Agent', 'НЕТ')[:50]}...")
                logger.debug(f"  • Referer: {headers.get('Referer', 'НЕТ')}")
                logger.debug(f"  • Origin: {headers.get('Origin', 'НЕТ')}")
                logger.debug(f"  • Accept: {headers.get('Accept', 'НЕТ')}")
                logger.debug(f"  • Accept-Language: {headers.get('Accept-Language', 'НЕТ')}")
                logger.debug(f"  • Sec-Fetch-Dest: {headers.get('Sec-Fetch-Dest', 'НЕТ')}")
                logger.debug(f"  • Sec-Fetch-Mode: {headers.get('Sec-Fetch-Mode', 'НЕТ')}")
                logger.debug(f"  • Sec-Fetch-Site: {headers.get('Sec-Fetch-Site', 'НЕТ')}")
                logger.debug(f"  • Все заголовки запроса:")
                for header_name, header_value in headers.items():
                    if header_name.lower() == 'cookie':
                        logger.debug(f"    - {header_name}: {header_value[:200]}... (полный: {len(header_value)} символов)")
                    else:
                        logger.debug(f"    - {header_name}: {header_value}")
                
                # Выполняем запрос с обработкой DNS ошибок
                response = None
                dns_retry_count = 0
                max_dns_retries = 2
                
                while dns_retry_count <= max_dns_retries:
                    try:
                        response = await self.session.get(url, headers=headers)
                        break  # Успешно
                    except DNSError as e:
                        dns_retry_count += 1
                        if dns_retry_count <= max_dns_retries:
                            wait_time = dns_retry_count * 3
                            logger.warning(f"⚠️ DNS ошибка при запросе страницы {page} (попытка {dns_retry_count}/{max_dns_retries}). Повтор через {wait_time} сек...")
                            logger.debug(f"  • DNS ошибка: {e}")
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            logger.error(f"❌ DNS ошибка при запросе страницы {page} после {max_dns_retries} попыток: {e}")
                            logger.error(f"  • Проверьте интернет-соединение")
                            logger.error(f"  • URL: {url}")
                            raise  # Пробрасываем ошибку дальше
                    except RequestException as e:
                        logger.warning(f"⚠️ Ошибка запроса страницы {page}: {e}")
                        raise  # Пробрасываем другие ошибки запроса
                
                if not response:
                    logger.error(f"❌ Не удалось получить ответ для страницы {page}")
                    return None
                
                # ДЕТАЛЬНОЕ ЛОГИРОВАНИЕ: Ответ сервера
                logger.debug(f"🔍 ДИАГНОСТИКА: Ответ сервера:")
                logger.debug(f"  • Status code: {response.status_code}")
                logger.debug(f"  • Response headers count: {len(response.headers)}")
                logger.debug(f"  • Content-Type: {response.headers.get('Content-Type', 'НЕТ')}")
                logger.debug(f"  • Content-Length: {response.headers.get('Content-Length', 'НЕТ')}")
                
                # Логируем все заголовки ответа
                logger.debug(f"  • Все заголовки ответа:")
                for header_name, header_value in response.headers.items():
                    if header_name.lower() in ['set-cookie', 'cookie']:
                        logger.debug(f"    - {header_name}: {header_value[:100]}...")
                    else:
                        logger.debug(f"    - {header_name}: {header_value}")
                
                # Логируем Set-Cookie заголовки
                set_cookies = response.headers.get_list('Set-Cookie') if hasattr(response.headers, 'get_list') else []
                if not set_cookies:
                    # Пробуем другой способ
                    set_cookies = [v for k, v in response.headers.items() if k.lower() == 'set-cookie']
                if set_cookies:
                    logger.debug(f"  • Set-Cookie заголовки ({len(set_cookies)}):")
                    for cookie in set_cookies:
                        logger.debug(f"    - {cookie[:150]}...")
                else:
                    logger.debug(f"  • Set-Cookie заголовки: НЕТ")
                
                # Логируем начало тела ответа
                try:
                    response_text_preview = response.text[:500] if hasattr(response, 'text') else str(response.content[:500])
                    logger.debug(f"  • Response body preview (500 chars): {response_text_preview}")
                except:
                    logger.debug(f"  • Response body: не удалось прочитать")
                
                # Проверяем cookies в jar после запроса
                if hasattr(self.session, 'cookies') and self.session.cookies:
                    try:
                        cookies_after = self.session.cookies.get_dict(domain='ozon.ru')
                        cookies_after_dot = self.session.cookies.get_dict(domain='.ozon.ru')
                        cookies_after.update(cookies_after_dot)
                        logger.debug(f"  • Cookies в jar после запроса: {list(cookies_after.keys())}")
                        new_cookies = set(cookies_after.keys()) - set(self._cookies_dict.keys())
                        if new_cookies:
                            logger.debug(f"  • Новые cookies после запроса: {list(new_cookies)}")
                    except:
                        pass
                elapsed_time = time.time() - start_time
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                        
                        # Проверяем наличие данных
                        if not data:
                            logger.warning(f"⚠️ Страница {page}: пустой ответ")
                            return None
                        
                        logger.info(
                            f"✅ Страница {page}: успешно загружена за {elapsed_time:.2f} сек."
                        )
                        return data
                        
                    except Exception as e:
                        logger.error(
                            f"❌ Ошибка парсинга JSON ответа для страницы {page} "
                            f"(время: {elapsed_time:.2f} сек): {e}"
                        )
                        return None
                        
                elif response.status_code == 403:
                    # Проверяем наличие ozon-antibot header (Perplexity Fix #2)
                    response_headers = response.headers if hasattr(response, 'headers') else {}
                    is_antibot_triggered = 'ozon-antibot' in response_headers or 'ozon-antibot' in str(response_headers).lower()
                    
                    if is_antibot_triggered:
                        self._antibot_triggered_count += 1
                        logger.error(
                            f"🚫 Ozon antibot активирован (попытка {retry_count + 1}/{self._antibot_triggered_count} всего)"
                        )
                    
                    # ДЕТАЛЬНОЕ ЛОГИРОВАНИЕ: Анализ 403 ошибки
                    logger.error(f"🔍 ДИАГНОСТИКА 403 ОШИБКИ:")
                    logger.error(f"  • URL запроса: {url}")
                    logger.error(f"  • Retry count: {retry_count}")
                    logger.error(f"  • Antibot header: {'ДА (ozon-antibot: 1)' if is_antibot_triggered else 'НЕТ'}")
                    logger.error(f"  • Всего срабатываний антибота: {self._antibot_triggered_count}")
                    logger.error(f"  • Cookies в словаре: {len(self._cookies_dict)}")
                    logger.error(f"  • Cookies names: {list(self._cookies_dict.keys())}")
                    logger.error(f"  • Proxy: {self.proxy if self.proxy else 'НЕ ИСПОЛЬЗУЕТСЯ'}")
                    
                    # Диагностическое логирование cookies (Perplexity Fix #4)
                    self._log_cookies_diagnostic()
                    
                    # Пробуем получить больше информации из ответа
                    try:
                        response_text = response.text[:1000] if hasattr(response, 'text') else str(response.content[:1000])
                        logger.error(f"  • Response body (1000 chars): {response_text}")
                        
                        # Ищем ключевые слова в ответе
                        if 'captcha' in response_text.lower() or 'challenge' in response_text.lower():
                            logger.error(f"  • ⚠️ Обнаружен CAPTCHA/Challenge в ответе!")
                        if 'blocked' in response_text.lower() or 'заблокирован' in response_text.lower():
                            logger.error(f"  • ⚠️ Обнаружена блокировка в ответе!")
                        if 'ip' in response_text.lower():
                            logger.error(f"  • ⚠️ Упоминание IP в ответе!")
                    except Exception as e:
                        logger.error(f"  • Не удалось прочитать response body: {e}")
                    
                    # Обработка antibot блокировки (Perplexity Fix #2)
                    if is_antibot_triggered and retry_count > 0:
                        # После повторной попытки антибот все еще активен
                        raise OzonAntibotException(
                            f"❌ Ozon antibot заблокировал доступ после {retry_count + 1} попыток. "
                            f"Всего срабатываний: {self._antibot_triggered_count}. "
                            f"Рекомендации:\n"
                            f"  • Сделайте паузу 5-10 минут\n"
                            f"  • Смените IP адрес (VPN/proxy)\n"
                            f"  • Уменьшите частоту запросов\n"
                            f"  • Используйте headless=False для отладки"
                        )
                    
                    # Первая попытка - пробуем обновить cookies
                    if retry_count == 0:
                        logger.debug(f"  • Попытка обновить cookies через повторную инициализацию...")
                        # Повторно инициализируем сессию для получения свежих cookies
                        await self._initialize_session()
                        # Увеличенная задержка перед повтором (ChatGPT/Grok рекомендации)
                        await asyncio.sleep(5.0)
                        return await self._fetch_page(seller_id, seller_name, page, 
                                                      paginator_token, search_page_state, 
                                                      retry_count + 1)
                    else:
                        # Логируем финальные детали для диагностики
                        logger.error(
                            f"❌ Forbidden (403) при запросе страницы {page} (после retry):\n"
                            f"URL: {url}\n"
                            f"Cookies в заголовке: {'ДА' if self._cookies_header else 'НЕТ'}\n"
                            f"Cookies count: {len(self._cookies_dict)}\n"
                            f"Cookies: {list(self._cookies_dict.keys())}\n"
                            f"Proxy: {self.proxy if self.proxy else 'НЕ ИСПОЛЬЗУЕТСЯ'}"
                        )
                        return None
                        
                elif response.status_code == 429:
                    # Rate limiting
                    wait_time = min(2.0 * (2 ** retry_count), 30.0)
                    
                    if retry_count < max_retries:
                        logger.warning(
                            f"⚠️ Rate limit (429) при запросе страницы {page}. "
                            f"Повтор через {wait_time:.1f} сек (попытка {retry_count + 1}/{max_retries})..."
                        )
                        await asyncio.sleep(wait_time)
                        return await self._fetch_page(seller_id, seller_name, page, 
                                                      paginator_token, search_page_state, 
                                                      retry_count + 1)
                    else:
                        logger.error(
                            f"❌ Rate limit (429) при запросе страницы {page} после {max_retries} попыток. "
                            f"Пропускаем страницу."
                        )
                        return None
                        
                else:
                    logger.warning(
                        f"⚠️ Ошибка запроса страницы {page}: статус {response.status_code}"
                    )
                    try:
                        response_text = response.text[:200]
                        logger.debug(f"Ответ сервера: {response_text}")
                    except:
                        pass
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
    
    async def fetch_seller_catalog(self, seller_id: int, seller_name: str, max_pages: int = 100) -> List[Dict]:
        """Получает весь каталог продавца (все страницы).
        
        Args:
            seller_id: ID продавца
            seller_name: Название продавца (из URL, например "cosmo-beauty")
            max_pages: Максимальное количество страниц (защита от бесконечного цикла)
        
        Returns:
            Список всех товаров из каталога
        """
        catalog_start_time = time.time()
        cabinet_name = self.CABINET_MAPPING.get(seller_id, f"UNKNOWN_{seller_id}")
        
        logger.info(
            f"🚀 Начинаем загрузку каталога продавца {seller_id} ({cabinet_name}) "
            f"через entrypoint API..."
        )
        
        all_products = []
        page = 1
        paginator_token = None
        search_page_state = None
        successful_pages = 0
        failed_pages = 0
        
        # Загружаем первую страницу
        first_page_start = time.time()
        first_page_data = await self._fetch_page(seller_id, seller_name, page)
        first_page_time = time.time() - first_page_start
        
        if not first_page_data:
            logger.error(
                f"❌ Не удалось получить первую страницу для продавца {seller_id} "
                f"(время: {first_page_time:.2f} сек)"
            )
            return []
        
        # Парсим товары с первой страницы
        products = self.parse_products_from_page(first_page_data)
        all_products.extend(products)
        successful_pages += 1
        
        # Извлекаем параметры для следующей страницы
        next_page_url = first_page_data.get("nextPage")
        
        logger.info(
            f"✅ Страница 1: получено {len(products)} товаров "
            f"(время: {first_page_time:.2f} сек)"
        )
        
        # Если есть nextPage, продолжаем загрузку
        while next_page_url and page < max_pages:
            page += 1
            
            # Извлекаем параметры из nextPage URL
            try:
                from urllib.parse import urlparse, parse_qs
                parsed = urlparse(next_page_url)
                params = parse_qs(parsed.query)
                
                paginator_token = params.get('paginator_token', [None])[0]
                search_page_state = params.get('search_page_state', [None])[0]
                
                page_data = await self._fetch_page(
                    seller_id, seller_name, page, 
                    paginator_token, search_page_state
                )
                
                if not page_data:
                    failed_pages += 1
                    break
                
                products = self.parse_products_from_page(page_data)
                all_products.extend(products)
                successful_pages += 1
                
                # Проверяем наличие следующей страницы
                next_page_url = page_data.get("nextPage")
                
                if not products:
                    # Если товаров нет, прекращаем
                    break
                    
            except Exception as e:
                logger.error(f"❌ Ошибка при обработке страницы {page}: {e}")
                failed_pages += 1
                break
        
        catalog_time = time.time() - catalog_start_time
        
        logger.success(
            f"✅ Каталог продавца {seller_id} ({cabinet_name}) загружен: "
            f"всего товаров {len(all_products)}, "
            f"страниц успешно {successful_pages}, "
            f"страниц с ошибками {failed_pages}, "
            f"время загрузки {catalog_time:.2f} сек"
        )
        
        return all_products
    
    @staticmethod
    def parse_products_from_page(page_data: Dict) -> List[Dict]:
        """Парсит товары из JSON ответа entrypoint API.
        
        Returns:
            Список товаров с базовой информацией
        """
        products = []
        
        try:
            # Ищем widgetStates с товарами
            widget_states = page_data.get("widgetStates", {})
            
            for state_id, state_json in widget_states.items():
                # Ищем состояния с типом tileGridDesktop (список товаров)
                if "tileGridDesktop" not in state_id:
                    continue
                
                # Парсим JSON из строки
                import json
                try:
                    state_data = json.loads(state_json)
                except:
                    # Если уже dict, используем как есть
                    state_data = state_json
                
                items = state_data.get("items", [])
                
                for item in items:
                    try:
                        product = OzonCatalogAPI.parse_product(item)
                        if product:
                            products.append(product)
                    except Exception as e:
                        logger.debug(f"Ошибка при парсинге товара: {e}")
                        continue
        
        except Exception as e:
            logger.error(f"Ошибка при парсинге страницы: {e}")
        
        return products
    
    @staticmethod
    def parse_product(item: Dict) -> Optional[Dict]:
        """Парсит товар из JSON.
        
        Returns:
            Словарь с данными о товаре или None
        """
        try:
            sku = item.get("sku")
            if not sku:
                return None
            
            # Извлекаем название товара
            product_name = ""
            main_state = item.get("mainState", [])
            
            for state in main_state:
                if state.get("type") == "textAtom":
                    text_atom = state.get("textAtom", {})
                    product_name = text_atom.get("text", "")
                    break
            
            # Извлекаем цены
            current_price = None
            original_price = None
            discount_percent = None
            
            for state in main_state:
                if state.get("type") == "priceV2":
                    price_v2 = state.get("priceV2", {})
                    prices = price_v2.get("price", [])
                    
                    for price_item in prices:
                        text_style = price_item.get("textStyle")
                        price_text = price_item.get("text", "")
                        
                        # Извлекаем числовое значение из строки "548 ₽"
                        price_value = price_text.replace("₽", "").replace(" ", "").strip()
                        
                        try:
                            price_value = float(price_value)
                        except:
                            continue
                        
                        if text_style == "PRICE":
                            current_price = price_value
                        elif text_style == "ORIGINAL_PRICE":
                            original_price = price_value
                    
                    # Извлекаем процент скидки
                    discount_text = price_v2.get("discount", "")
                    if discount_text:
                        # Извлекаем числовое значение из "−68%"
                        discount_value = discount_text.replace("−", "").replace("%", "").strip()
                        try:
                            discount_percent = float(discount_value)
                        except:
                            pass
                    
                    break
            
            return {
                "sku": sku,
                "product_name": product_name,
                "current_price": current_price,
                "original_price": original_price,
                "discount_percent": discount_percent,
                "source": "catalog_api"
            }
            
        except Exception as e:
            logger.debug(f"Ошибка при парсинге товара: {e}")
            return None
