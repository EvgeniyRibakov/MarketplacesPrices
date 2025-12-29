"""
Модели данных для парсера цен Wildberries
"""
from dataclasses import dataclass
from typing import Optional
from datetime import datetime


@dataclass
class Product:
    """Модель товара с ценами и метаданными"""
    name: str
    article: str
    price_basic: float
    price_product: float
    price_card: Optional[float]
    cabinet_id: int
    cabinet_name: str
    source_price_basic: str = "api-json"
    source_price_product: str = "api-json"
    source_price_card: str = "api-json"
    product_url: Optional[str] = None
    timestamp: Optional[datetime] = None

    def __post_init__(self):
        """Валидация после создания объекта"""
        if self.price_basic < 0:
            raise ValueError(f"price_basic не может быть отрицательным: {self.price_basic}")
        if self.price_product < 0:
            raise ValueError(f"price_product не может быть отрицательным: {self.price_product}")
        if self.price_card is not None and self.price_card < 0:
            raise ValueError(f"price_card не может быть отрицательным: {self.price_card}")
        if not self.name:
            raise ValueError("name не может быть пустым")
        if not self.article:
            raise ValueError("article не может быть пустым")
        
        # Установить timestamp если не указан
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()

    def to_dict(self) -> dict:
        """Конвертация в словарь для экспорта"""
        return {
            "cabinet_name": self.cabinet_name,
            "cabinet_id": self.cabinet_id,
            "article": self.article,
            "name": self.name,
            "price_basic": self.price_basic,
            "price_product": self.price_product,
            "price_card": self.price_card,
            "source_price_basic": self.source_price_basic,
            "source_price_product": self.source_price_product,
            "source_price_card": self.source_price_card,
            "product_url": self.product_url,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


@dataclass
class Cabinet:
    """Модель кабинета продавца"""
    name: str
    cabinet_id: int
    api_key: Optional[str] = None

    def __post_init__(self):
        """Валидация кабинета"""
        if not self.name:
            raise ValueError("cabinet name не может быть пустым")
        if self.cabinet_id <= 0:
            raise ValueError(f"cabinet_id должен быть положительным: {self.cabinet_id}")


