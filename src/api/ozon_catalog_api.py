"""Модуль для работы с публичным API каталога продавца Ozon (entrypoint)."""
import asyncio
import os
import re
import time
from typing import List, Dict, Optional
from urllib.parse import urlencode, quote
from curl_cffi.requests import AsyncSession
from curl_cffi.requests.exceptions import DNSError, RequestException
from loguru import logger
from src.exceptions import OzonAntibotException


def get_playwright_headless() -> bool:
    """Получает настройку headless режима Playwright из переменной окружения.
    
    Читает переменную каждый раз при вызове, чтобы учитывать изменения в .env файле.
    
    Returns:
        True если headless режим включен, False если выключен
    """
    headless_str = os.getenv('OZON_PLAYWRIGHT_HEADLESS', 'true').lower().strip()
    return headless_str in ('true', '1', 'yes')


class OzonCatalogAPI:
    """Клиент для работы с публичным API каталога продавца Ozon."""
    
    BASE_URL = "https://www.ozon.ru/api/entrypoint-api.bx/page/json/v2"
    
    # Маппинг seller_id -> название кабинета
    CABINET_MAPPING = {
        176640: "COSMO_BEAUTY",
    }
    
    def __init__(self, request_delay: float = 3.0, max_concurrent: int = 2, 
                 auto_get_cookies: bool = True, cookies: Optional[str] = None,
                 proxy: Optional[str] = None, mode: Optional[str] = None):
        """Инициализация клиента.
        
        Args:
            request_delay: Задержка между запросами (секунды) - рекомендуется 3-5 сек для обхода антибота
            max_concurrent: Максимальное количество параллельных запросов
            auto_get_cookies: Автоматически получать cookies из браузера если не переданы
            cookies: Опциональные cookies из браузера в формате "name1=value1; name2=value2"
            proxy: Опциональный прокси-сервер в формате "http://host:port" или "socks5://host:port"
            mode: Режим работы - "light" (HTTP-only, без Playwright) или "full" (с Playwright fallback)
                  Если None, читается из OZON_MODE в .env (по умолчанию "full")
        """
        self.request_delay = request_delay
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.session: Optional[AsyncSession] = None
        self.auto_get_cookies = auto_get_cookies
        self.custom_cookies = cookies
        self.proxy = proxy
        
        # Определяем режим работы
        if mode is None:
            mode = os.getenv('OZON_MODE', 'full').lower().strip()
        self.mode = mode if mode in ('light', 'full') else 'full'
        
        # Логируем предупреждение для LIGHT режима
        if self.mode == 'light':
            logger.warning(
                "⚠️ LIGHT режим активирован: Playwright fallback отключен. "
                "Риск блокировок повышен. Используйте cookies из файла (Cookies-as-a-Service)."
            )
        
        self._cookies_header: Optional[str] = None
        self._cookies_dict: Dict[str, str] = {}
        self._antibot_triggered_count: int = 0  # Счетчик срабатываний антибота
        
        # Адаптивный контроллер задержек (опционально, включается через .env)
        self.use_adaptive_delay = os.getenv('OZON_ADAPTIVE_DELAY', 'true').lower() in ('true', '1', 'yes')
        if self.use_adaptive_delay:
            from src.utils.adaptive_delayer import AdaptiveDelayer
            self.adaptive_delayer = AdaptiveDelayer(
                initial_delay=request_delay,
                min_delay=0.5,
                max_delay=5.0
            )
        else:
            self.adaptive_delayer = None
        
        # Playwright браузер и контекст (для переиспользования)
        self._playwright_browser = None
        self._playwright_context = None
        self._playwright_p = None
        self._playwright_manager = None  # Контекстный менеджер для Playwright
    
    async def __aenter__(self):
        """Асинхронный контекстный менеджер - вход."""
        # В FULL режиме используем только Playwright (curl_cffi всегда блокируется)
        if self.mode == 'full':
            # Инициализируем Playwright браузер один раз для всех запросов
            try:
                from playwright.async_api import async_playwright
                # Используем async_playwright() как контекстный менеджер
                self._playwright_manager = async_playwright()
                self._playwright_p = await self._playwright_manager.__aenter__()
                
                headless_mode = get_playwright_headless()
                launch_options = {
                    'headless': headless_mode,
                    'args': [
                        '--no-sandbox',
                        '--disable-blink-features=AutomationControlled',
                        '--disable-dev-shm-usage',
                    ]
                }
                
                self._playwright_browser = await self._playwright_p.chromium.launch(**launch_options)
                
                context_options = {
                    'viewport': {'width': 1920, 'height': 1080},
                    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                    'locale': 'ru-RU',
                    'timezone_id': 'Europe/Moscow',
                }
                
                if self.proxy:
                    if self.proxy.startswith('http://') or self.proxy.startswith('https://'):
                        context_options['proxy'] = {'server': self.proxy}
                    elif self.proxy.startswith('socks5://'):
                        context_options['proxy'] = {'server': self.proxy}
                    else:
                        context_options['proxy'] = {'server': f'http://{self.proxy}'}
                
                self._playwright_context = await self._playwright_browser.new_context(**context_options)
                logger.info("🎭 Playwright браузер инициализирован (один экземпляр для всех запросов)")
            except ImportError:
                logger.warning("⚠️ Playwright не установлен, переключаемся на LIGHT режим")
                self.mode = 'light'
            except Exception as e:
                logger.error(f"❌ Ошибка инициализации Playwright: {e}")
                self.mode = 'light'
        
        # В LIGHT режиме используем curl_cffi (но он обычно блокируется)
        if self.mode == 'light':
            self.session = AsyncSession(
                impersonate="chrome131",
                timeout=30,
                verify=True,
                allow_redirects=True,
            )
        
        # Загружаем cookies в порядке приоритета (для Playwright они не критичны, но могут помочь)
        # 1. Если переданы напрямую (custom_cookies) - используем их
        # 2. Если есть файл cookies - загружаем из файла
        # 3. Если auto_get_cookies=True - получаем из браузера
        cookies_loaded = False
        
        if self.custom_cookies:
            await self._load_custom_cookies()
            cookies_loaded = True
        elif self.auto_get_cookies:
            # Сначала пробуем загрузить из файла (Cookies-as-a-Service)
            if await self._load_cookies_from_file():
                cookies_loaded = True
                logger.info("✓ Cookies загружены из файла (Cookies-as-a-Service)")
            else:
                # Fallback: получаем из браузера (как в WB парсере)
                await self._load_cookies_from_browser()
                cookies_loaded = True
        
        # Инициализируем curl_cffi сессию только в LIGHT режиме (в FULL не нужна)
        if self.mode == 'light':
            init_success = await self._initialize_session()
            if not init_success:
                logger.warning("⚠️ Инициализация сессии не удалась, продолжаем без cookies")
        
        return self
    
    async def _load_cookies_from_file(self) -> bool:
        """Загружает cookies из JSON файла (Cookies-as-a-Service).
        
        Проверяет несколько возможных путей:
        1. OZON_COOKIES_PATH из .env
        2. cookies/ozon_cookies.json (по умолчанию)
        
        Returns:
            True если cookies загружены, False если файл не найден
        """
        try:
            import json
            from pathlib import Path
            
            # Определяем путь к файлу cookies
            cookies_path_env = os.getenv("OZON_COOKIES_PATH")
            if cookies_path_env:
                cookies_path = Path(cookies_path_env)
            else:
                # Путь по умолчанию
                project_root = Path(__file__).parent.parent.parent
                cookies_path = project_root / "cookies" / "ozon_cookies.json"
            
            if not cookies_path.exists():
                logger.debug(f"Файл cookies не найден: {cookies_path}")
                return False
            
            # Читаем JSON файл
            with open(cookies_path, 'r', encoding='utf-8') as f:
                cookies_data = json.load(f)
            
            # Поддерживаем два формата:
            # 1. Новый формат: {"cookies": {...}, "cookies_string": "..."}
            # 2. Старый формат: {"name": "value", ...}
            if "cookies_string" in cookies_data:
                cookies_string = cookies_data["cookies_string"]
            elif "cookies" in cookies_data:
                # Формируем строку из словаря cookies
                cookies_dict = cookies_data["cookies"]
                cookies_string = "; ".join([f"{k}={v}" for k, v in cookies_dict.items()])
            else:
                # Старый формат - весь файл это словарь cookies
                cookies_string = "; ".join([f"{k}={v}" for k, v in cookies_data.items()])
            
            if cookies_string:
                self.custom_cookies = cookies_string
                await self._load_custom_cookies()
                logger.info(f"✓ Cookies загружены из файла: {cookies_path}")
                return True
            else:
                logger.warning(f"Файл cookies пуст: {cookies_path}")
                return False
                
        except json.JSONDecodeError as e:
            logger.warning(f"Ошибка парсинга JSON файла cookies: {e}")
            return False
        except Exception as e:
            logger.debug(f"Ошибка при загрузке cookies из файла: {e}")
            return False
    
    async def _load_cookies_from_browser(self):
        """Автоматически загружает cookies из браузера Chrome (как в WB парсере).
        
        Используется как fallback, если файл cookies не найден.
        """
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
        # Закрываем Playwright браузер
        if self._playwright_browser:
            await self._playwright_browser.close()
            self._playwright_browser = None
            self._playwright_context = None
            logger.info("🎭 Playwright браузер закрыт")
        
        # Закрываем контекстный менеджер Playwright
        if self._playwright_manager:
            try:
                await self._playwright_manager.__aexit__(exc_type, exc_val, exc_tb)
            except Exception as e:
                logger.debug(f"Ошибка при закрытии Playwright менеджера: {e}")
            self._playwright_manager = None
            self._playwright_p = None
        
        # Закрываем curl_cffi сессию (если использовалась)
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
    
    async def _fetch_page_via_playwright(self, url: str, seller_name: str, seller_id: int, page_num: int = 1) -> Optional[Dict]:
        """Выполняет запрос к entrypoint API через Playwright (использует переиспользуемый браузер).
        
        Args:
            url: URL для запроса к entrypoint API
            seller_name: Имя продавца (для Referer)
            seller_id: ID продавца
            page_num: Номер страницы (для логирования)
            
        Returns:
            JSON данные ответа или None при ошибке
        """
        try:
            from playwright_stealth import stealth
            
            # Используем переиспользуемый браузер и контекст
            if not self._playwright_context:
                logger.error("❌ Playwright контекст не инициализирован")
                return None
            
            # Создаем новую вкладку в существующем контексте (не открываем новое окно)
            page = await self._playwright_context.new_page()
            
            try:
                # Применяем stealth (если доступен)
                try:
                    if callable(stealth):
                        stealth(page)
                except:
                    pass
                
                # Сначала открываем страницу продавца для установки cookies (только для первой страницы)
                seller_page_url = f"https://www.ozon.ru/seller/{seller_name}-{seller_id}/"
                
                if page_num == 1:
                    logger.debug(f"  • Открываем страницу продавца: {seller_page_url}")
                    await page.goto(seller_page_url, wait_until='networkidle', timeout=30000)
                    await asyncio.sleep(1)  # Небольшая задержка для загрузки
                
                # Делаем запрос к API через Playwright
                headers = {
                    'Accept': 'application/json, text/plain, */*',
                    'Referer': seller_page_url,
                    'Origin': 'https://www.ozon.ru'
                }
                
                logger.debug(f"  • Запрос к API через вкладку (страница {page_num})")
                response = await page.request.get(url, headers=headers)
                
                if response.status == 200:
                    try:
                        data = await response.json()
                        logger.success(f"✅ Playwright запрос успешен: получен JSON ответ (страница {page_num})")
                        return data
                    except Exception as e:
                        logger.error(f"❌ Ошибка парсинга JSON из Playwright ответа: {e}")
                        return None
                else:
                    logger.warning(f"⚠️ Playwright вернул статус {response.status} (страница {page_num})")
                    return None
                    
            finally:
                # Закрываем вкладку (но не браузер)
                await page.close()
                    
        except Exception as e:
            logger.error(f"❌ Ошибка при Playwright запросе: {e}")
            logger.debug("Детали ошибки:", exc_info=True)
            return None
    
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
                # Используем адаптивную задержку если включена, иначе фиксированную
                delay = self.adaptive_delayer.get_delay() if self.adaptive_delayer else self.request_delay
                await asyncio.sleep(delay)
                
                logger.debug(f"📥 Запрос страницы {page} для продавца {seller_id}...")
                
                # В FULL режиме используем только Playwright (curl_cffi всегда блокируется)
                if self.mode == 'full':
                    playwright_result = await self._fetch_page_via_playwright(url, seller_name, seller_id, page)
                    if playwright_result:
                        elapsed_time = time.time() - start_time
                        logger.info(f"✅ Страница {page}: успешно загружена за {elapsed_time:.2f} сек.")
                        return playwright_result
                    else:
                        logger.error(f"❌ Не удалось получить страницу {page} через Playwright")
                        return None
                
                # LIGHT режим: пробуем curl_cffi (но он обычно блокируется)
                if not self.session:
                    logger.error("❌ curl_cffi сессия не инициализирована в LIGHT режиме")
                    return None
                
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
                    # Успешный запрос - уведомляем адаптивный контроллер
                    if self.adaptive_delayer:
                        self.adaptive_delayer.on_success()
                    
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
                        # Уведомляем адаптивный контроллер о блокировке
                        if self.adaptive_delayer:
                            self.adaptive_delayer.on_block()
                        
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
                    
                    # LIGHT режим - curl_cffi заблокирован, Playwright недоступен
                    logger.error(
                        f"❌ LIGHT режим: curl_cffi заблокирован, Playwright fallback недоступен. "
                        f"Рекомендации:\n"
                        f"  • Используйте cookies из файла (Cookies-as-a-Service)\n"
                        f"  • Переключитесь на FULL режим (OZON_MODE=full)\n"
                        f"  • Сделайте паузу 5-10 минут"
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
    
    async def fetch_seller_catalog(self, seller_id: int, seller_name: str, max_pages: int = 100, max_products: int = None) -> List[Dict]:
        """Получает весь каталог продавца (все страницы).
        
        Args:
            seller_id: ID продавца
            seller_name: Название продавца (из URL, например "cosmo-beauty")
            max_pages: Максимальное количество страниц (защита от бесконечного цикла)
            max_products: Максимальное количество товаров (для тестового режима). Если None - без ограничений
        
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
        
        # Проверяем лимит товаров для тестового режима
        if max_products is not None:
            all_products.extend(products[:max_products])
            if len(products) > max_products:
                logger.info(
                    f"ℹ️ Добавлено {max_products} товаров с первой страницы (лимит). "
                    f"Пропущено {len(products) - max_products} товаров"
                )
        else:
            all_products.extend(products)
        
        successful_pages += 1
        
        # Если достигнут лимит после первой страницы, прекращаем
        if max_products is not None and len(all_products) >= max_products:
            logger.info(
                f"ℹ️ Достигнут лимит товаров ({max_products}) после первой страницы. "
                f"Остановка загрузки."
            )
            catalog_time = time.time() - catalog_start_time
            logger.success(
                f"✅ Каталог продавца {seller_id} ({cabinet_name}) загружен: "
                f"всего товаров {len(all_products)}, страниц успешно {successful_pages}, "
                f"страниц с ошибками {failed_pages}, время загрузки {catalog_time:.2f} сек"
            )
            return all_products
        
        # Извлекаем параметры для следующей страницы
        # Пробуем разные варианты полей для пагинации
        next_page_url = first_page_data.get("nextPage")
        pagination_info = None
        
        # ДИАГНОСТИКА: Проверяем структуру ответа для пагинации
        logger.debug(f"🔍 ДИАГНОСТИКА пагинации (страница 1):")
        logger.debug(f"  • Ключи в ответе: {list(first_page_data.keys())[:10]}")
        logger.debug(f"  • nextPage присутствует: {'ДА' if next_page_url else 'НЕТ'}")
        
        # Ищем пагинацию в widgetStates (tileGridDesktop)
        widget_states = first_page_data.get("widgetStates", {})
        for state_id, state_json in widget_states.items():
            if "tileGridDesktop" in state_id:
                try:
                    import json
                    try:
                        state_data = json.loads(state_json)
                    except:
                        state_data = state_json
                    
                    # Ищем поля пагинации в state_data
                    logger.debug(f"  • Проверяем tileGridDesktop для пагинации...")
                    logger.debug(f"  • Ключи в state_data: {list(state_data.keys())[:15]}")
                    
                    # Проверяем количество товаров на странице
                    items_count = len(state_data.get("items", []))
                    current_page = state_data.get("page", 1)
                    logger.debug(f"  • Товаров на странице: {items_count}, текущая страница: {current_page}")
                    
                    # Проверяем sharedData (может содержать информацию о пагинации)
                    shared_data = state_data.get("sharedData", {})
                    if shared_data:
                        logger.debug(f"  • Найдено sharedData, ключи: {list(shared_data.keys())[:10]}")
                        if "pagination" in shared_data:
                            pagination_info = shared_data.get("pagination")
                            logger.debug(f"  • ✅ Найдено 'pagination' в sharedData")
                        if "nextPage" in shared_data:
                            next_page_url = shared_data.get("nextPage")
                            logger.debug(f"  • ✅ Найдено 'nextPage' в sharedData")
                        if "paginatorToken" in shared_data:
                            paginator_token = shared_data.get("paginatorToken")
                            logger.debug(f"  • ✅ Найдено 'paginatorToken' в sharedData: {paginator_token[:50] if paginator_token else None}")
                        if "searchPageState" in shared_data:
                            search_page_state = shared_data.get("searchPageState")
                            logger.debug(f"  • ✅ Найдено 'searchPageState' в sharedData")
                    
                    # Проверяем различные варианты полей пагинации в state_data
                    if "nextPage" in state_data:
                        next_page_url = state_data.get("nextPage")
                        logger.debug(f"  • ✅ Найдено nextPage в tileGridDesktop: {next_page_url[:200] if next_page_url else None}")
                    if "next" in state_data:
                        next_val = state_data.get("next")
                        logger.debug(f"  • ✅ Найдено 'next' в tileGridDesktop: {type(next_val)}")
                        if isinstance(next_val, str) and next_val:
                            next_page_url = next_val
                        elif isinstance(next_val, dict):
                            pagination_info = next_val
                    if "pagination" in state_data:
                        pagination_info = state_data.get("pagination")
                        logger.debug(f"  • ✅ Найдено 'pagination' в tileGridDesktop: {type(pagination_info)}")
                    if "hasNext" in state_data:
                        has_next = state_data.get("hasNext")
                        logger.debug(f"  • ✅ Найдено 'hasNext' в tileGridDesktop: {has_next}")
                        if has_next:
                            # Если hasNext=True, но нет токенов, пробуем следующую страницу с инкрементом
                            if not current_paginator_token and not current_search_page_state:
                                logger.debug(f"  • hasNext=True, но нет токенов - будем пробовать следующую страницу")
                    if "paginatorToken" in state_data:
                        paginator_token = state_data.get("paginatorToken")
                        logger.debug(f"  • ✅ Найдено 'paginatorToken' в tileGridDesktop: {paginator_token[:50] if paginator_token else None}")
                    if "searchPageState" in state_data:
                        search_page_state = state_data.get("searchPageState")
                        logger.debug(f"  • ✅ Найдено 'searchPageState' в tileGridDesktop")
                    
                    # Если получили 12 товаров (типичная полная страница), возможно есть следующая
                    # Но это не надёжный индикатор, поэтому используем только если есть явные признаки
                except Exception as e:
                    logger.debug(f"  • Ошибка при проверке tileGridDesktop: {e}")
        
        # Если не нашли в widgetStates, проверяем корневой уровень
        if not next_page_url:
            # Проверяем pageInfo (может содержать информацию о пагинации)
            page_info = first_page_data.get("pageInfo", {})
            if page_info:
                logger.debug(f"  • Найдено pageInfo, ключи: {list(page_info.keys())[:10]}")
                if "nextPage" in page_info:
                    next_page_url = page_info.get("nextPage")
                    logger.debug(f"  • ✅ Найдено 'nextPage' в pageInfo")
                if "pagination" in page_info:
                    pagination_info = page_info.get("pagination")
                    logger.debug(f"  • ✅ Найдено 'pagination' в pageInfo")
            
            if "next" in first_page_data:
                next_val = first_page_data.get("next")
                logger.debug(f"  • ✅ Найдено 'next' в корневом уровне: {type(next_val)}")
                if isinstance(next_val, str) and next_val:
                    next_page_url = next_val
                elif isinstance(next_val, dict):
                    pagination_info = next_val
            if "pagination" in first_page_data:
                pagination_info = first_page_data.get("pagination")
                logger.debug(f"  • ✅ Найдено 'pagination' в корневом уровне")
        
        # Если всё ещё нет информации о пагинации, но получили 12 товаров (полная страница),
        # пробуем следующую страницу с инкрементом page (на основе данных из F12)
        # Это эвристика: если получили полную страницу, вероятно есть следующая
        if not next_page_url and not pagination_info and len(products) == 12:
            logger.debug(f"  • ⚠️ Пагинация не найдена, но получено 12 товаров (полная страница)")
            logger.debug(f"  • Пробуем следующую страницу с инкрементом page (page=2)")
            # Устанавливаем флаг для попытки следующей страницы
            # В цикле будем пробовать page=2 без токенов (Ozon может принять такой запрос)
            current_paginator_token = None  # Будем пробовать без токенов для page=2
            current_search_page_state = None
        
        if next_page_url:
            logger.debug(f"  • ✅ Используем nextPage URL: {next_page_url[:200]}")
        elif pagination_info:
            logger.debug(f"  • ✅ Используем pagination info: {pagination_info}")
        else:
            logger.debug(f"  • ⚠️ Пагинация не найдена - возможно, это последняя страница или у продавца только одна страница")
        
        logger.info(
            f"✅ Страница 1: получено {len(products)} товаров "
            f"(время: {first_page_time:.2f} сек)"
        )
        
        # Если есть nextPage или pagination_info, продолжаем загрузку
        current_paginator_token = None
        current_search_page_state = None
        
        # Извлекаем параметры из pagination_info, если есть
        if pagination_info and isinstance(pagination_info, dict):
            current_paginator_token = pagination_info.get("paginatorToken") or pagination_info.get("paginator_token")
            current_search_page_state = pagination_info.get("searchPageState") or pagination_info.get("search_page_state")
        
        # Если есть nextPage URL, извлекаем параметры из него
        if next_page_url:
            try:
                from urllib.parse import urlparse, parse_qs
                parsed = urlparse(next_page_url)
                params = parse_qs(parsed.query)
                
                if not current_paginator_token:
                    current_paginator_token = params.get('paginator_token', [None])[0]
                if not current_search_page_state:
                    current_search_page_state = params.get('search_page_state', [None])[0]
            except Exception as e:
                logger.debug(f"  • Ошибка при парсинге nextPage URL: {e}")
        
        # Флаг для эвристической пагинации (если получили полную страницу, но нет токенов)
        try_next_page_heuristic = (not next_page_url and not current_paginator_token and 
                                   not current_search_page_state and len(products) == 12)
        
        # Продолжаем загрузку, если есть информация о следующей странице или эвристика
        while ((next_page_url or current_paginator_token or current_search_page_state or try_next_page_heuristic) 
               and page < max_pages):
            page += 1
            
            try:
                logger.info(f"📄 Загрузка страницы {page}...")
                
                page_data = await self._fetch_page(
                    seller_id, seller_name, page, 
                    current_paginator_token, current_search_page_state
                )
                
                if not page_data:
                    failed_pages += 1
                    logger.warning(f"⚠️ Не удалось загрузить страницу {page}")
                    break
                
                products = self.parse_products_from_page(page_data)
                
                # Проверяем лимит товаров для тестового режима
                if max_products is not None and len(all_products) >= max_products:
                    logger.info(
                        f"ℹ️ Достигнут лимит товаров ({max_products}). "
                        f"Остановка загрузки. Всего собрано: {len(all_products)}"
                    )
                    break
                
                # Добавляем товары с учетом лимита
                if max_products is not None:
                    remaining = max_products - len(all_products)
                    if remaining > 0:
                        all_products.extend(products[:remaining])
                        if len(products) > remaining:
                            logger.info(
                                f"ℹ️ Добавлено {remaining} товаров (лимит {max_products}). "
                                f"Пропущено {len(products) - remaining} товаров"
                            )
                    else:
                        break
                else:
                    all_products.extend(products)
                
                successful_pages += 1
                
                logger.info(
                    f"✅ Страница {page}: получено {len(products)} товаров. "
                    f"Всего собрано: {len(all_products)}"
                )
                
                if not products:
                    # Если товаров нет, прекращаем
                    logger.info(f"ℹ️ Страница {page} пустая, прекращаем загрузку")
                    break
                
                # Проверяем лимит после добавления
                if max_products is not None and len(all_products) >= max_products:
                    logger.info(
                        f"ℹ️ Достигнут лимит товаров ({max_products}). Остановка загрузки."
                    )
                    break
                
                # Ищем информацию о следующей странице в ответе
                next_page_url = None
                pagination_info = None
                
                # Ищем в widgetStates (tileGridDesktop)
                widget_states = page_data.get("widgetStates", {})
                for state_id, state_json in widget_states.items():
                    if "tileGridDesktop" in state_id:
                        try:
                            import json
                            try:
                                state_data = json.loads(state_json)
                            except:
                                state_data = state_json
                            
                            # Проверяем sharedData
                            shared_data = state_data.get("sharedData", {})
                            if shared_data:
                                if "paginatorToken" in shared_data:
                                    current_paginator_token = shared_data.get("paginatorToken")
                                    logger.debug(f"  • Извлечён paginatorToken из sharedData: {current_paginator_token[:50] if current_paginator_token else None}")
                                if "searchPageState" in shared_data:
                                    current_search_page_state = shared_data.get("searchPageState")
                                    logger.debug(f"  • Извлечён searchPageState из sharedData")
                                if "pagination" in shared_data:
                                    pagination_info = shared_data.get("pagination")
                                if "nextPage" in shared_data:
                                    next_page_url = shared_data.get("nextPage")
                            
                            if "nextPage" in state_data:
                                next_page_url = state_data.get("nextPage")
                            elif "next" in state_data:
                                next_val = state_data.get("next")
                                if isinstance(next_val, str) and next_val:
                                    next_page_url = next_val
                                elif isinstance(next_val, dict):
                                    pagination_info = next_val
                            if "pagination" in state_data:
                                pagination_info = state_data.get("pagination")
                            if "paginatorToken" in state_data:
                                current_paginator_token = state_data.get("paginatorToken")
                                logger.debug(f"  • Извлечён paginatorToken из state_data: {current_paginator_token[:50] if current_paginator_token else None}")
                            if "searchPageState" in state_data:
                                current_search_page_state = state_data.get("searchPageState")
                                logger.debug(f"  • Извлечён searchPageState из state_data")
                        except Exception as e:
                            logger.debug(f"Ошибка при проверке пагинации: {e}")
                
                # Если не нашли в widgetStates, проверяем корневой уровень
                if not next_page_url:
                    # Проверяем pageInfo
                    page_info = page_data.get("pageInfo", {})
                    if page_info:
                        if "nextPage" in page_info:
                            next_page_url = page_info.get("nextPage")
                            logger.debug(f"  • Найдено 'nextPage' в pageInfo страницы {page}")
                        if "pagination" in page_info:
                            pagination_info = page_info.get("pagination")
                            logger.debug(f"  • Найдено 'pagination' в pageInfo страницы {page}")
                    
                    if "nextPage" in page_data:
                        next_page_url = page_data.get("nextPage")
                    elif "next" in page_data:
                        next_val = page_data.get("next")
                        if isinstance(next_val, str) and next_val:
                            next_page_url = next_val
                        elif isinstance(next_val, dict):
                            pagination_info = next_val
                    if "pagination" in page_data:
                        pagination_info = page_data.get("pagination")
                
                # Обновляем параметры пагинации из pagination_info
                if pagination_info and isinstance(pagination_info, dict):
                    current_paginator_token = pagination_info.get("paginatorToken") or pagination_info.get("paginator_token") or current_paginator_token
                    current_search_page_state = pagination_info.get("searchPageState") or pagination_info.get("search_page_state") or current_search_page_state
                
                # Обновляем флаг эвристической пагинации
                try_next_page_heuristic = (not next_page_url and not current_paginator_token and 
                                           not current_search_page_state and len(products) == 12)
                
                # Если нет информации о следующей странице и не используем эвристику, прекращаем
                if not next_page_url and not current_paginator_token and not current_search_page_state and not try_next_page_heuristic:
                    logger.info(f"ℹ️ Информация о следующей странице не найдена, прекращаем загрузку")
                    break
                
                # Если используем эвристику и получили меньше 12 товаров, прекращаем
                if try_next_page_heuristic and len(products) < 12:
                    logger.info(f"ℹ️ Получено меньше 12 товаров ({len(products)}), прекращаем эвристическую пагинацию")
                    break
                    
            except Exception as e:
                logger.error(f"❌ Ошибка при обработке страницы {page}: {e}")
                logger.debug("Детали ошибки:", exc_info=True)
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
                            # Краткое логирование по каждому товару
                            sku = product.get('sku', 'N/A')
                            price = product.get('current_price', 'N/A')
                            old_price = product.get('original_price', 'N/A')
                            discount = product.get('discount_percent', 'N/A')
                            logger.debug(f"  ✓ SKU {sku}: цена={price}, старая={old_price}, скидка={discount}%")
                        else:
                            sku = item.get('sku', 'N/A')
                            logger.debug(f"  ✗ SKU {sku}: товар не распарсен")
                    except Exception as e:
                        sku = item.get('sku', 'N/A') if isinstance(item, dict) else 'N/A'
                        logger.debug(f"  ✗ SKU {sku}: ошибка парсинга - {e}")
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
            
            # Пробуем извлечь offer_id из разных мест в структуре
            offer_id = None
            
            # Вариант 1: Прямое поле в item
            offer_id = item.get("offer_id") or item.get("offerId") or item.get("offer")
            
            # Вариант 2: В action/link (может быть в URL товара)
            if not offer_id:
                action = item.get("action", {})
                link = action.get("link", "") if isinstance(action, dict) else ""
                # Пробуем извлечь из URL товара (если там есть offer_id)
                if link and "offer" in link.lower():
                    import re
                    # Ищем паттерны типа offer=XXX или offer_id=XXX
                    offer_match = re.search(r'offer[_-]?id=([^&/?]+)', link, re.IGNORECASE)
                    if offer_match:
                        offer_id = offer_match.group(1)
            
            # Вариант 3: В multiButton или других вложенных структурах
            if not offer_id:
                multi_button = item.get("multiButton", {})
                if isinstance(multi_button, dict):
                    ozon_button = multi_button.get("ozonButton", {})
                    if isinstance(ozon_button, dict):
                        add_to_cart = ozon_button.get("addToCart", {})
                        if isinstance(add_to_cart, dict):
                            # Может быть в params или других полях
                            params = add_to_cart.get("params", {})
                            if isinstance(params, dict):
                                offer_id = params.get("offer_id") or params.get("offerId")
            
            # Вариант 4: В trackingInfo или других метаданных
            if not offer_id:
                tracking_info = item.get("trackingInfo", {})
                if isinstance(tracking_info, dict):
                    # Может быть в ключах или значениях
                    for key, value in tracking_info.items():
                        if "offer" in key.lower() and value:
                            offer_id = str(value)
                            break
            
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
            
            # Ищем цены в разных форматах
            for state in main_state:
                state_type = state.get("type")
                
                # Формат 1: priceV2 (основной формат)
                if state_type == "priceV2":
                    price_v2 = state.get("priceV2", {})
                    prices = price_v2.get("price", [])
                    
                    # Если prices - это список
                    if isinstance(prices, list):
                        for price_item in prices:
                            text_style = price_item.get("textStyle")
                            price_text = price_item.get("text", "")
                            
                            # Извлекаем числовое значение из строки "548 ₽" или "1 548 ₽"
                            price_value_str = price_text.replace("₽", "").replace(" ", "").replace("\u00A0", "").strip()
                            
                            try:
                                price_value = float(price_value_str)
                            except:
                                # Пробуем извлечь число из строки с помощью регулярного выражения
                                import re
                                numbers = re.findall(r'\d+', price_text.replace(" ", "").replace("\u00A0", ""))
                                if numbers:
                                    try:
                                        price_value = float("".join(numbers))
                                    except:
                                        continue
                                else:
                                    continue
                            
                            if text_style == "PRICE":
                                if current_price is None:  # Берем первое найденное значение
                                    current_price = price_value
                            elif text_style == "ORIGINAL_PRICE":
                                if original_price is None:  # Берем первое найденное значение
                                    original_price = price_value
                            elif text_style is None and current_price is None:
                                # Если textStyle отсутствует, но есть цена - используем как текущую
                                current_price = price_value
                    
                    # Также проверяем прямые поля в price_v2
                    if current_price is None:
                        # Пробуем извлечь из поля "price" напрямую
                        direct_price = price_v2.get("price")
                        if isinstance(direct_price, (int, float)):
                            current_price = float(direct_price)
                        elif isinstance(direct_price, str):
                            try:
                                current_price = float(direct_price.replace(" ", "").replace("₽", "").replace("\u00A0", ""))
                            except:
                                pass
                    
                    if original_price is None:
                        # Пробуем извлечь из поля "originalPrice" или "oldPrice"
                        original_price_val = price_v2.get("originalPrice") or price_v2.get("oldPrice")
                        if isinstance(original_price_val, (int, float)):
                            original_price = float(original_price_val)
                        elif isinstance(original_price_val, str):
                            try:
                                original_price = float(original_price_val.replace(" ", "").replace("₽", "").replace("\u00A0", ""))
                            except:
                                pass
                    
                    # Извлекаем процент скидки
                    discount_text = price_v2.get("discount", "")
                    if discount_text:
                        # Извлекаем числовое значение из "−68%" или "-68%"
                        discount_value = discount_text.replace("−", "-").replace("%", "").replace(" ", "").strip()
                        try:
                            discount_percent = abs(float(discount_value))  # Берем абсолютное значение
                        except:
                            pass
                    
                    # Если нашли хотя бы одну цену, выходим
                    if current_price is not None or original_price is not None:
                        break
                
                # Формат 2: price (альтернативный формат)
                elif state_type == "price":
                    price_data = state.get("price", {})
                    if isinstance(price_data, dict):
                        # Пробуем извлечь цену из разных полей
                        if current_price is None:
                            price_val = price_data.get("value") or price_data.get("price") or price_data.get("current")
                            if isinstance(price_val, (int, float)):
                                current_price = float(price_val)
                            elif isinstance(price_val, str):
                                try:
                                    current_price = float(price_val.replace(" ", "").replace("₽", "").replace("\u00A0", ""))
                                except:
                                    pass
                        
                        if original_price is None:
                            original_val = price_data.get("original") or price_data.get("old") or price_data.get("originalPrice")
                            if isinstance(original_val, (int, float)):
                                original_price = float(original_val)
                            elif isinstance(original_val, str):
                                try:
                                    original_price = float(original_val.replace(" ", "").replace("₽", "").replace("\u00A0", ""))
                                except:
                                    pass
            
            # Если не нашли цены в mainState, проверяем другие места в item
            if current_price is None or original_price is None:
                # Проверяем прямые поля в item
                if current_price is None:
                    item_price = item.get("price") or item.get("currentPrice")
                    if isinstance(item_price, (int, float)):
                        current_price = float(item_price)
                    elif isinstance(item_price, str):
                        try:
                            current_price = float(item_price.replace(" ", "").replace("₽", "").replace("\u00A0", ""))
                        except:
                            pass
                
                if original_price is None:
                    item_original = item.get("originalPrice") or item.get("oldPrice") or item.get("priceOriginal")
                    if isinstance(item_original, (int, float)):
                        original_price = float(item_original)
                    elif isinstance(item_original, str):
                        try:
                            original_price = float(item_original.replace(" ", "").replace("₽", "").replace("\u00A0", ""))
                        except:
                            pass
            
            # Логируем товары без цен для диагностики (кратко)
            if current_price is None:
                state_types = [s.get('type') for s in main_state]
                logger.debug(f"  ⚠️ SKU {sku}: нет цены покупателя, типы states: {state_types}")
            
            if original_price is None and current_price is not None:
                # Если есть текущая цена, но нет зачёркнутой - это нормально (нет скидки)
                pass
            elif original_price is None and current_price is None:
                logger.debug(f"  ⚠️ SKU {sku}: нет ни одной цены")
            
            # Вычисляем скидку, если она не найдена, но есть обе цены
            if discount_percent is None and current_price is not None and original_price is not None:
                if original_price > 0 and original_price > current_price:
                    discount_percent = round(((original_price - current_price) / original_price) * 100, 1)
                    logger.debug(f"  ✓ SKU {sku}: скидка вычислена: {discount_percent}% ({original_price} → {current_price})")
            
            result = {
                "sku": sku,
                "product_name": product_name,
                "current_price": current_price,
                "original_price": original_price,
                "discount_percent": discount_percent,
                "source": "catalog_api"
            }
            
            # Добавляем offer_id если нашли
            if offer_id:
                result["offer_id"] = offer_id
                logger.debug(f"  ✓ SKU {sku}: найден offer_id={offer_id} в публичном API")
            else:
                # Логируем структуру item для диагностики (только для первого товара)
                logger.debug(f"  ⚠️ SKU {sku}: offer_id не найден в публичном API. Доступные ключи: {list(item.keys())[:20]}")
            
            return result
            
        except Exception as e:
            logger.debug(f"Ошибка при парсинге товара: {e}")
            logger.debug(f"Детали ошибки:", exc_info=True)
            return None
