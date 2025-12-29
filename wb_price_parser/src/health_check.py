"""
Health-check скрипт для проверки работоспособности API
"""
import asyncio
import logging
import sys
from typing import List, Dict, Any

from .config import get_config
from .wb_api import WBAPIClient, WBProduct
from .utils import setup_logger, convert_price_to_rubles


class HealthChecker:
    """Класс для проверки здоровья системы"""
    
    def __init__(self, config=None, logger=None):
        """
        Инициализация health checker
        
        Args:
            config: Конфигурация (опционально)
            logger: Логгер (опционально)
        """
        self.config = config or get_config()
        self.logger = logger or setup_logger(
            "health_check",
            self.config.logs_dir,
            self.config.log_level
        )
        self.issues = []
        self.warnings = []
    
    async def check_api_connectivity(self) -> bool:
        """
        Проверяет доступность API
        
        Returns:
            True если API доступен
        """
        self.logger.info("Проверка доступности API...")
        
        try:
            async with WBAPIClient(self.config, self.logger) as api_client:
                data = await api_client._fetch_page(1)
                
                if data:
                    self.logger.info("✓ API доступен")
                    return True
                else:
                    self.issues.append("API вернул пустой ответ")
                    self.logger.error("✗ API вернул пустой ответ")
                    return False
                    
        except Exception as e:
            self.issues.append(f"Ошибка подключения к API: {e}")
            self.logger.error(f"✗ Ошибка подключения к API: {e}")
            return False
    
    async def check_products_structure(self, limit: int = 10) -> bool:
        """
        Проверяет структуру данных товаров
        
        Args:
            limit: Количество товаров для проверки
        
        Returns:
            True если структура корректна
        """
        self.logger.info(f"Проверка структуры данных (первые {limit} товаров)...")
        
        try:
            async with WBAPIClient(self.config, self.logger) as api_client:
                products = await api_client.fetch_page(1)
                
                if not products:
                    self.issues.append("Не получены товары из API")
                    return False
                
                checked = 0
                for product in products[:limit]:
                    # Проверяем обязательные поля
                    if not product.name:
                        self.warnings.append(f"Товар {product.nm_id}: отсутствует название")
                    
                    if product.price_basic is None or product.price_basic <= 0:
                        self.warnings.append(f"Товар {product.nm_id}: некорректная price_basic")
                    
                    if product.price_product is None or product.price_product <= 0:
                        self.warnings.append(f"Товар {product.nm_id}: некорректная price_product")
                    
                    # Проверяем конвертацию цен
                    if product.price_basic and product.price_basic > 1000000:
                        self.warnings.append(
                            f"Товар {product.nm_id}: price_basic слишком большая "
                            f"({product.price_basic} руб.) - возможно не применена конвертация /100"
                        )
                    
                    checked += 1
                
                self.logger.info(f"✓ Проверено {checked} товаров")
                
                if self.warnings:
                    self.logger.warning(f"Найдено {len(self.warnings)} предупреждений")
                else:
                    self.logger.info("✓ Структура данных корректна")
                
                return True
                
        except Exception as e:
            self.issues.append(f"Ошибка проверки структуры: {e}")
            self.logger.error(f"✗ Ошибка проверки структуры: {e}")
            return False
    
    def check_config(self) -> bool:
        """
        Проверяет конфигурацию
        
        Returns:
            True если конфигурация корректна
        """
        self.logger.info("Проверка конфигурации...")
        
        issues = []
        
        # Проверяем обязательные параметры
        if not self.config.wb_brand_id:
            issues.append("WB_BRAND_ID не установлен")
        
        if not self.config.wb_dest:
            issues.append("WB_DEST не установлен")
        
        if self.config.concurrency <= 0:
            issues.append("CONCURRENCY должен быть > 0")
        
        if not self.config.output_file:
            issues.append("OUTPUT_FILE не установлен")
        
        # Проверяем кабинеты
        if not self.config.cabinets:
            issues.append("Не загружены кабинеты")
        else:
            self.logger.info(f"✓ Загружено кабинетов: {len(self.config.cabinets)}")
        
        if issues:
            self.issues.extend(issues)
            for issue in issues:
                self.logger.error(f"✗ {issue}")
            return False
        else:
            self.logger.info("✓ Конфигурация корректна")
            return True
    
    async def run_full_check(self) -> bool:
        """
        Запускает полную проверку системы
        
        Returns:
            True если все проверки пройдены
        """
        self.logger.info("=" * 60)
        self.logger.info("Запуск Health Check")
        self.logger.info("=" * 60)
        
        results = []
        
        # Проверка конфигурации
        results.append(self.check_config())
        
        # Проверка API
        api_ok = await self.check_api_connectivity()
        results.append(api_ok)
        
        # Проверка структуры данных (только если API доступен)
        if api_ok:
            results.append(await self.check_products_structure(limit=10))
        
        # Итоговый результат
        all_ok = all(results)
        
        self.logger.info("=" * 60)
        if all_ok:
            self.logger.info("✓ Все проверки пройдены успешно")
            if self.warnings:
                self.logger.warning(f"Найдено предупреждений: {len(self.warnings)}")
        else:
            self.logger.error(f"✗ Найдено проблем: {len(self.issues)}")
            for issue in self.issues:
                self.logger.error(f"  - {issue}")
        self.logger.info("=" * 60)
        
        return all_ok


async def main():
    """Главная функция health-check скрипта"""
    try:
        config = get_config()
        checker = HealthChecker(config)
        
        success = await checker.run_full_check()
        
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        print("\nПрервано пользователем")
        sys.exit(0)
    except Exception as e:
        print(f"Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())


