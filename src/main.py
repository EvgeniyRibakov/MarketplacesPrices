"""Точка входа в приложение."""
import sys
from loguru import logger
from config.settings import Settings
from utils.logger import setup_logger
from parsers.wb_parser import WildberriesParser


def main() -> int:
    """Основная функция приложения.
    
    Returns:
        Код возврата (0 - успех, 1 - ошибка)
    """
    try:
        # Загрузка настроек
        settings = Settings()
        
        # Настройка логирования
        setup_logger(settings.logs_dir, debug=settings.debug)
        
        logger.info("=" * 60)
        logger.info("Запуск парсера цен Wildberries и Ozon")
        logger.info("=" * 60)
        
        # Получаем API ключи и ID кабинетов
        wb_api_keys = settings.get_wb_api_keys()
        wb_cabinet_ids = settings.get_wb_cabinet_ids()
        
        # Проверяем наличие API ключей
        missing_keys = [name for name, key in wb_api_keys.items() if not key]
        if missing_keys:
            logger.warning(f"Отсутствуют API ключи для кабинетов: {', '.join(missing_keys)}")
            logger.info("Продолжаем работу только с доступными кабинетами")
        
        # Обработка кабинетов WB
        all_results = []
        
        for cabinet_name, api_key in wb_api_keys.items():
            if not api_key:
                logger.warning(f"Пропускаем кабинет {cabinet_name} - нет API ключа")
                continue
            
            cabinet_id = wb_cabinet_ids.get(cabinet_name)
            if not cabinet_id:
                logger.warning(f"Пропускаем кабинет {cabinet_name} - нет ID кабинета")
                continue
            
            logger.info(f"Обработка кабинета: {cabinet_name} (ID: {cabinet_id})")
            
            try:
                parser = WildberriesParser(
                    api_key=api_key,
                    cabinet_name=cabinet_name,
                    cabinet_id=cabinet_id,
                    request_delay=settings.request_delay,
                )
                
                # Парсинг базовых цен (читает артикулы из Articles.xlsx)
                basic_prices = parser.parse_basic_prices()
                all_results.extend(basic_prices)
                
                logger.success(f"Кабинет {cabinet_name} обработан: {len(basic_prices)} товаров")
                
            except Exception as e:
                logger.error(f"Ошибка при обработке кабинета {cabinet_name}: {e}")
                logger.exception("Детали ошибки:")
                continue
        
        logger.info("=" * 60)
        logger.success(f"Обработка завершена. Всего товаров: {len(all_results)}")
        logger.info("=" * 60)
        
        # TODO: Экспорт результатов
        logger.info("Экспорт результатов ещё не реализован")
        
        return 0
        
    except KeyboardInterrupt:
        logger.warning("Прервано пользователем")
        return 1
        
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        logger.exception("Детали ошибки:")
        return 1


if __name__ == "__main__":
    sys.exit(main())

