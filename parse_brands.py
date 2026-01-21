"""Скрипт для парсинга цен по продавцам через внутренний API WB."""
import asyncio
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

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
        
        discounts_api_token = os.getenv("WB_DISCOUNTS_API_TOKEN")
        
        # Загружаем токены для каждого кабинета (если указаны)
        discounts_tokens_by_cabinet = {}
        cabinet_names = ["COSMO", "BEAUTYLAB", "MAU", "MAB", "MMA", "DREAMLAB"]
        for cabinet_name in cabinet_names:
            token = os.getenv(f"WB_DISCOUNTS_API_TOKEN_{cabinet_name}")
            if token:
                discounts_tokens_by_cabinet[cabinet_name] = token
        
        # Собираем cookies из .env (опционально, для обхода антибота)
        # Если cookies не указаны, код попытается работать без них (может не работать)
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
            "dest": int(os.getenv("WB_DEST", "-1257786")),  # ПВЗ: г Москва, ул Никольская д. 7-9, стр. 4
            "spp": int(os.getenv("WB_SPP", "30")),
            "cookies": cookies_string,  # Опционально: cookies из .env для обхода антибота
            "discounts_api_token": discounts_api_token,
            "discounts_tokens_by_cabinet": discounts_tokens_by_cabinet,
        }
    except Exception:
        return {
            "dest": -1257786,  # ПВЗ: г Москва, ул Никольская д. 7-9, стр. 4
            "spp": 30,
            "cookies": None,  # Cookies опциональны
            "discounts_api_token": None,
            "discounts_tokens_by_cabinet": {}
        }


async def fetch_discounted_prices_for_results(results: List[Dict], 
                                             cookies: Optional[str] = None,
                                             discounts_api_token: Optional[str] = None,
                                             discounts_tokens_by_cabinet: Optional[Dict[str, str]] = None) -> List[Dict]:
    """Получает discountedPrice для всех товаров из результатов парсинга.
    
    Args:
        results: Список результатов парсинга с полем product_id
        cookies: Опциональные cookies для запросов (если нужны для discounts API)
        discounts_api_token: Токен для авторизации в discounts API
        discounts_tokens_by_cabinet: Токены по кабинетам для discounts API
    
    Returns:
        Обновленный список результатов с полем price_before_spp
    """
    import time
    from src.api.wb_catalog_api import WBCatalogAPI
    
    if not results:
        return results
    
    logger.info("\n" + "=" * 70)
    logger.info("💰 Получение цен до СПП (discountedPrice) через официальный API")
    logger.info("=" * 70)
    
    fetch_start_time = time.time()
    
    # Собираем уникальные product_id и группируем по кабинетам для анализа
    product_ids = set()
    product_ids_by_cabinet = {}
    
    for result in results:
        product_id = result.get("product_id")
        cabinet_name = result.get("cabinet_name", "Unknown")
        
        if product_id:
            product_ids.add(product_id)
            if cabinet_name not in product_ids_by_cabinet:
                product_ids_by_cabinet[cabinet_name] = []
            product_ids_by_cabinet[cabinet_name].append(product_id)
    
    logger.info(f"📊 Найдено уникальных товаров: {len(product_ids)}")
    
    # Логируем распределение по кабинетам
    for cabinet_name, ids in product_ids_by_cabinet.items():
        logger.info(f"  • {cabinet_name}: {len(ids)} товаров")
    
    if not product_ids:
        logger.warning("⚠️ Не найдено product_id в результатах")
        return results
    
    # Проверяем наличие токенов
    if not discounts_api_token and not (discounts_tokens_by_cabinet and discounts_tokens_by_cabinet):
        logger.warning(
            "⚠️ WB_DISCOUNTS_API_TOKEN не найден в .env файле. "
            "Запросы к discounts API будут пропущены. "
            "Добавьте токен в .env: WB_DISCOUNTS_API_TOKEN=your_token "
            "или WB_DISCOUNTS_API_TOKEN_COSMO, WB_DISCOUNTS_API_TOKEN_BEAUTYLAB и т.д."
        )
        # Возвращаем результаты без price_before_spp
        for result in results:
            result["price_before_spp"] = None
        return results
    
    # Если есть токены по кабинетам, делаем отдельные запросы для каждого кабинета
    if discounts_tokens_by_cabinet:
        logger.info("🔑 Используются токены по кабинетам для запросов к discounts API")
        all_discounted_prices = {}
        
        # Группируем товары по кабинетам
        products_by_cabinet = {}
        for result in results:
            cabinet_name = result.get("cabinet_name", "Unknown")
            product_id = result.get("product_id")
            if product_id:
                if cabinet_name not in products_by_cabinet:
                    products_by_cabinet[cabinet_name] = []
                products_by_cabinet[cabinet_name].append(product_id)
        
        # Делаем запросы для каждого кабинета с соответствующим токеном
        for cabinet_name, product_ids_list in products_by_cabinet.items():
            cabinet_token = discounts_tokens_by_cabinet.get(cabinet_name)
            
            if not cabinet_token:
                # Fallback на общий токен, если нет токена для кабинета
                cabinet_token = discounts_api_token
                if not cabinet_token:
                    logger.warning(
                        f"⚠️ Нет токена для кабинета {cabinet_name}, пропускаем {len(product_ids_list)} товаров"
                    )
                    continue
            
            logger.info(
                f"📊 Запрос discountedPrice для кабинета {cabinet_name}: "
                f"{len(set(product_ids_list))} уникальных товаров"
            )
            
            async with WBCatalogAPI(
                request_delay=0.1, 
                max_concurrent=10,
                cookies=cookies,
                discounts_api_token=cabinet_token
            ) as api:
                cabinet_discounted_prices = await api.fetch_discounted_prices(list(set(product_ids_list)))
                all_discounted_prices.update(cabinet_discounted_prices)
        
        discounted_prices = all_discounted_prices
    else:
        # Используем общий токен для всех товаров
        async with WBCatalogAPI(
            request_delay=0.1, 
            max_concurrent=10,
            cookies=cookies,
            discounts_api_token=discounts_api_token
        ) as api:
            discounted_prices = await api.fetch_discounted_prices(list(product_ids))
    
    fetch_time = time.time() - fetch_start_time
    
    logger.info(
        f"✅ Получено discountedPrice для {len(discounted_prices)} товаров "
        f"за {fetch_time:.2f} сек"
    )
    
    # Анализируем, какие кабинеты получили данные
    found_by_cabinet = {}
    for result in results:
        product_id = result.get("product_id")
        cabinet_name = result.get("cabinet_name", "Unknown")
        if product_id in discounted_prices:
            if cabinet_name not in found_by_cabinet:
                found_by_cabinet[cabinet_name] = 0
            found_by_cabinet[cabinet_name] += 1
    
    if found_by_cabinet:
        logger.info("📊 Получено данных по кабинетам:")
        for cabinet_name, count in found_by_cabinet.items():
            total = len(product_ids_by_cabinet.get(cabinet_name, []))
            logger.info(f"  • {cabinet_name}: {count} из {total} товаров ({count/total*100:.1f}%)")
    
    # Сопоставляем discountedPrice с товарами
    updated_count = 0
    not_found_in_api = []
    not_matched_by_size = []
    
    # Группируем по кабинетам для анализа
    not_found_by_cabinet = {}
    
    for result in results:
        product_id = result.get("product_id")
        size_id = result.get("size_id")
        size_name = result.get("size_name")
        product_name = result.get("product_name", "Unknown")
        cabinet_name = result.get("cabinet_name", "Unknown")
        
        if product_id in discounted_prices:
            price_data = discounted_prices[product_id]
            
            # Если это товар без размеров
            if None in price_data:
                result["price_before_spp"] = price_data[None]
                updated_count += 1
            # Если это товар с размерами (новая структура с _by_id и _by_name)
            elif isinstance(price_data, dict) and "_by_id" in price_data:
                size_prices_by_id = price_data.get("_by_id", {})
                size_prices_by_name = price_data.get("_by_name", {})
                
                # Пытаемся найти по size_id (optionId из каталога может совпадать с sizeID из discounts API)
                if size_id is not None and size_id in size_prices_by_id:
                    result["price_before_spp"] = size_prices_by_id[size_id]
                    updated_count += 1
                # Если не нашли по ID, пытаемся найти по имени размера
                elif size_name and size_name in size_prices_by_name:
                    result["price_before_spp"] = size_prices_by_name[size_name]
                    updated_count += 1
                # Если ничего не нашли, берем первый доступный размер
                elif size_prices_by_id:
                    first_price = next(iter(size_prices_by_id.values()))
                    result["price_before_spp"] = first_price
                    updated_count += 1
                    logger.debug(
                        f"⚠️ Товар {product_id} ({product_name}): размер {size_id}/{size_name} не найден, "
                        f"использован первый доступный размер"
                    )
                else:
                    # Товар есть в API, но нет discountedPrice для размеров
                    result["price_before_spp"] = None
                    not_matched_by_size.append((product_id, product_name, size_id, size_name))
            # Старая структура (для обратной совместимости)
            elif isinstance(price_data, dict):
                if size_id is not None and size_id in price_data:
                    result["price_before_spp"] = price_data[size_id]
                    updated_count += 1
                elif price_data:
                    first_price = next(iter(price_data.values()))
                    result["price_before_spp"] = first_price
                    updated_count += 1
                else:
                    result["price_before_spp"] = None
                    not_matched_by_size.append((product_id, product_name, size_id, size_name))
        else:
            result["price_before_spp"] = None
            not_found_in_api.append((product_id, result.get("product_name", "Unknown"), cabinet_name))
            # Группируем по кабинетам
            if cabinet_name not in not_found_by_cabinet:
                not_found_by_cabinet[cabinet_name] = []
            not_found_by_cabinet[cabinet_name].append(product_id)
    
    # Логируем статистику по не найденным товарам с разбивкой по кабинетам
    if not_found_in_api:
        logger.warning(
            f"⚠️ {len(not_found_in_api)} товаров не найдено в ответе discounts API"
        )
        
        # Статистика по кабинетам
        for cabinet_name, product_ids in not_found_by_cabinet.items():
            logger.warning(
                f"  • {cabinet_name}: {len(product_ids)} товаров не найдено "
                f"(примеры product_id: {product_ids[:5]})"
            )
        
        # Примеры всех не найденных товаров
        logger.warning(
            f"  Примеры не найденных товаров: {not_found_in_api[:5]}"
        )
    
    if not_matched_by_size:
        logger.warning(
            f"⚠️ {len(not_matched_by_size)} товаров найдено в API, но размеры не совпадают "
            f"(примеры: {not_matched_by_size[:5]})"
        )
    
    logger.success(
        f"✅ Обновлено записей с price_before_spp: {updated_count} из {len(results)} "
        f"({updated_count/len(results)*100:.1f}%)"
    )
    logger.info("=" * 70)
    
    return results


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
        logger.warning("⚠️ Cookies не найдены в .env - запросы могут быть заблокированы антиботом (ошибка 498)")
        logger.info("💡 Для работы парсера необходимо указать cookies в .env файле:")
        logger.info("   WB_COOKIE_WBX_VALIDATION_KEY=...")
        logger.info("   WB_COOKIE__CP=...")
        logger.info("   WB_COOKIE_ROUTEB=...")
        logger.info("   WB_COOKIE_X_WBAAS_TOKEN=...")
        logger.info("   WB_COOKIE__WBAUID=...")
    
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
    
    # Получаем discountedPrice для всех товаров
    if all_results:
        discounts_api_token = env_config.get("discounts_api_token")
        discounts_tokens_by_cabinet = env_config.get("discounts_tokens_by_cabinet", {})
        all_results = await fetch_discounted_prices_for_results(
            all_results,
            cookies=cookies,
            discounts_api_token=discounts_api_token,
            discounts_tokens_by_cabinet=discounts_tokens_by_cabinet
        )
    
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
        
        # Переименовываем столбцы
        rename_mapping = {
            'price_before_spp': 'Цена до СПП',
            'product_id': 'Артикул',
            'price_basic': 'Зачёркнутая цена',
            'price_product': 'Цена с СПП'
        }
        
        for old_name, new_name in rename_mapping.items():
            if old_name in df.columns:
                df = df.rename(columns={old_name: new_name})
        
        # Удаляем ненужные столбцы из экспорта
        columns_to_remove = [
            'size_name',
            'price_card',
            'source_price_basic',
            'source_price_product',
            'source_price_card'
        ]
        
        for col in columns_to_remove:
            if col in df.columns:
                df = df.drop(columns=[col])
        
        # Добавляем расчетные столбцы ПЕРЕД определением порядка
        
        # 1. Цена с картой 10% = Цена с СПП * 0.9 (округляем вниз)
        import math
        if 'Цена с СПП' in df.columns:
            df['Цена с картой 10%'] = df['Цена с СПП'].apply(
                lambda x: math.floor(x * 0.9) if x is not None and pd.notna(x) else None
            )
        
        # 2. Процент СПП = (Цена до СПП - Цена с СПП) / Цена до СПП * 100
        if 'Цена до СПП' in df.columns and 'Цена с СПП' in df.columns:
            def calculate_spp_percent(row):
                price_before_spp = row.get('Цена до СПП')
                price_prod = row.get('Цена с СПП')
                product_id = row.get('Артикул', 'Unknown')
                
                # Проверяем на None и на ноль
                if price_before_spp is None or pd.isna(price_before_spp) or price_before_spp == 0:
                    return None
                if price_prod is None or pd.isna(price_prod):
                    return None
                
                # Вычисляем процент
                percent = ((price_before_spp - price_prod) / price_before_spp) * 100
                
                # Проверяем на отрицательное значение (это баг)
                if percent < 0:
                    logger.warning(
                        f"⚠️ Отрицательный процент СПП для товара {product_id}: "
                        f"{percent:.2f}% (Цена до СПП={price_before_spp}, Цена с СПП={price_prod})"
                    )
                
                # Округляем до 2 знаков после запятой
                return round(percent, 2) if percent is not None else None
            
            df['Процент СПП'] = df.apply(calculate_spp_percent, axis=1)
        
        # Определяем порядок столбцов для экспорта
        desired_order = [
            'brand_id',
            'brand_name',
            'Артикул',
            'product_name',
            'cabinet_id',
            'cabinet_name',
            'supplier_id',
            'supplier_name',
            'size_id',
            'Зачёркнутая цена',
            'Цена до СПП',
            'Цена с СПП',
            'Цена с картой 10%',
            'Процент СПП'
        ]
        
        # Оставляем только существующие столбцы в нужном порядке
        existing_columns = [col for col in desired_order if col in df.columns]
        # Добавляем остальные столбцы (если есть), которые не в списке
        other_columns = [col for col in df.columns if col not in desired_order]
        df = df[existing_columns + other_columns]
        
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
        
        if 'Зачёркнутая цена' in df.columns:
            filled = df['Зачёркнутая цена'].notna().sum()
            logger.info(
                f"💰 Заполнено зачёркнутых цен: {filled} из {len(df)} "
                f"({filled/len(df)*100:.1f}%)"
            )
        
        if 'Цена с СПП' in df.columns:
            filled = df['Цена с СПП'].notna().sum()
            logger.info(
                f"💰 Заполнено цен с СПП: {filled} из {len(df)} "
                f"({filled/len(df)*100:.1f}%)"
            )
        
        if 'Цена до СПП' in df.columns:
            filled = df['Цена до СПП'].notna().sum()
            logger.info(
                f"💰 Заполнено цен до СПП: {filled} из {len(df)} "
                f"({filled/len(df)*100:.1f}%)"
            )
        
        if 'Цена с картой 10%' in df.columns:
            filled = df['Цена с картой 10%'].notna().sum()
            logger.info(
                f"💰 Заполнено цен с картой 10%: {filled} из {len(df)} "
                f"({filled/len(df)*100:.1f}%)"
            )
        
        if 'Процент СПП' in df.columns:
            filled = df['Процент СПП'].notna().sum()
            logger.info(
                f"📊 Заполнено процентов СПП: {filled} из {len(df)} "
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
