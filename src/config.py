"""Централизованная конфигурация для парсера Ozon.

Вместо прямого чтения .env в каждом модуле, используется единый класс OzonConfig.
"""
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from pathlib import Path


class Mode(Enum):
    """Режим работы парсера."""
    LIGHT = "light"  # HTTP-only, без Playwright (для хостинга)
    FULL = "full"    # С Playwright fallback (для локального ПК)


class AccountType(Enum):
    """Тип аккаунта для Seller API."""
    MY = "my"        # Свой кабинет (Seller API работает)
    FOREIGN = "foreign"  # Чужой продавец (Seller API пропускается)


@dataclass
class OzonConfig:
    """Централизованная конфигурация для парсера Ozon.
    
    Все параметры читаются из .env или имеют значения по умолчанию.
    """
    # Режим работы
    mode: Mode = field(default_factory=lambda: Mode(os.getenv('OZON_MODE', 'full').lower().strip() or 'full'))
    
    # Seller API credentials
    client_id: int = field(default_factory=lambda: int(os.getenv('OZON_CLIENT_ID', '0')))
    api_key: str = field(default_factory=lambda: os.getenv('OZON_API_KEY', ''))
    
    # Продавец для парсинга
    seller_id: int = field(default_factory=lambda: int(os.getenv('OZON_SELLER_ID_COSMO', '176640')))
    seller_name: str = field(default_factory=lambda: os.getenv('OZON_SELLER_NAME_COSMO', 'cosmo-beauty'))
    
    # Тип аккаунта
    account_type: AccountType = field(default_factory=lambda: AccountType(os.getenv('OZON_ACCOUNT_TYPE', 'foreign').lower().strip() or 'foreign'))
    
    # Cookies
    cookies: Optional[str] = field(default_factory=lambda: os.getenv('OZON_COOKIES'))
    cookies_path: Optional[str] = field(default_factory=lambda: os.getenv('OZON_COOKIES_PATH', 'cookies/ozon_cookies.json'))
    
    # Параметры запросов
    request_delay: float = field(default_factory=lambda: float(os.getenv('OZON_CATALOG_REQUEST_DELAY', '1.0')))
    max_concurrent: int = field(default_factory=lambda: int(os.getenv('OZON_CATALOG_MAX_CONCURRENT', '3')))
    seller_request_delay: float = field(default_factory=lambda: float(os.getenv('OZON_SELLER_REQUEST_DELAY', '0.5')))
    
    # Адаптивные задержки
    adaptive_delay: bool = field(default_factory=lambda: os.getenv('OZON_ADAPTIVE_DELAY', 'true').lower() in ('true', '1', 'yes'))
    
    # Playwright
    playwright_headless: bool = field(default_factory=lambda: os.getenv('OZON_PLAYWRIGHT_HEADLESS', 'true').lower() in ('true', '1', 'yes'))
    
    # Прокси
    proxy: Optional[str] = field(default_factory=lambda: os.getenv('OZON_PROXY') or None)
    
    # Кэш
    cache_enabled: bool = field(default_factory=lambda: os.getenv('OZON_CACHE_ENABLED', 'false').lower() in ('true', '1', 'yes'))
    cache_ttl: int = field(default_factory=lambda: int(os.getenv('OZON_CACHE_TTL', '86400')))  # 24 часа
    
    def validate(self) -> bool:
        """Валидирует конфигурацию.
        
        Returns:
            True если конфигурация валидна, False если есть ошибки
        """
        errors = []
        
        if not self.client_id or self.client_id == 0:
            errors.append("OZON_CLIENT_ID не установлен или равен 0")
        
        if not self.api_key:
            errors.append("OZON_API_KEY не установлен")
        
        if not self.seller_id or self.seller_id == 0:
            errors.append("OZON_SELLER_ID_COSMO не установлен или равен 0")
        
        if not self.seller_name:
            errors.append("OZON_SELLER_NAME_COSMO не установлен")
        
        if errors:
            from loguru import logger
            for error in errors:
                logger.error(f"❌ Ошибка конфигурации: {error}")
            return False
        
        return True
    
    def get_cookies_path(self) -> Optional[Path]:
        """Возвращает путь к файлу cookies, если он существует.
        
        Returns:
            Path к файлу cookies или None
        """
        if not self.cookies_path:
            return None
        
        cookies_path = Path(self.cookies_path)
        if cookies_path.exists():
            return cookies_path
        
        # Пробуем относительный путь от корня проекта
        project_root = Path(__file__).parent.parent
        cookies_path = project_root / self.cookies_path
        if cookies_path.exists():
            return cookies_path
        
        return None


def load_config() -> OzonConfig:
    """Загружает конфигурацию из .env.
    
    Returns:
        OzonConfig с параметрами из .env
    """
    config = OzonConfig()
    
    # Валидация
    if not config.validate():
        raise ValueError("Неверная конфигурация. Проверьте .env файл.")
    
    return config
