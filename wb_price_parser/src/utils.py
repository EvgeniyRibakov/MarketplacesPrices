"""
Вспомогательные функции для парсера цен Wildberries
"""
import re
import logging
from typing import Optional, Dict, Any
from pathlib import Path
from datetime import datetime


def convert_price_to_rubles(price_kopecks: int) -> float:
    """
    Конвертирует цену из копеек в рубли
    
    Args:
        price_kopecks: Цена в копейках (например, 43200)
    
    Returns:
        Цена в рублях как float (например, 432.00)
    """
    if price_kopecks is None:
        return None
    return float(price_kopecks) / 100.0


def sanitize_for_logging(text: str, secrets: Optional[list] = None) -> str:
    """
    Удаляет секретные данные из строки для логирования
    
    Args:
        text: Текст для очистки
        secrets: Список секретов для замены (API ключи и т.д.)
    
    Returns:
        Очищенный текст
    """
    if secrets:
        for secret in secrets:
            if secret:
                text = text.replace(secret, "***REDACTED***")
    
    # Удаляем возможные API ключи в формате WB_API_KEY_*=...
    text = re.sub(r'WB_API_KEY_\w+=[^\s]+', 'WB_API_KEY_*=***REDACTED***', text)
    text = re.sub(r'OZON_API_KEY_\w+=[^\s]+', 'OZON_API_KEY_*=***REDACTED***', text)
    
    return text


def setup_logger(name: str, log_dir: Path, log_level: str = "INFO") -> logging.Logger:
    """
    Настраивает логгер с записью в файл и консоль
    
    Args:
        name: Имя логгера
        log_dir: Директория для логов
        log_level: Уровень логирования
    
    Returns:
        Настроенный логгер
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    
    # Удаляем существующие обработчики
    logger.handlers.clear()
    
    # Формат логов
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Обработчик для файла
    log_file = log_dir / f"{name}_{datetime.now().strftime('%Y%m%d')}.log"
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # Обработчик для консоли
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    return logger


def build_wb_catalog_url(
    brand_id: int,
    dest: int,
    spp: int = 30,
    page: int = 1,
    curr: str = "rub",
    lang: str = "ru",
    sort: str = "popular"
) -> str:
    """
    Строит URL для запроса к внутреннему API каталога WB
    
    Args:
        brand_id: ID бренда
        dest: Регион/ПВЗ
        spp: Параметр СПП
        page: Номер страницы
        curr: Валюта
        lang: Язык
        sort: Сортировка
    
    Returns:
        Полный URL для запроса
    """
    base_url = "https://www.wildberries.ru/__internal/catalog/brands/v4/catalog"
    
    params = {
        "ab_testing": "false",
        "appType": "1",
        "brand": str(brand_id),
        "curr": curr,
        "dest": str(dest),
        "lang": lang,
        "page": str(page),
        "sort": sort,
        "spp": str(spp),
        "uclusters": "1"
    }
    
    query_string = "&".join([f"{k}={v}" for k, v in params.items()])
    return f"{base_url}?{query_string}"


def extract_price_from_text(text: str) -> Optional[float]:
    """
    Извлекает цену из текста (удаляет пробелы, символы валюты и т.д.)
    
    Args:
        text: Текст с ценой (например, "432,00 ₽" или "432.00")
    
    Returns:
        Цена как float или None
    """
    if not text:
        return None
    
    # Удаляем все символы кроме цифр, точки и запятой
    cleaned = re.sub(r'[^\d.,]', '', text.strip())
    
    # Заменяем запятую на точку
    cleaned = cleaned.replace(',', '.')
    
    try:
        return float(cleaned)
    except (ValueError, AttributeError):
        return None


def retry_with_backoff(max_retries: int = 3, base_delay: float = 1.0):
    """
    Декоратор для retry с экспоненциальным backoff
    
    Args:
        max_retries: Максимальное количество попыток
        base_delay: Базовая задержка в секундах
    """
    import asyncio
    from functools import wraps
    
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        await asyncio.sleep(delay)
                    else:
                        raise
            raise last_exception
        return wrapper
    return decorator


