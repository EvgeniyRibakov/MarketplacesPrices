"""
Discovery скрипт для исследования API и создания примеров данных
"""
import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, Any, List

from .config import get_config
from .wb_api import WBAPIClient
from .utils import setup_logger


class DiscoveryTool:
    """Инструмент для discovery API и создания примеров"""
    
    def __init__(self, config=None, logger=None):
        """
        Инициализация discovery инструмента
        
        Args:
            config: Конфигурация (опционально)
            logger: Логгер (опционально)
        """
        self.config = config or get_config()
        self.logger = logger or setup_logger(
            "discovery",
            self.config.logs_dir,
            self.config.log_level
        )
        self.samples_dir = Path(__file__).parent.parent / "samples"
        self.samples_dir.mkdir(parents=True, exist_ok=True)
    
    async def fetch_and_save_page(self, page: int = 1) -> Dict[str, Any]:
        """
        Запрашивает страницу API и сохраняет в samples/
        
        Args:
            page: Номер страницы
        
        Returns:
            JSON данные страницы
        """
        self.logger.info(f"Запрос страницы {page} API...")
        
        async with WBAPIClient(self.config, self.logger) as api_client:
            data = await api_client._fetch_page(page)
        
        # Сохраняем полный ответ
        output_file = self.samples_dir / f"json_page_{page}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        self.logger.info(f"Сохранён полный ответ в {output_file}")
        
        return data
    
    def extract_products_info(self, data: Dict[str, Any], limit: int = 30) -> List[Dict[str, Any]]:
        """
        Извлекает информацию о товарах из JSON ответа
        
        Args:
            data: JSON данные от API
            limit: Максимальное количество товаров для извлечения
        
        Returns:
            Список словарей с информацией о товарах
        """
        # Пробуем разные варианты структуры
        products_data = data.get("data", {}).get("products", [])
        if not products_data:
            products_data = data.get("products", [])
        if not products_data:
            products_data = data.get("data", [])
        
        if not products_data:
            self.logger.warning("Не найдены товары в ответе API")
            return []
        
        products_info = []
        for i, item in enumerate(products_data[:limit]):
            try:
                product_info = {
                    "index": i + 1,
                    "id": item.get("id"),
                    "nmId": item.get("nmId"),
                    "name": item.get("name") or item.get("title", ""),
                    "price": {
                        "basic": item.get("price", {}).get("basic"),
                        "product": item.get("price", {}).get("product"),
                        "card": item.get("price", {}).get("card") or item.get("price", {}).get("priceCard"),
                    },
                    "link": item.get("link"),
                    "url": item.get("url"),
                    "brand": item.get("brand"),
                    "supplierArticle": item.get("supplierArticle"),
                    "vendorCode": item.get("vendorCode"),
                }
                
                # Формируем product_url если его нет
                if not product_info["link"] and not product_info["url"]:
                    nm_id = product_info["nmId"]
                    if nm_id:
                        product_info["product_url"] = f"https://www.wildberries.ru/catalog/{nm_id}/detail.aspx"
                
                products_info.append(product_info)
                
            except Exception as e:
                self.logger.warning(f"Ошибка извлечения товара {i}: {e}")
        
        return products_info
    
    def save_products_summary(self, products_info: List[Dict[str, Any]], page: int = 1):
        """
        Сохраняет сводку по товарам
        
        Args:
            products_info: Список информации о товарах
            page: Номер страницы
        """
        output_file = self.samples_dir / f"products_summary_page_{page}.json"
        
        summary = {
            "page": page,
            "total_products": len(products_info),
            "products": products_info
        }
        
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        
        self.logger.info(f"Сохранена сводка по {len(products_info)} товарам в {output_file}")
        
        # Также создаём текстовый отчёт
        self._create_text_report(products_info, page)
    
    def _create_text_report(self, products_info: List[Dict[str, Any]], page: int):
        """
        Создаёт текстовый отчёт для удобного просмотра
        
        Args:
            products_info: Список информации о товарах
            page: Номер страницы
        """
        report_file = self.samples_dir / f"products_report_page_{page}.txt"
        
        with open(report_file, "w", encoding="utf-8") as f:
            f.write("=" * 80 + "\n")
            f.write(f"ОТЧЁТ ПО ТОВАРАМ - СТРАНИЦА {page}\n")
            f.write("=" * 80 + "\n\n")
            
            for product in products_info:
                f.write(f"Товар #{product['index']}\n")
                f.write(f"  ID: {product.get('id')}\n")
                f.write(f"  nmId: {product.get('nmId')}\n")
                f.write(f"  Название: {product.get('name', 'N/A')}\n")
                f.write(f"  Цена basic: {product.get('price', {}).get('basic')} коп. "
                       f"({product.get('price', {}).get('basic', 0) / 100:.2f} руб.)\n")
                f.write(f"  Цена product: {product.get('price', {}).get('product')} коп. "
                       f"({product.get('price', {}).get('product', 0) / 100:.2f} руб.)\n")
                f.write(f"  Цена card: {product.get('price', {}).get('card')} коп. "
                       f"({product.get('price', {}).get('card', 0) / 100:.2f} руб.)\n" 
                       if product.get('price', {}).get('card') else "  Цена card: N/A\n")
                f.write(f"  URL: {product.get('link') or product.get('url') or product.get('product_url', 'N/A')}\n")
                f.write(f"  Бренд: {product.get('brand', 'N/A')}\n")
                f.write(f"  Артикул: {product.get('supplierArticle') or product.get('vendorCode', 'N/A')}\n")
                f.write("-" * 80 + "\n\n")
        
        self.logger.info(f"Создан текстовый отчёт: {report_file}")
    
    async def create_mapping_file(self, products_info: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Создаёт файл мэппинга для сопоставления JSON ↔ DOM
        
        Args:
            products_info: Список информации о товарам
        
        Returns:
            Словарь мэппинга
        """
        mapping = {}
        
        for product in products_info:
            nm_id = product.get("nmId")
            if not nm_id:
                continue
            
            mapping[str(nm_id)] = {
                "id": product.get("id"),
                "nmId": nm_id,
                "name": product.get("name"),
                "product_url": (
                    product.get("link") or 
                    product.get("url") or 
                    f"https://www.wildberries.ru/catalog/{nm_id}/detail.aspx"
                ),
                "price_basic": product.get("price", {}).get("basic"),
                "price_product": product.get("price", {}).get("product"),
                "price_card": product.get("price", {}).get("card"),
            }
        
        # Сохраняем мэппинг
        mapping_file = self.samples_dir / "mapping.json"
        with open(mapping_file, "w", encoding="utf-8") as f:
            json.dump(mapping, f, ensure_ascii=False, indent=2)
        
        self.logger.info(f"Создан файл мэппинга: {mapping_file} ({len(mapping)} записей)")
        
        return mapping
    
    async def run_discovery(self, pages: int = 1):
        """
        Запускает полный процесс discovery
        
        Args:
            pages: Количество страниц для анализа
        """
        self.logger.info("=" * 60)
        self.logger.info("Запуск Discovery процесса")
        self.logger.info("=" * 60)
        
        all_products_info = []
        
        for page in range(1, pages + 1):
            try:
                # Запрашиваем страницу
                data = await self.fetch_and_save_page(page)
                
                # Извлекаем информацию о товарах
                products_info = self.extract_products_info(data, limit=30)
                
                if products_info:
                    # Сохраняем сводку
                    self.save_products_summary(products_info, page)
                    all_products_info.extend(products_info)
                else:
                    self.logger.warning(f"Страница {page} не содержит товаров")
                    
            except Exception as e:
                self.logger.error(f"Ошибка при обработке страницы {page}: {e}")
        
        # Создаём общий файл мэппинга
        if all_products_info:
            await self.create_mapping_file(all_products_info)
        
        self.logger.info("=" * 60)
        self.logger.info(f"Discovery завершён. Обработано товаров: {len(all_products_info)}")
        self.logger.info(f"Результаты сохранены в {self.samples_dir}")
        self.logger.info("=" * 60)


async def main():
    """Главная функция discovery скрипта"""
    import sys
    
    try:
        config = get_config()
        discovery = DiscoveryTool(config)
        
        # Количество страниц для анализа (можно передать как аргумент)
        pages = 1
        if len(sys.argv) > 1:
            try:
                pages = int(sys.argv[1])
            except ValueError:
                print(f"Неверный аргумент: {sys.argv[1]}. Используется значение по умолчанию: 1")
        
        await discovery.run_discovery(pages=pages)
        
    except KeyboardInterrupt:
        print("\nПрервано пользователем")
        sys.exit(0)
    except Exception as e:
        print(f"Ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())


