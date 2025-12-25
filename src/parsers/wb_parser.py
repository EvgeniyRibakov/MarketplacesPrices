"""Парсер цен для Wildberries."""
from typing import Dict, List, Optional
from loguru import logger
from api.wb_api import WildberriesAPI


class WildberriesParser:
    """Парсер цен для Wildberries."""
    
    def __init__(self, api_key: str, cabinet_name: str, cabinet_id: str, request_delay: float = 0.5):
        """Инициализация парсера.
        
        Args:
            api_key: API ключ Wildberries
            cabinet_name: Название кабинета
            cabinet_id: ID кабинета
            request_delay: Задержка между запросами
        """
        self.cabinet_name = cabinet_name
        self.cabinet_id = cabinet_id
        self.api = WildberriesAPI(api_key, request_delay=request_delay)
    
    def parse_basic_prices(self) -> List[Dict]:
        """Парсинг базовых цен через официальное API.
        
        Returns:
            Список товаров с базовыми ценами
        """
        logger.info(f"Начинаем парсинг базовых цен для кабинета {self.cabinet_name}...")
        
        # Получаем все товары
        products = self.api.get_all_products()
        
        if not products:
            logger.warning(f"Не удалось получить товары для кабинета {self.cabinet_name}")
            return []
        
        logger.info(f"Получено товаров: {len(products)}")
        
        # Извлекаем артикулы для запроса цен
        vendor_codes = []
        products_map = {}  # Маппинг артикул -> товар
        
        for product in products:
            vendor_code = product.get("vendorCode")
            if vendor_code:
                vendor_codes.append(vendor_code)
                products_map[vendor_code] = product
        
        if not vendor_codes:
            logger.warning(f"Не найдено артикулов для кабинета {self.cabinet_name}")
            return []
        
        logger.info(f"Запрашиваем цены для {len(vendor_codes)} артикулов...")
        
        # Получаем цены по артикулам
        prices_data = self.api.get_prices_by_articles(vendor_codes)
        
        if not prices_data:
            logger.warning(f"Не удалось получить цены для кабинета {self.cabinet_name}")
            # Возвращаем товары без цен
            return [
                {
                    "cabinet": self.cabinet_name,
                    "cabinet_id": self.cabinet_id,
                    "nm_id": product.get("nmID"),
                    "vendor_code": product.get("vendorCode"),
                    "brand": product.get("brand"),
                    "title": product.get("title"),
                    "base_price": None,
                    "discount_price": None,
                    "price_with_card": None,
                }
                for product in products
            ]
        
        # Создаём маппинг артикул -> цена
        prices_map = {}
        for price_item in prices_data:
            vendor_code = price_item.get("vendorCode")
            if vendor_code:
                prices_map[vendor_code] = price_item
        
        # Объединяем данные товаров и цен
        result = []
        for product in products:
            vendor_code = product.get("vendorCode")
            price_data = prices_map.get(vendor_code, {})
            
            # Извлекаем цены из ответа API
            # Структура ответа может отличаться, нужно будет уточнить после тестирования
            base_price = price_data.get("price") or price_data.get("basicPrice")
            discount_price = price_data.get("discountPrice") or price_data.get("priceWithDiscount")
            price_with_card = price_data.get("priceWithCard") or price_data.get("wbCardPrice")
            
            result.append({
                "cabinet": self.cabinet_name,
                "cabinet_id": self.cabinet_id,
                "nm_id": product.get("nmID"),
                "vendor_code": vendor_code,
                "brand": product.get("brand"),
                "title": product.get("title"),
                "base_price": base_price,
                "discount_price": discount_price,
                "price_with_card": price_with_card,
                "raw_price_data": price_data,  # Сохраняем сырые данные для отладки
            })
        
        logger.success(f"Обработано товаров: {len(result)}")
        return result
    
    def parse_card_prices(self) -> List[Dict]:
        """Парсинг цен с WB-картой через XPath (существующее решение).
        
        Returns:
            Список товаров с ценами с картой
        """
        logger.info(f"Начинаем парсинг цен с WB-картой для кабинета {self.cabinet_name}...")
        
        # TODO: Адаптировать существующее XPath-решение
        # Пока заглушка
        
        logger.warning("Парсинг цен с WB-картой ещё не реализован")
        return []
    
    def parse_spp_prices(self) -> List[Dict]:
        """Парсинг цен после СПП (чёрная цена) - требует research.
        
        Returns:
            Список товаров с ценами после СПП
        """
        logger.info(f"Начинаем парсинг цен после СПП для кабинета {self.cabinet_name}...")
        
        # TODO: Research - найти API или XPath для получения цены после СПП
        logger.warning("Парсинг цен после СПП требует research - не реализован")
        return []

