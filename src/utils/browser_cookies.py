"""Модуль для автоматического получения cookies из браузера Chrome."""
import os
import platform
import sqlite3
import shutil
import tempfile
from pathlib import Path
from typing import Dict, Optional
from loguru import logger


class BrowserCookiesExtractor:
    """Класс для извлечения cookies из браузера Chrome."""
    
    # Важные cookies для Wildberries
    REQUIRED_COOKIES = [
        "wbx-validation-key",
        "_cp",
        "routeb",
        "x_wbaas_token",
        "_wbauid"
    ]
    
    def __init__(self, browser: str = "chrome", profile: str = "Default"):
        """Инициализация экстрактора cookies.
        
        Args:
            browser: Браузер для использования ("chrome" или "edge")
            profile: Название профиля браузера (по умолчанию "Default")
        """
        self.browser = browser.lower()
        self.profile = profile
        self._chrome_path = self._find_chrome_path()
        self._cookies_db_path = None
    
    def _find_chrome_path(self) -> Optional[Path]:
        """Находит путь к папке с данными Chrome."""
        system = platform.system()
        home = Path.home()
        
        if system == "Windows":
            # Windows пути для Chrome - проверяем несколько вариантов
            username = os.getenv("USERNAME", "")
            possible_paths = [
                home / "AppData" / "Local" / "Google" / "Chrome" / "User Data",
                Path(f"C:/Users/{username}/AppData/Local/Google/Chrome/User Data") if username else None,
                Path(os.getenv("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data" if os.getenv("LOCALAPPDATA") else None,
            ]
            # Убираем None значения
            possible_paths = [p for p in possible_paths if p is not None]
        elif system == "Darwin":  # macOS
            possible_paths = [
                home / "Library" / "Application Support" / "Google" / "Chrome",
            ]
        else:  # Linux
            possible_paths = [
                home / ".config" / "google-chrome",
                home / ".config" / "chromium",
            ]
        
        # Сначала проверяем указанный профиль
        for path in possible_paths:
            if path.exists():
                cookies_path = path / self.profile / "Cookies"
                if cookies_path.exists():
                    logger.debug(f"Найден путь к Chrome: {path} (профиль: {self.profile})")
                    return path
        
        # Если не нашли с указанным профилем, пробуем найти любой профиль
        for path in possible_paths:
            if path.exists():
                # Ищем все подпапки (профили)
                try:
                    profiles_found = []
                    all_profiles = []
                    
                    # Сначала проверяем известные профили
                    known_profiles = ["Default", "Profile 1", "Profile 2", "Profile 3", "Profile 4"]
                    for profile_name in known_profiles:
                        profile_path = path / profile_name
                        if profile_path.exists() and profile_path.is_dir():
                            all_profiles.append(profile_name)
                            cookies_path = profile_path / "Cookies"
                            if cookies_path.exists():
                                profiles_found.append(profile_name)
                                logger.info(f"Найден путь к Chrome: {path} (профиль: {profile_name})")
                                self.profile = profile_name
                                return path
                    
                    # Если не нашли в известных, ищем все папки
                    for item in path.iterdir():
                        if item.is_dir() and not item.name.startswith('.') and item.name not in known_profiles:
                            # Пропускаем системные папки
                            if item.name in ["System Profile", "Guest Profile", "Crash Reports", "ShaderCache"]:
                                continue
                            all_profiles.append(item.name)
                            cookies_path = item / "Cookies"
                            if cookies_path.exists():
                                profiles_found.append(item.name)
                                logger.info(f"Найден путь к Chrome: {path} (профиль: {item.name})")
                                self.profile = item.name
                                return path
                    
                    # Если нашли профили, но без файла Cookies (возможно заблокирован Chrome)
                    if all_profiles:
                        logger.debug(f"Найдены профили: {all_profiles}, но файл Cookies не доступен (возможно Chrome запущен)")
                        # Пробуем использовать первый профиль все равно (попробуем скопировать позже)
                        logger.info(f"Пробуем использовать профиль: {all_profiles[0]} (файл может быть заблокирован)")
                        self.profile = all_profiles[0]
                        return path
                    elif profiles_found:
                        # Если нашли профили с cookies, но не смогли вернуть (не должно быть)
                        logger.info(f"Используем профиль: {profiles_found[0]}")
                        self.profile = profiles_found[0]
                        return path
                        
                except PermissionError:
                    logger.debug(f"Нет доступа к {path}")
                    continue
                except Exception as e:
                    logger.debug(f"Ошибка при поиске профилей в {path}: {e}")
                    continue
        
        logger.warning("Не удалось найти путь к Chrome автоматически")
        logger.debug(f"Проверенные пути: {possible_paths}")
        return None
    
    def _get_cookies_db_path(self) -> Optional[Path]:
        """Получает путь к базе данных cookies."""
        if not self._chrome_path:
            return None
        
        cookies_path = self._chrome_path / self.profile / "Cookies"
        
        if not cookies_path.exists():
            logger.debug(f"Файл cookies не найден: {cookies_path} (возможно Chrome не запускался на этом домене)")
            # Возвращаем None, чтобы не пытаться копировать несуществующий файл
            return None
        
        # Проверяем, доступен ли файл для чтения
        try:
            with open(cookies_path, 'rb'):
                pass
        except PermissionError:
            logger.debug(f"Файл cookies заблокирован: {cookies_path} (Chrome запущен)")
            # Возвращаем путь все равно - попробуем скопировать
            return cookies_path
        except Exception as e:
            logger.debug(f"Ошибка при проверке файла cookies: {e}")
            return cookies_path
        
        return cookies_path
    
    def _copy_cookies_db(self) -> Optional[Path]:
        """Копирует базу данных cookies во временную папку для чтения.
        
        Chrome блокирует файл Cookies во время работы, поэтому нужно скопировать.
        Пробует несколько методов копирования для обхода блокировки.
        """
        cookies_path = self._get_cookies_db_path()
        if not cookies_path:
            return None
        
        # Пробуем несколько методов копирования
        methods = [
            ("shutil.copy2", lambda: self._copy_with_shutil(cookies_path)),
            ("Windows CopyFile", lambda: self._copy_with_windows(cookies_path)),
            ("чтение-запись", lambda: self._copy_with_readwrite(cookies_path)),
        ]
        
        for method_name, copy_func in methods:
            try:
                temp_cookies = copy_func()
                if temp_cookies and temp_cookies.exists():
                    logger.debug(f"Скопирована база cookies методом {method_name}: {temp_cookies}")
                    return temp_cookies
            except Exception as e:
                logger.debug(f"Метод {method_name} не сработал: {e}")
                continue
        
        logger.warning(f"Не удалось скопировать файл Cookies: {cookies_path}")
        return None
    
    def _copy_with_shutil(self, cookies_path: Path) -> Optional[Path]:
        """Копирование через shutil.copy2 (стандартный метод)."""
        temp_dir = tempfile.mkdtemp()
        temp_cookies = Path(temp_dir) / "Cookies"
        shutil.copy2(cookies_path, temp_cookies)
        return temp_cookies
    
    def _copy_with_windows(self, cookies_path: Path) -> Optional[Path]:
        """Копирование через Windows API (для обхода блокировки)."""
        if platform.system() != "Windows":
            return None
        
        try:
            import win32file
            import win32con
            
            temp_dir = tempfile.mkdtemp()
            temp_cookies = Path(temp_dir) / "Cookies"
            
            # Пробуем скопировать через Windows API
            win32file.CopyFile(
                str(cookies_path),
                str(temp_cookies),
                False  # failIfExists
            )
            return temp_cookies
        except ImportError:
            # pywin32 не установлен
            return None
        except Exception:
            return None
    
    def _copy_with_readwrite(self, cookies_path: Path) -> Optional[Path]:
        """Копирование через чтение-запись (для обхода блокировки)."""
        try:
            temp_dir = tempfile.mkdtemp()
            temp_cookies = Path(temp_dir) / "Cookies"
            
            # Пробуем открыть файл в режиме чтения (даже если заблокирован)
            with open(cookies_path, 'rb') as src:
                with open(temp_cookies, 'wb') as dst:
                    # Копируем по частям
                    while True:
                        chunk = src.read(8192)
                        if not chunk:
                            break
                        dst.write(chunk)
            
            return temp_cookies
        except Exception:
            return None
    
    def _decrypt_cookie_value(self, encrypted_value: bytes) -> str:
        """Расшифровывает значение cookie из Chrome.
        
        В Windows Chrome использует Windows Data Protection API (DPAPI).
        В macOS/Linux используется ключ из Keychain.
        
        Args:
            encrypted_value: Зашифрованное значение cookie
            
        Returns:
            Расшифрованное значение или пустая строка
        """
        try:
            if platform.system() == "Windows":
                try:
                    import win32crypt
                    # Пробуем расшифровать через DPAPI
                    try:
                        decrypted = win32crypt.CryptUnprotectData(
                            encrypted_value, None, None, None, 0
                        )
                        return decrypted[1].decode('utf-8')
                    except Exception:
                        # Если не получилось, возвращаем как есть (может быть уже расшифровано)
                        try:
                            return encrypted_value.decode('utf-8')
                        except:
                            return ""
                except ImportError:
                    # pywin32 не установлен, пробуем как есть
                    try:
                        return encrypted_value.decode('utf-8')
                    except:
                        return ""
            else:
                # Для macOS/Linux нужен ключ из Keychain
                # Пока возвращаем как есть
                try:
                    return encrypted_value.decode('utf-8')
                except:
                    return ""
        except Exception as e:
            logger.debug(f"Ошибка расшифровки cookie: {e}")
            try:
                return encrypted_value.decode('utf-8')
            except:
                return ""
    
    def extract_cookies_from_db(self, domain: str = "wildberries.ru") -> Dict[str, str]:
        """Извлекает cookies из базы данных Chrome.
        
        Args:
            domain: Домен для фильтрации cookies
            
        Returns:
            Словарь с cookies {name: value}
        """
        cookies = {}
        temp_db = None
        
        try:
            temp_db = self._copy_cookies_db()
            if not temp_db:
                return cookies
            
            # Подключаемся к SQLite базе
            conn = sqlite3.connect(str(temp_db))
            cursor = conn.cursor()
            
            # Запрос для получения cookies для домена
            query = """
                SELECT name, value, encrypted_value, host_key
                FROM cookies
                WHERE host_key LIKE ? OR host_key LIKE ?
                ORDER BY creation_utc DESC
            """
            
            cursor.execute(query, (f"%{domain}", f".{domain}"))
            rows = cursor.fetchall()
            
            for name, value, encrypted_value, host_key in rows:
                # Пробуем использовать обычное значение, если оно есть
                if value:
                    cookie_value = value
                elif encrypted_value:
                    # Пробуем расшифровать
                    cookie_value = self._decrypt_cookie_value(encrypted_value)
                else:
                    continue
                
                if cookie_value and name:
                    cookies[name] = cookie_value
                    logger.debug(f"Извлечен cookie: {name} для {host_key}")
            
            conn.close()
            
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e).lower():
                logger.warning("База данных cookies заблокирована Chrome. Попробуем еще раз...")
                # Пробуем еще раз через небольшую задержку
                import time
                time.sleep(0.5)
                try:
                    temp_db2 = self._copy_cookies_db()
                    if temp_db2:
                        conn = sqlite3.connect(str(temp_db2))
                        cursor = conn.cursor()
                        cursor.execute(query, (f"%{domain}", f".{domain}"))
                        rows = cursor.fetchall()
                        for name, value, encrypted_value, host_key in rows:
                            if value:
                                cookie_value = value
                            elif encrypted_value:
                                cookie_value = self._decrypt_cookie_value(encrypted_value)
                            else:
                                continue
                            if cookie_value and name:
                                cookies[name] = cookie_value
                        conn.close()
                        logger.info("Успешно прочитали cookies после повторной попытки")
                except Exception as retry_e:
                    logger.warning(f"Повторная попытка не удалась: {retry_e}. Используйте headless режим или закройте Chrome.")
            else:
                logger.error(f"Ошибка SQLite: {e}")
        except Exception as e:
            logger.error(f"Ошибка при извлечении cookies из базы: {e}")
            logger.debug("Детали ошибки:", exc_info=True)
        finally:
            # Удаляем временную копию
            if temp_db and temp_db.exists():
                try:
                    temp_db.unlink()
                    temp_db.parent.rmdir()
                except:
                    pass
        
        return cookies
    
    def extract_cookies_headless(self, domain: str = "wildberries.ru") -> Dict[str, str]:
        """Извлекает cookies используя headless Chrome через Selenium.
        
        Args:
            domain: Домен для получения cookies
            
        Returns:
            Словарь с cookies {name: value}
        """
        cookies = {}
        
        try:
            import undetected_chromedriver as uc
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            
            logger.info("Запуск headless Chrome для получения cookies...")
            
            options = uc.ChromeOptions()
            options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-blink-features=AutomationControlled")
            # Убрали excludeSwitches - вызывает проблемы совместимости
            # options.add_experimental_option("excludeSwitches", ["enable-automation"])
            # options.add_experimental_option('useAutomationExtension', False)
            
            # Используем профиль Chrome только если файл Cookies существует
            # Если файла нет, создаем новую сессию без профиля
            cookies_path = self._get_cookies_db_path()
            use_profile = cookies_path and cookies_path.exists()
            temp_user_data = None  # Для очистки в finally
            
            if use_profile and self._chrome_path:
                # Используем существующий профиль (быстрее, если cookies есть)
                user_data_dir = str(self._chrome_path)
                options.add_argument(f"--user-data-dir={user_data_dir}")
                options.add_argument(f"--profile-directory={self.profile}")
                logger.debug("Используем существующий профиль Chrome")
            else:
                # Создаем новую сессию без профиля (для получения cookies)
                temp_user_data = tempfile.mkdtemp(prefix="chrome_headless_")
                options.add_argument(f"--user-data-dir={temp_user_data}")
                logger.info("Создаем новую сессию Chrome (файл Cookies не найден)")
            
            # Дополнительные опции для стабильности
            options.add_argument("--disable-gpu")
            options.add_argument("--disable-software-rasterizer")
            options.add_argument("--disable-extensions")
            
            # Пробуем запустить Chrome с несколькими попытками
            driver = None
            max_retries = 2
            
            for attempt in range(max_retries):
                try:
                    if attempt > 0:
                        # При повторной попытке используем другую временную папку
                        if not use_profile:
                            # Удаляем старую временную папку
                            if temp_user_data and Path(temp_user_data).exists():
                                try:
                                    import shutil
                                    shutil.rmtree(temp_user_data, ignore_errors=True)
                                except:
                                    pass
                            temp_user_data = tempfile.mkdtemp(prefix="chrome_headless_")
                            # Обновляем опции
                            options = uc.ChromeOptions()
                            options.add_argument("--headless=new")
                            options.add_argument("--no-sandbox")
                            options.add_argument("--disable-dev-shm-usage")
                            options.add_argument("--disable-blink-features=AutomationControlled")
                            options.add_argument("--disable-gpu")
                            options.add_argument(f"--user-data-dir={temp_user_data}")
                        logger.debug(f"Повторная попытка запуска Chrome (попытка {attempt + 1}/{max_retries})")
                    
                    driver = uc.Chrome(options=options, version_main=None)
                    break  # Успешно запустили
                    
                except Exception as e:
                    error_msg = str(e).lower()
                    if "cannot connect" in error_msg or "chrome not reachable" in error_msg:
                        if attempt < max_retries - 1:
                            logger.debug(f"Chrome не может подключиться, пробуем еще раз...")
                            import time
                            time.sleep(1)
                            continue
                        else:
                            # Последняя попытка - пробуем без профиля
                            if use_profile:
                                logger.info("Пробуем запустить Chrome без профиля (новая сессия)...")
                                # Очищаем старую временную папку если была
                                if temp_user_data and Path(temp_user_data).exists():
                                    try:
                                        import shutil
                                        shutil.rmtree(temp_user_data, ignore_errors=True)
                                    except:
                                        pass
                                options = uc.ChromeOptions()
                                options.add_argument("--headless=new")
                                options.add_argument("--no-sandbox")
                                options.add_argument("--disable-dev-shm-usage")
                                options.add_argument("--disable-blink-features=AutomationControlled")
                                options.add_argument("--disable-gpu")
                                temp_user_data = tempfile.mkdtemp(prefix="chrome_headless_")
                                options.add_argument(f"--user-data-dir={temp_user_data}")
                                use_profile = False  # Теперь используем временную папку
                                try:
                                    driver = uc.Chrome(options=options, version_main=None)
                                    break
                                except:
                                    raise e
                            else:
                                raise e
                    else:
                        raise e
            
            if not driver:
                raise Exception("Не удалось запустить Chrome после всех попыток")
            
            try:
                # Для Ozon открываем главную страницу и страницу продавца
                if "ozon.ru" in domain:
                    # Шаг 1: Открываем главную страницу
                    main_url = f"https://www.{domain}"
                    logger.debug(f"Открываем главную страницу {main_url} в headless Chrome...")
                    driver.get(main_url)
                    
                    # Ждем загрузки страницы
                    WebDriverWait(driver, 20).until(
                        EC.presence_of_element_located((By.TAG_NAME, "body"))
                    )
                    
                    import time
                    logger.debug("Ожидаем полной загрузки главной страницы и установки cookies...")
                    
                    # Ждем полной загрузки страницы (включая JS)
                    for i in range(10):  # Максимум 10 секунд
                        ready_state = driver.execute_script("return document.readyState")
                        if ready_state == "complete":
                            logger.debug(f"  • Страница загружена (readyState: {ready_state})")
                            break
                        time.sleep(1)
                    
                    time.sleep(5)  # Дополнительная задержка для установки cookies через JS
                    
                    # Прокручиваем страницу для запуска дополнительных скриптов
                    try:
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
                        time.sleep(2)
                        driver.execute_script("window.scrollTo(0, 0);")
                        time.sleep(2)
                    except:
                        pass
                    
                    # Шаг 2: Открываем страницу продавца для получения специфичных cookies
                    seller_url = "https://www.ozon.ru/seller/cosmo-beauty-176640/"
                    logger.debug(f"Открываем страницу продавца {seller_url} для получения дополнительных cookies...")
                    driver.get(seller_url)
                    
                    # Ждем загрузки страницы продавца
                    WebDriverWait(driver, 20).until(
                        EC.presence_of_element_located((By.TAG_NAME, "body"))
                    )
                    
                    logger.debug("Ожидаем полной загрузки страницы продавца и установки cookies...")
                    
                    # Ждем полной загрузки страницы продавца (включая JS)
                    for i in range(10):  # Максимум 10 секунд
                        ready_state = driver.execute_script("return document.readyState")
                        if ready_state == "complete":
                            logger.debug(f"  • Страница продавца загружена (readyState: {ready_state})")
                            break
                        time.sleep(1)
                    
                    time.sleep(5)  # Дополнительная задержка для установки cookies через JS
                    
                    # Прокручиваем страницу продавца
                    try:
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight/3);")
                        time.sleep(2)
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight*2/3);")
                        time.sleep(2)
                        driver.execute_script("window.scrollTo(0, 0);")
                        time.sleep(2)
                    except:
                        pass
                else:
                    # Для других доменов (WB) - обычная логика
                    url = f"https://www.{domain}"
                    logger.debug(f"Открываем {url} в headless Chrome...")
                    driver.get(url)
                    
                    WebDriverWait(driver, 20).until(
                        EC.presence_of_element_located((By.TAG_NAME, "body"))
                    )
                    
                    import time
                    logger.debug("Ожидаем полной загрузки страницы и установки cookies...")
                    time.sleep(3)
                    
                    try:
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
                        time.sleep(2)
                        driver.execute_script("window.scrollTo(0, 0);")
                        time.sleep(2)
                    except:
                        pass
                
                # Получаем все cookies после всех действий
                selenium_cookies = driver.get_cookies()
                logger.debug(f"🔍 ДИАГНОСТИКА: Получение cookies через Selenium:")
                logger.debug(f"  • Всего cookies от Selenium: {len(selenium_cookies)}")
                
                # Логируем все cookies от Selenium
                all_selenium_cookies = {}
                for cookie in selenium_cookies:
                    cookie_name = cookie.get("name", "")
                    cookie_domain = cookie.get("domain", "")
                    cookie_value = cookie.get("value", "")
                    all_selenium_cookies[cookie_name] = {
                        "domain": cookie_domain,
                        "value_length": len(cookie_value),
                        "value_preview": cookie_value[:50] + "..." if len(cookie_value) > 50 else cookie_value
                    }
                    logger.debug(f"  • Cookie от Selenium: {cookie_name} (домен: {cookie_domain}, длина значения: {len(cookie_value)})")
                
                # Фильтруем cookies по домену
                for cookie in selenium_cookies:
                    cookie_domain = cookie.get("domain", "")
                    # Проверяем домен (может быть с точкой в начале или без)
                    if domain in cookie_domain or cookie_domain.lstrip('.') == domain or cookie_domain == '':
                        cookies[cookie["name"]] = cookie["value"]
                        logger.debug(f"  • Принят cookie: {cookie['name']} (домен: {cookie_domain})")
                    else:
                        logger.debug(f"  • Отклонен cookie: {cookie['name']} (домен: {cookie_domain} не подходит для {domain})")
                
                logger.debug(f"  • Всего принято cookies для {domain}: {len(cookies)}")
                
                if cookies:
                    cookie_names = list(cookies.keys())
                    logger.info(f"✅ Успешно получено {len(cookies)} cookies для {domain}: {', '.join(cookie_names[:10])}{'...' if len(cookie_names) > 10 else ''}")
                    logger.debug(f"  • Все cookies: {cookie_names}")
                else:
                    logger.warning(f"⚠️ Не получено cookies для {domain} (возможно антибот-защита)")
                    logger.warning(f"  • Все cookies от Selenium: {list(all_selenium_cookies.keys())}")
                
            finally:
                if driver:
                    try:
                        driver.quit()
                    except:
                        pass
                
                # Очищаем временную папку если создавали
                if temp_user_data and Path(temp_user_data).exists():
                    try:
                        import shutil
                        shutil.rmtree(temp_user_data, ignore_errors=True)
                    except:
                        pass
                
        except ImportError:
            logger.warning("undetected-chromedriver не установлен. Установите: python -m pip install undetected-chromedriver selenium")
        except Exception as e:
            error_msg = str(e)
            # Не логируем как ошибку, если это известные проблемы
            if "excludeSwitches" in error_msg or "chrome option" in error_msg.lower():
                logger.debug(f"Проблема совместимости headless Chrome: {e}")
            elif "Remote end closed" in error_msg or "connection" in error_msg.lower():
                logger.debug(f"Проблема подключения к Chrome: {e}")
            else:
                logger.warning(f"Ошибка при получении cookies через headless Chrome: {e}")
            logger.debug("Детали ошибки:", exc_info=True)
        
        return cookies
    
    def get_cookies(self, domain: str = "wildberries.ru", use_headless: bool = True) -> Dict[str, str]:
        """Получает cookies из браузера.
        
        Сначала пытается прочитать из базы данных, если не получается - использует headless режим.
        
        Args:
            domain: Домен для получения cookies
            use_headless: Использовать headless Chrome если чтение из БД не удалось
            
        Returns:
            Словарь с cookies {name: value}
        """
        logger.info(f"Попытка извлечения cookies для {domain}...")
        
        # Сначала пробуем прочитать из базы данных (быстрее)
        cookies = self.extract_cookies_from_db(domain)
        
        # Проверяем наличие важных cookies только для Wildberries
        if "wildberries.ru" in domain:
            found_required = [c for c in self.REQUIRED_COOKIES if c in cookies]
            missing_required = [c for c in self.REQUIRED_COOKIES if c not in cookies]
            
            if found_required:
                logger.info(f"✓ Найдены важные cookies из БД: {', '.join(found_required)}")
            
            if missing_required and use_headless:
                logger.warning(f"⚠ Отсутствуют cookies из БД: {', '.join(missing_required)}")
                logger.info("Попытка получить через headless Chrome...")
                
                # Пробуем получить через headless Chrome
                headless_cookies = self.extract_cookies_headless(domain)
                
                # Объединяем cookies (headless имеет приоритет)
                cookies.update(headless_cookies)
                
                # Проверяем снова
                found_after = [c for c in self.REQUIRED_COOKIES if c in cookies]
                if found_after:
                    logger.info(f"✓ После headless получены: {', '.join(found_after)}")
        else:
            # Для других доменов (Ozon и т.д.) просто пробуем получить любые cookies
            if not cookies and use_headless:
                logger.info("Cookies из БД не найдены, попытка получить через headless Chrome...")
                headless_cookies = self.extract_cookies_headless(domain)
                cookies.update(headless_cookies)
        
        if not cookies:
            logger.error("Не удалось получить cookies ни одним способом")
        else:
            logger.success(f"Получено {len(cookies)} cookies для {domain}")
        
        return cookies
    
    def format_cookies_string(self, cookies: Dict[str, str]) -> str:
        """Форматирует cookies в строку для использования в заголовках.
        
        Args:
            cookies: Словарь с cookies
            
        Returns:
            Строка в формате "name1=value1; name2=value2"
        """
        return "; ".join([f"{name}={value}" for name, value in cookies.items()])


def get_wb_cookies(use_headless: bool = True) -> Optional[str]:
    """Удобная функция для получения cookies Wildberries.
    
    Args:
        use_headless: Использовать headless Chrome если чтение из БД не удалось
        
    Returns:
        Строка с cookies в формате "name1=value1; name2=value2" или None
    """
    extractor = BrowserCookiesExtractor()
    cookies = extractor.get_cookies(domain="wildberries.ru", use_headless=use_headless)
    
    if cookies:
        return extractor.format_cookies_string(cookies)
    
    return None


def get_ozon_cookies(use_headless: bool = True) -> Optional[str]:
    """Удобная функция для получения cookies Ozon.
    
    Args:
        use_headless: Использовать headless Chrome если чтение из БД не удалось
        
    Returns:
        Строка с cookies в формате "name1=value1; name2=value2" или None
    """
    extractor = BrowserCookiesExtractor()
    cookies = extractor.get_cookies(domain="ozon.ru", use_headless=use_headless)
    
    if cookies:
        return extractor.format_cookies_string(cookies)
    
    return None