"""
Главный модуль - точка входа для парсера цен Wildberries
"""
import asyncio
import logging
import sys
from pathlib import Path
from typing import List

from .config import get_config, Config
from .models import Product
from .wb_api import WBAPIClient, WBProduct
from .mapper import ProductMapper
from .wb_xpath import WBXPathParser
from .exporter import ExcelExporter
from .utils import setup_logger


class PriceParserPipeline:
    """Основной пайплайн парсера цен"""
    
    def __init__(self, config: Config):
        """
        Инициализация пайплайна
        
        Args:
            config: Конфигурация проекта
        """
        self.config = config
        self.logger = setup_logger(
            "wb_price_parser",
            config.logs_dir,
            config.log_level
        )
        
        # Инициализируем компоненты
        self.api_client: WBAPIClient = None
        self.xpath_parser: WBXPathParser = None
        self.mapper = ProductMapper(self.logger)
        self.exporter = ExcelExporter(config, self.logger)
    
    async def run(self):
        """Запуск основного пайплайна"""
        try:
            self.logger.info("=" * 60)
            self.logger.info("Запуск парсера цен Wildberries")
            self.logger.info("=" * 60)
            
            # Шаг 1: Получение товаров через API
            self.logger.info("Шаг 1: Получение товаров через API...")
            async with WBAPIClient(self.config, self.logger) as api_client:
                self.api_client = api_client
                wb_products = await api_client.fetch_all_products()
            
            if not wb_products:
                self.logger.error("Не удалось получить товары из API")
                return
            
            self.logger.info(f"Получено {len(wb_products)} товаров из API")
            
            # Шаг 2: Определение кабинетов и создание моделей Product
            self.logger.info("Шаг 2: Обработка товаров и определение кабинетов...")
            products = self._create_products(wb_products)
            
            # Шаг 3: Получение price_card через XPath для товаров без цены с картой
            self.logger.info("Шаг 3: Получение price_card через XPath (fallback)...")
            products = await self._enrich_with_price_card(products)
            
            # Шаг 4: Экспорт в Excel
            self.logger.info("Шаг 4: Экспорт в Excel...")
            output_file = self.exporter.export(products)
            
            self.logger.info("=" * 60)
            self.logger.info(f"Парсинг завершён успешно!")
            self.logger.info(f"Обработано товаров: {len(products)}")
            self.logger.info(f"Файл сохранён: {output_file}")
            self.logger.info("=" * 60)
            
        except Exception as e:
            self.logger.error(f"Критическая ошибка в пайплайне: {e}", exc_info=True)
            raise
    
    def _create_products(self, wb_products: List[WBProduct]) -> List[Product]:
        """
        Создаёт модели Product из WBProduct с определением кабинетов
        
        Args:
            wb_products: Список товаров из API
        
        Returns:
            Список моделей Product
        """
        products = []
        
        # Определяем кабинет по бренду или другим признакам
        # В MVP используем первый доступный кабинет или определяем по логике
        default_cabinet = list(self.config.cabinets.values())[0]
        
        for wb_product in wb_products:
            # Определяем кабинет (в MVP можно улучшить логику)
            cabinet = self._determine_cabinet(wb_product) or default_cabinet
            
            # Создаём модель Product
            product = Product(
                name=wb_product.name,
                article=str(wb_product.nm_id) or wb_product.supplier_article or "",
                price_basic=wb_product.price_basic,
                price_product=wb_product.price_product,
                price_card=wb_product.price_card,
                cabinet_id=cabinet.cabinet_id,
                cabinet_name=cabinet.name,
                source_price_basic="api-json",
                source_price_product="api-json",
                source_price_card="api-json" if wb_product.price_card else None,
                product_url=wb_product.product_url,
            )
            
            products.append(product)
        
        return products
    
    def _determine_cabinet(self, wb_product: WBProduct):
        """
        Определяет кабинет для товара
        
        Args:
            wb_product: Товар из API
        
        Returns:
            Кабинет или None
        """
        # В MVP можно использовать бренд или другие признаки
        # Пока возвращаем None - будет использован default_cabinet
        # TODO: Реализовать логику определения кабинета по бренду/другим признакам
        return None
    
    async def _enrich_with_price_card(self, products: List[Product]) -> List[Product]:
        """
        Обогащает товары price_card через XPath для тех, у кого её нет
        
        Args:
            products: Список товаров
        
        Returns:
            Обновлённый список товаров
        """
        # Фильтруем товары без price_card
        products_without_card = [
            p for p in products
            if p.price_card is None and p.product_url
        ]
        
        if not products_without_card:
            self.logger.info("Все товары уже имеют price_card из API")
            return products
        
        self.logger.info(
            f"Получение price_card через XPath для {len(products_without_card)} товаров"
        )
        
        # Получаем price_card через XPath
        async with WBXPathParser(self.config, self.logger) as xpath_parser:
            self.xpath_parser = xpath_parser
            
            # Пакетная обработка
            urls = [p.product_url for p in products_without_card]
            price_cards = await xpath_parser.fetch_price_card_batch(urls)
            
            # Обновляем товары
            url_to_product = {p.product_url: p for p in products_without_card}
            
            for url, price_card in price_cards.items():
                if url in url_to_product:
                    product = url_to_product[url]
                    if price_card:
                        product.price_card = price_card
                        product.source_price_card = "xpath-html"
                        self.logger.debug(
                            f"Получена price_card для {product.name}: {price_card} руб."
                        )
        
        return products


async def main():
    """Главная функция"""
    try:
        # Загружаем конфигурацию
        config = get_config()
        
        # Создаём и запускаем пайплайн
        pipeline = PriceParserPipeline(config)
        await pipeline.run()
        
    except KeyboardInterrupt:
        print("\nПрервано пользователем")
        sys.exit(0)
    except Exception as e:
        print(f"Критическая ошибка: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())


