"""Скрипт для парсинга цен по брендам через внутренний API WB."""
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


async def parse_all_brands():
    """Парсит все бренды из конфигурации."""
    logs_dir = project_root / "logs"
    logs_dir.mkdir(exist_ok=True)
    setup_logger(logs_dir, debug=False)
    
    logger.info("=" * 70)
    logger.info("Парсинг цен по брендам через внутренний API WB")
    logger.info("=" * 70)
    
    brands_config = load_brands_config()
    env_config = load_env_config()
    
    if not brands_config:
        logger.error("Не удалось загрузить конфигурацию брендов")
        return []
    
    logger.info(f"Найдено брендов для обработки: {len(brands_config)}")
    
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
        logger.info("Используются cookies из .env файла")
    else:
        logger.warning("Cookies не найдены в .env - запросы могут быть заблокированы антиботом")
    
    for brand_name, brand_data in brands_config.items():
        brand_id = int(brand_data["brand_id"])
        logger.info(f"\n{'='*70}")
        logger.info(f"Обработка бренда: {brand_name} (ID: {brand_id})")
        logger.info(f"{'='*70}")
        
        try:
            results = await parser.parse_brand_catalog(
                brand_id=brand_id,
                brand_name=brand_name.upper(),
                dest=dest,
                spp=spp,
                fsupplier=brand_data.get("fsupplier"),
                cookies=cookies
            )
            
            all_results.extend(results)
            logger.success(f"✓ Бренд {brand_name}: получено {len(results)} записей")
            
        except Exception as e:
            logger.error(f"✗ Ошибка при обработке бренда {brand_name}: {e}")
            logger.exception("Детали ошибки:")
            continue
    
    return all_results


def export_results(results: List[Dict], output_dir: Path):
    """Экспортирует результаты в Excel."""
    if not results:
        logger.warning("Нет данных для экспорта")
        return
    
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
        
        logger.success(f"✅ Результаты сохранены в: {output_file}")
        logger.info(f"📊 Всего строк: {len(df)}")
        logger.info(f"📋 Колонки: {', '.join(df.columns.tolist())}")
        
        if 'price_basic' in df.columns:
            filled = df['price_basic'].notna().sum()
            logger.info(f"💰 Заполнено базовых цен: {filled} из {len(df)} ({filled/len(df)*100:.1f}%)")
        
        if 'price_product' in df.columns:
            filled = df['price_product'].notna().sum()
            logger.info(f"💰 Заполнено цен продукта: {filled} из {len(df)} ({filled/len(df)*100:.1f}%)")
        
        if 'brand_name' in df.columns:
            logger.info("\n📈 Статистика по брендам:")
            brand_stats = df.groupby('brand_name').size()
            for brand, count in brand_stats.items():
                logger.info(f"  {brand}: {count} записей")
        
        if 'cabinet_name' in df.columns:
            logger.info("\n🏢 Статистика по кабинетам:")
            cabinet_stats = df.groupby('cabinet_name').size()
            for cabinet, count in cabinet_stats.items():
                logger.info(f"  {cabinet}: {count} записей")
        
    except Exception as e:
        logger.error(f"Ошибка при экспорте результатов: {e}")
        logger.exception("Детали ошибки:")


async def main():
    """Основная функция."""
    try:
        results = await parse_all_brands()
        
        logger.info("\n" + "=" * 70)
        logger.success(f"Обработка завершена. Всего записей: {len(results)}")
        logger.info("=" * 70)
        
        output_dir = project_root / "output"
        export_results(results, output_dir)
        
        return 0
        
    except KeyboardInterrupt:
        logger.warning("Прервано пользователем")
        return 1
        
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        logger.exception("Детали ошибки:")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
