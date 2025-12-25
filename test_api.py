"""Тестовый скрипт для проверки работы API."""
import sys
from pathlib import Path

# Добавляем src в путь
sys.path.insert(0, str(Path(__file__).parent / "src"))

from loguru import logger
from config.settings import Settings
from utils.logger import setup_logger
from api.wb_api import WildberriesAPI
from api.ozon_api import OzonAPI


def test_wb_api(settings: Settings) -> bool:
    """Тестирование Wildberries API.
    
    Args:
        settings: Настройки приложения
        
    Returns:
        True если тест прошёл успешно, False иначе
    """
    logger.info("=" * 60)
    logger.info("ТЕСТИРОВАНИЕ WILDBERRIES API")
    logger.info("=" * 60)
    
    wb_api_keys = settings.get_wb_api_keys()
    wb_cabinet_ids = settings.get_wb_cabinet_ids()
    
    # Берём первый доступный кабинет для теста
    test_cabinet = None
    test_api_key = None
    test_cabinet_id = None
    
    for cabinet_name, api_key in wb_api_keys.items():
        if api_key:
            test_cabinet = cabinet_name
            test_api_key = api_key
            test_cabinet_id = wb_cabinet_ids.get(cabinet_name)
            break
    
    if not test_cabinet:
        logger.error("❌ Не найден ни один кабинет WB с API ключом")
        return False
    
    logger.info(f"Тестируем кабинет: {test_cabinet} (ID: {test_cabinet_id})")
    
    try:
        # Создаём API клиент
        api = WildberriesAPI(test_api_key, request_delay=0.5)
        
        # Тест 1: Получение списка товаров
        logger.info("")
        logger.info("Тест 1: Получение списка товаров...")
        products = api.get_content(limit=10, offset=0)
        
        if products:
            logger.success(f"✅ Получено товаров: {len(products)}")
            if products:
                logger.info(f"Пример товара: {products[0].get('vendorCode', 'N/A')} - {products[0].get('title', 'N/A')[:50]}")
        else:
            logger.warning("⚠️ Не удалось получить товары (возможно, кабинет пуст или ошибка API)")
        
        # Тест 2: Получение цен по артикулам (если есть товары)
        if products and len(products) > 0:
            logger.info("")
            logger.info("Тест 2: Получение цен по артикулам...")
            
            # Берём первые 5 артикулов для теста
            test_articles = []
            for product in products[:5]:
                vendor_code = product.get("vendorCode")
                if vendor_code:
                    test_articles.append(vendor_code)
            
            if test_articles:
                logger.info(f"Запрашиваем цены для артикулов: {test_articles}")
                prices = api.get_prices_by_articles(test_articles)
                
                if prices:
                    logger.success(f"✅ Получено цен: {len(prices)}")
                    if prices:
                        logger.info(f"Пример данных о цене: {prices[0]}")
                else:
                    logger.warning("⚠️ Не удалось получить цены")
            else:
                logger.warning("⚠️ Не найдено артикулов для теста")
        
        # Тест 3: Получение цен по nm_id (если есть товары)
        if products and len(products) > 0:
            logger.info("")
            logger.info("Тест 3: Получение цен по nm_id...")
            
            # Берём первый nm_id для теста
            test_nm_id = None
            for product in products:
                nm_id = product.get("nmID")
                if nm_id:
                    test_nm_id = nm_id
                    break
            
            if test_nm_id:
                logger.info(f"Запрашиваем цены для nm_id: {test_nm_id}")
                price_data = api.get_prices_by_nm_id(test_nm_id)
                
                if price_data:
                    logger.success("✅ Получены данные о ценах")
                    logger.info(f"Пример данных: {price_data}")
                else:
                    logger.warning("⚠️ Не удалось получить цены по nm_id")
            else:
                logger.warning("⚠️ Не найден nm_id для теста")
        
        logger.success("=" * 60)
        logger.success("✅ ТЕСТИРОВАНИЕ WILDBERRIES API ЗАВЕРШЕНО")
        logger.success("=" * 60)
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка при тестировании WB API: {e}")
        logger.exception("Детали ошибки:")
        return False


def test_ozon_api(settings: Settings) -> bool:
    """Тестирование Ozon API.
    
    Args:
        settings: Настройки приложения
        
    Returns:
        True если тест прошёл успешно, False иначе
    """
    logger.info("")
    logger.info("=" * 60)
    logger.info("ТЕСТИРОВАНИЕ OZON API")
    logger.info("=" * 60)
    
    ozon_api_keys = settings.get_ozon_api_keys()
    ozon_client_ids = settings.get_ozon_client_ids()
    
    # Берём первый доступный кабинет для теста
    test_cabinet = None
    test_api_key = None
    test_client_id = None
    
    for cabinet_name, api_key in ozon_api_keys.items():
        if api_key:
            test_cabinet = cabinet_name
            test_api_key = api_key
            test_client_id = ozon_client_ids.get(cabinet_name)
            break
    
    if not test_cabinet:
        logger.error("❌ Не найден ни один кабинет Ozon с API ключом")
        return False
    
    logger.info(f"Тестируем кабинет: {test_cabinet}")
    
    try:
        # Создаём API клиент
        api = OzonAPI(test_api_key, test_client_id, request_delay=0.5)
        
        # Тест 1: Получение списка товаров
        logger.info("")
        logger.info("Тест 1: Получение списка товаров...")
        products = api.get_product_list(limit=10)
        
        if products and "result" in products:
            items = products["result"].get("items", [])
            logger.success(f"✅ Получено товаров: {len(items)}")
            if items:
                logger.info(f"Пример товара: {items[0]}")
        else:
            logger.warning("⚠️ Не удалось получить товары (возможно, кабинет пуст или ошибка API)")
            logger.info(f"Ответ API: {products}")
        
        # Тест 2: Получение цен (если есть товары)
        if products and "result" in products:
            items = products["result"].get("items", [])
            if items:
                logger.info("")
                logger.info("Тест 2: Получение цен товаров...")
                
                # Берём первые 5 product_id для теста
                test_product_ids = []
                for item in items[:5]:
                    product_id = item.get("product_id") or item.get("id")
                    if product_id:
                        test_product_ids.append(product_id)
                
                if test_product_ids:
                    logger.info(f"Запрашиваем цены для product_id: {test_product_ids}")
                    prices = api.get_product_prices(test_product_ids)
                    
                    if prices:
                        logger.success(f"✅ Получено цен: {len(prices)}")
                        if prices:
                            logger.info(f"Пример данных о цене: {prices[0]}")
                    else:
                        logger.warning("⚠️ Не удалось получить цены")
                else:
                    logger.warning("⚠️ Не найдено product_id для теста")
        
        logger.success("=" * 60)
        logger.success("✅ ТЕСТИРОВАНИЕ OZON API ЗАВЕРШЕНО")
        logger.success("=" * 60)
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка при тестировании Ozon API: {e}")
        logger.exception("Детали ошибки:")
        return False


def main():
    """Основная функция тестирования."""
    try:
        # Загрузка настроек
        settings = Settings()
        
        # Настройка логирования
        setup_logger(settings.logs_dir, debug=settings.debug)
        
        logger.info("=" * 60)
        logger.info("ЗАПУСК ТЕСТИРОВАНИЯ API")
        logger.info("=" * 60)
        logger.info("")
        
        # Проверка наличия API ключей
        wb_api_keys = settings.get_wb_api_keys()
        ozon_api_keys = settings.get_ozon_api_keys()
        
        wb_available = sum(1 for key in wb_api_keys.values() if key)
        ozon_available = sum(1 for key in ozon_api_keys.values() if key)
        
        logger.info(f"Доступно кабинетов WB: {wb_available}/{len(wb_api_keys)}")
        logger.info(f"Доступно кабинетов Ozon: {ozon_available}/{len(ozon_api_keys)}")
        logger.info("")
        
        # Тестирование WB API
        wb_success = test_wb_api(settings)
        
        # Тестирование Ozon API
        ozon_success = test_ozon_api(settings)
        
        # Итоги
        logger.info("")
        logger.info("=" * 60)
        logger.info("ИТОГИ ТЕСТИРОВАНИЯ")
        logger.info("=" * 60)
        logger.info(f"Wildberries API: {'✅ УСПЕШНО' if wb_success else '❌ ОШИБКА'}")
        logger.info(f"Ozon API: {'✅ УСПЕШНО' if ozon_success else '❌ ОШИБКА'}")
        logger.info("=" * 60)
        
        return 0 if (wb_success or ozon_success) else 1
        
    except KeyboardInterrupt:
        logger.warning("Прервано пользователем")
        return 1
        
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        logger.exception("Детали ошибки:")
        return 1


if __name__ == "__main__":
    sys.exit(main())


