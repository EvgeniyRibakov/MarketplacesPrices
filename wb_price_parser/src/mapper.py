"""
Модуль для маппинга между JSON идентификаторами и DOM идентификаторами
"""
import logging
from typing import Dict, Optional, Any
from urllib.parse import urljoin, urlparse

from .wb_api import WBProduct


class ProductMapper:
    """Класс для сопоставления JSON товаров с DOM элементами"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        Инициализация маппера
        
        Args:
            logger: Логгер (опционально)
        """
        self.logger = logger or logging.getLogger(__name__)
        # Кэш для мэппинга (можно загружать из файла discovery)
        self.mapping_cache: Dict[int, Dict[str, Any]] = {}
    
    def map_json_to_dom(self, product: WBProduct) -> Dict[str, Any]:
        """
        Сопоставляет JSON товар с DOM идентификаторами
        
        Args:
            product: Товар из JSON API
        
        Returns:
            Словарь с информацией для DOM парсинга:
            - product_url: URL товара
            - dom_id: ID DOM элемента (если известен)
            - nm_id: nmId товара
        """
        result = {
            "product_url": product.product_url,
            "nm_id": product.nm_id,
            "id": product.id,
        }
        
        # Если есть кэш, используем его
        if product.nm_id in self.mapping_cache:
            cached = self.mapping_cache[product.nm_id]
            result.update(cached)
        
        # Формируем product_url если его нет
        if not result["product_url"] and product.nm_id:
            result["product_url"] = f"https://www.wildberries.ru/catalog/{product.nm_id}/detail.aspx"
        
        return result
    
    def extract_dom_id_from_url(self, url: str) -> Optional[str]:
        """
        Извлекает DOM ID из URL товара
        
        Args:
            url: URL товара
        
        Returns:
            DOM ID или None
        """
        if not url:
            return None
        
        # Пробуем извлечь из различных форматов URL
        # Например: /catalog/123456/detail.aspx -> 123456
        try:
            parsed = urlparse(url)
            path_parts = parsed.path.strip("/").split("/")
            
            # Ищем числовой ID в пути
            for part in path_parts:
                if part.isdigit():
                    return part
        except Exception as e:
            self.logger.debug(f"Не удалось извлечь DOM ID из URL {url}: {e}")
        
        return None
    
    def load_mapping_from_discovery(self, mapping_file: str):
        """
        Загружает мэппинг из файла discovery
        
        Args:
            mapping_file: Путь к файлу с мэппингом
        """
        import json
        from pathlib import Path
        
        mapping_path = Path(mapping_file)
        if not mapping_path.exists():
            self.logger.warning(f"Файл мэппинга не найден: {mapping_file}")
            return
        
        try:
            with open(mapping_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Предполагаем формат: {nm_id: {dom_id, product_url, ...}}
                self.mapping_cache.update(data)
            self.logger.info(f"Загружено {len(self.mapping_cache)} записей мэппинга")
        except Exception as e:
            self.logger.error(f"Ошибка загрузки мэппинга: {e}")


