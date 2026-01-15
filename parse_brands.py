"""Скрипт для парсинга цен по продавцам через внутренний API WB."""
import asyncio
import json
import sys
from pathlib import Path
from typing import Dict, List

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from loguru import logger
from src.parsers.wb_parser import WildberriesParser
try:
    from src.utils.logger import setup_logger
except ImportError:
    def setup_logger(logs_dir, debug=False):
        logger.info("Логирование настроено")


def load_brands_config() -> Dict:
    """Загружает конфигурацию брендов из brands_config.json."""
    config_file = project_root / "config" / "brands_config.json"
    
    if not config_file.exists():
        logger.error(f"Файл конфигурации {config_file} не найден")
        return {}
    
    with open(config_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_env_config() -> Dict:
    """Загружает конфигурацию из .env файла."""
    try:
        from dotenv import load_dotenv
        import os
        
        env_file = project_root / ".env"
        if env_file.exists():
            load_dotenv(env_file)
        
        # Собираем cookies из .env
        cookies_parts = []
        cookie_names = [
            "wbx-validation-key",
            "_cp",
            "routeb",
            "x_wbaas_token",
            "_wbauid"
        ]
        
        for cookie_name in cookie_names:
            cookie_value = os.getenv(f"WB_COOKIE_{cookie_name.replace('-', '_').upper()}")
            if cookie_value:
                cookies_parts.append(f"{cookie_name}={cookie_value}")
        
        cookies_string = "; ".join(cookies_parts) if cookies_parts else None
        
        return {
            "dest": int(os.getenv("WB_DEST", "-3115289")),
            "spp": int(os.getenv("WB_SPP", "30")),
            "cookies": cookies_string,
        }
    except Exception:
        return {"dest": -3115289, "spp": 30, "cookies": None}


async def parse_all_sellers():
    """Парсит всех продавцов из конфигурации кабинетов."""
    import time
    from src.api.wb_catalog_api import WBCatalogAPI
    
    logs_dir = project_root / "logs"
    logs_dir.mkdir(exist_ok=True)
    setup_logger(logs_dir, debug=True)  # Включаем DEBUG для диагностики cookies
    
    total_start_time = time.time()
    
    logger.info("=" * 70)
    logger.info("🚀 Парсинг цен по продавцам через внутренний API WB")
    logger.info("=" * 70)
    
    config_start = time.time()
    env_config = load_env_config()
    config_time = time.time() - config_start
    
    # Парсим только COSMO и BEAUTYLAB
    suppliers = [
        224650,   # COSMO
        4428365   # BEAUTYLAB
    ]
    
    logger.info(
        f"✅ Конфигурация загружена за {config_time:.2f} сек: "
        f"найдено продавцов для обработки: {len(suppliers)}"
    )
    
    parser = WildberriesParser(
        api_key="",
        cabinet_name="",
        cabinet_id="",
        request_delay=0.1
    )
    
    all_results = []
    dest = env_config["dest"]
    spp = env_config["spp"]
    cookies = env_config.get("cookies")
    
    if cookies:
        logger.info("✅ Используются cookies из .env файла")
    else:
        logger.warning("⚠️ Cookies не найдены в .env - запросы могут быть заблокированы антиботом")
    
    successful_suppliers = 0
    failed_suppliers = 0
    supplier_times = []
    
    for supplier_index, supplier_id in enumerate(suppliers, 1):
        cabinet_name = WBCatalogAPI.CABINET_MAPPING[supplier_id]
        supplier_start_time = time.time()
        
        logger.info(f"\n{'='*70}")
        logger.info(
            f"📦 Продавец {supplier_index}/{len(suppliers)}: {supplier_id} ({cabinet_name})"
        )
        logger.info(f"{'='*70}")
        
        try:
            results = await parser.parse_seller_catalog(
                supplier_id=supplier_id,
                dest=dest,
                spp=spp,
                cookies=cookies
            )
            
            supplier_time = time.time() - supplier_start_time
            supplier_times.append((cabinet_name, supplier_time))
            
            all_results.extend(results)
            successful_suppliers += 1
            
            logger.success(
                f"✅ Продавец {supplier_id} ({cabinet_name}): получено {len(results)} записей за {supplier_time:.2f} сек"
            )
            
        except Exception as e:
            supplier_time = time.time() - supplier_start_time
            failed_suppliers += 1
            
            logger.error(
                f"❌ Ошибка при обработке продавца {supplier_id} ({cabinet_name}) "
                f"(время до ошибки: {supplier_time:.2f} сек): {e}"
            )
            logger.exception("Детали ошибки:")
            continue
    
    total_time = time.time() - total_start_time
    
    logger.info("\n" + "=" * 70)
    logger.info("📊 ИТОГОВАЯ СТАТИСТИКА ПАРСИНГА")
    logger.info("=" * 70)
    logger.info(f"⏱️  Общее время выполнения: {total_time:.2f} сек ({total_time/60:.2f} мин)")
    logger.info(f"✅ Успешно обработано продавцов: {successful_suppliers}")
    logger.info(f"❌ Ошибок при обработке: {failed_suppliers}")
    logger.info(f"📦 Всего получено записей: {len(all_results)}")
    
    if supplier_times:
        logger.info("\n⏱️  Время обработки по продавцам:")
        for cabinet_name, supplier_time in supplier_times:
            logger.info(f"  • {cabinet_name}: {supplier_time:.2f} сек")
        
        avg_time = sum(st[1] for st in supplier_times) / len(supplier_times)
        logger.info(f"  📊 Среднее время на продавца: {avg_time:.2f} сек")
    
    logger.info("=" * 70)
    
    return all_results


def export_results(results: List[Dict], output_dir: Path):
    """Экспортирует результаты в Excel."""
    import time
    
    if not results:
        logger.warning("⚠️ Нет данных для экспорта")
        return
    
    export_start_time = time.time()
    logger.info("💾 Начинаем экспорт результатов в Excel...")
    
    try:
        import pandas as pd
        from datetime import datetime
        from openpyxl.utils import get_column_letter
        
        df = pd.DataFrame(results)
        
        sort_columns = []
        if 'brand_name' in df.columns:
            sort_columns.append('brand_name')
        if 'cabinet_name' in df.columns:
            sort_columns.append('cabinet_name')
        if 'product_name' in df.columns:
            sort_columns.append('product_name')
        
        if sort_columns:
            df = df.sort_values(sort_columns, ascending=[True] * len(sort_columns))
        
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"wb_brands_prices_{timestamp}.xlsx"
        
        with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Prices')
            
            worksheet = writer.sheets['Prices']
            
            for idx, col in enumerate(df.columns, 1):
                max_length = max(
                    df[col].astype(str).map(len).max(),
                    len(str(col))
                )
                col_letter = get_column_letter(idx)
                worksheet.column_dimensions[col_letter].width = min(max_length + 2, 50)
        
        export_time = time.time() - export_start_time
        
        logger.success(
            f"✅ Результаты сохранены в: {output_file} (время экспорта: {export_time:.2f} сек)"
        )
        logger.info(f"📊 Всего строк: {len(df)}")
        logger.info(f"📋 Колонки: {', '.join(df.columns.tolist())}")
        
        if 'price_basic' in df.columns:
            filled = df['price_basic'].notna().sum()
            logger.info(
                f"💰 Заполнено базовых цен: {filled} из {len(df)} "
                f"({filled/len(df)*100:.1f}%)"
            )
        
        if 'price_product' in df.columns:
            filled = df['price_product'].notna().sum()
            logger.info(
                f"💰 Заполнено цен продукта: {filled} из {len(df)} "
                f"({filled/len(df)*100:.1f}%)"
            )
        
        if 'brand_name' in df.columns:
            logger.info("\n📈 Статистика по брендам:")
            brand_stats = df.groupby('brand_name').size()
            for brand, count in brand_stats.items():
                logger.info(f"  • {brand}: {count} записей")
        
        if 'cabinet_name' in df.columns:
            logger.info("\n🏢 Статистика по кабинетам:")
            cabinet_stats = df.groupby('cabinet_name').size()
            for cabinet, count in cabinet_stats.items():
                logger.info(f"  • {cabinet}: {count} записей")
        
    except Exception as e:
        export_time = time.time() - export_start_time
        logger.error(
            f"❌ Ошибка при экспорте результатов (время до ошибки: {export_time:.2f} сек): {e}"
        )
        logger.exception("Детали ошибки:")


async def main():
    """Основная функция."""
    import time
    
    main_start_time = time.time()
    
    try:
        results = await parse_all_sellers()
        
        parse_time = time.time() - main_start_time
        
        logger.info("\n" + "=" * 70)
        logger.success(
            f"✅ Обработка завершена. Всего записей: {len(results)} "
            f"(время парсинга: {parse_time:.2f} сек)"
        )
        logger.info("=" * 70)
        
        export_start = time.time()
        output_dir = project_root / "output"
        export_results(results, output_dir)
        export_time = time.time() - export_start
        
        total_time = time.time() - main_start_time
        
        logger.info("\n" + "=" * 70)
        logger.info("🎉 ПРОЦЕСС ЗАВЕРШЕН УСПЕШНО")
        logger.info("=" * 70)
        logger.info(f"⏱️  Общее время выполнения: {total_time:.2f} сек ({total_time/60:.2f} мин)")
        logger.info(f"  • Парсинг: {parse_time:.2f} сек")
        logger.info(f"  • Экспорт: {export_time:.2f} сек")
        logger.info(f"📦 Всего записей: {len(results)}")
        logger.info("=" * 70)
        
        return 0
        
    except KeyboardInterrupt:
        elapsed_time = time.time() - main_start_time
        logger.warning(
            f"⚠️ Прервано пользователем (время работы: {elapsed_time:.2f} сек)"
        )
        return 1
        
    except Exception as e:
        elapsed_time = time.time() - main_start_time
        logger.error(
            f"❌ Критическая ошибка (время до ошибки: {elapsed_time:.2f} сек): {e}"
        )
        logger.exception("Детали ошибки:")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
