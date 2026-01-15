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
                    for item in path.iterdir():
                        if item.is_dir() and not item.name.startswith('.'):
                            cookies_path = item / "Cookies"
                            if cookies_path.exists():
                                logger.info(f"Найден путь к Chrome: {path} (профиль: {item.name})")
                                self.profile = item.name  # Обновляем профиль
                                return path
                except PermissionError:
                    logger.debug(f"Нет доступа к {path}")
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
            logger.warning(f"Файл cookies не найден: {cookies_path}")
            return None
        
        return cookies_path
    
    def _copy_cookies_db(self) -> Optional[Path]:
        """Копирует базу данных cookies во временную папку для чтения.
        
        Chrome блокирует файл Cookies во время работы, поэтому нужно скопировать.
        """
        cookies_path = self._get_cookies_db_path()
        if not cookies_path:
            return None
        
        try:
            # Создаем временную копию
            temp_dir = tempfile.mkdtemp()
            temp_cookies = Path(temp_dir) / "Cookies"
            shutil.copy2(cookies_path, temp_cookies)
            logger.debug(f"Скопирована база cookies во временную папку: {temp_cookies}")
            return temp_cookies
        except Exception as e:
            logger.error(f"Ошибка при копировании базы cookies: {e}")
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
                logger.warning("База данных cookies заблокирована Chrome. Закройте браузер или используйте headless режим.")
            else:
                logger.error(f"Ошибка SQLite: {e}")
        except Exception as e:
            logger.error(f"Ошибка при извлечении cookies из базы: {e}")
            logger.exception("Детали ошибки:")
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
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)
            
            # Используем профиль Chrome если доступен
            # _chrome_path уже указывает на папку "User Data" (например, C:\Users\...\Chrome\User Data)
            # Для --user-data-dir нужно передать этот путь напрямую, без .parent
            if self._chrome_path:
                user_data_dir = str(self._chrome_path)
                options.add_argument(f"--user-data-dir={user_data_dir}")
                options.add_argument(f"--profile-directory={self.profile}")
            
            driver = uc.Chrome(options=options, version_main=None)
            
            try:
                # Открываем сайт Wildberries
                url = f"https://www.{domain}"
                driver.get(url)
                
                # Ждем загрузки страницы
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                
                # Небольшая задержка для получения cookies
                import time
                time.sleep(3)
                
                # Получаем все cookies
                selenium_cookies = driver.get_cookies()
                
                for cookie in selenium_cookies:
                    if domain in cookie.get("domain", ""):
                        cookies[cookie["name"]] = cookie["value"]
                        logger.debug(f"Получен cookie через Selenium: {cookie['name']}")
                
            finally:
                driver.quit()
                
        except ImportError:
            logger.error("undetected-chromedriver не установлен. Установите: python -m pip install undetected-chromedriver")
        except Exception as e:
            logger.error(f"Ошибка при получении cookies через headless Chrome: {e}")
            logger.exception("Детали ошибки:")
        
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
        
        # Проверяем наличие важных cookies
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