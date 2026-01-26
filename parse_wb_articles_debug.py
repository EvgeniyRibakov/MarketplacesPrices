"""Парсер для получения ВСЕХ полей карточек товаров по всем 6 кабинетам WB (для отладки).

Использует официальное API: POST https://content-api.wildberries.ru/content/v2/get/cards/list
Сохраняет ВСЕ поля в Excel файл для анализа структуры данных.
"""
import asyncio
import os
import sys
import json
from pathlib import Path
from typing import Dict, List
from datetime import datetime

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from loguru import logger
from curl_cffi.requests import AsyncSession

from src.utils.logger import setup_logger

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logs_dir = project_root / "logs"
output_dir = project_root / "output"
logs_dir.mkdir(parents=True, exist_ok=True)
output_dir.mkdir(parents=True, exist_ok=True)

setup_logger(logs_dir, debug=False)

# Маппинг названий кабинетов
CABINET_MAPPING = {
    "MAU": 53607,
    "MAB": 121614,
    "MMA": 174711,
    "COSMO": 224650,
    "DREAMLAB": 1140223,
    "BEAUTYLAB": 4428365
}


async def get_cabinet_cards(api_token: str, cabinet_name: str, limit: int = 100) -> List[Dict]:
    """Получает список карточек товаров для кабинета через официальное API.
    
    Args:
        api_token: API токен продавца (с доступом к разделу "Контент")
        cabinet_name: Название кабинета (MAU, MAB, MMA, COSMO, DREAMLAB, BEAUTYLAB)
        limit: Количество товаров за запрос (максимум 100)
    
    Returns:
        Список карточек товаров со всеми полями
    """
    url = "https://content-api.wildberries.ru/content/v2/get/cards/list"
    
    headers = {
        "Authorization": api_token,
        "Content-Type": "application/json"
    }
    
    all_cards = []
    cursor = None
    
    async with AsyncSession(impersonate="chrome131", timeout=30) as session:
        while True:
            # Формируем тело запроса
            payload = {
                "settings": {
                    "cursor": {
                        "limit": limit
                    },
                    "filter": {
                        "withPhoto": -1  # -1 = все товары (с фото и без)
                    },
                    "sort": {
                        "ascending": False  # По убыванию (новые сначала)
                    }
                }
            }
            
            # Добавляем курсор для пагинации (если есть)
            if cursor:
                payload["settings"]["cursor"].update(cursor)
            
            try:
                logger.debug(f"📥 Запрос карточек для {cabinet_name} (limit={limit})...")
                response = await session.post(url, json=payload, headers=headers)
                
                if response.status_code == 401:
                    error_data = response.json() if response.content else {}
                    detail = error_data.get("detail", "Unauthorized")
                    logger.error(f"❌ Ошибка авторизации для {cabinet_name}: {detail}")
                    logger.error("💡 Проверьте, что токен имеет доступ к разделу 'Контент' API")
                    break
                
                response.raise_for_status()
                data = response.json()
                
                # Извлекаем карточки
                cards = data.get("cards", [])
                if not cards:
                    logger.info(f"📭 Нет больше карточек для {cabinet_name}")
                    break
                
                all_cards.extend(cards)
                logger.info(f"✅ Получено {len(cards)} карточек для {cabinet_name} (всего: {len(all_cards)})")
                
                # Если получили меньше limit, значит это последняя страница
                if len(cards) < limit:
                    break
                
                # Обновляем курсор для следующего запроса
                if cards:
                    last_card = cards[-1]
                    cursor = {
                        "updatedAt": last_card.get("updatedAt"),
                        "nmID": last_card.get("nmID")
                    }
                else:
                    break
                
                # Соблюдаем rate limits (600мс между запросами)
                await asyncio.sleep(0.6)
                
            except Exception as e:
                logger.error(f"❌ Ошибка при запросе карточек для {cabinet_name}: {e}")
                logger.exception("Детали ошибки:")
                break
    
    return all_cards


def flatten_card(card: Dict, cabinet_name: str, cabinet_id: int) -> Dict:
    """Преобразует карточку товара в плоскую структуру для Excel.
    
    Args:
        card: Карточка товара из API
        cabinet_name: Название кабинета
        cabinet_id: ID кабинета
    
    Returns:
        Словарь с плоской структурой всех полей
    """
    result = {
        "cabinet_name": cabinet_name,
        "cabinet_id": cabinet_id,
    }
    
    # Простые поля (строки, числа, булевы значения)
    simple_fields = [
        "nmID", "imtID", "nmUUID", "subjectID", "subjectName", 
        "vendorCode", "brand", "title", "description", "needKiz",
        "video", "createdAt", "updatedAt"
    ]
    
    for field in simple_fields:
        value = card.get(field)
        if value is not None:
            # Преобразуем сложные типы в строки для Excel
            if isinstance(value, (dict, list)):
                result[field] = json.dumps(value, ensure_ascii=False)
            else:
                result[field] = value
    
    # Обрабатываем вложенные объекты
    # photos - массив
    photos = card.get("photos", [])
    if photos:
        result["photos_count"] = len(photos)
        result["photos"] = json.dumps(photos, ensure_ascii=False)
    else:
        result["photos_count"] = 0
        result["photos"] = ""
    
    # wholesale - объект
    wholesale = card.get("wholesale", {})
    if wholesale:
        result["wholesale"] = json.dumps(wholesale, ensure_ascii=False)
    else:
        result["wholesale"] = ""
    
    # dimensions - объект
    dimensions = card.get("dimensions", {})
    if dimensions:
        result["dimensions"] = json.dumps(dimensions, ensure_ascii=False)
    else:
        result["dimensions"] = ""
    
    # characteristics - массив объектов
    characteristics = card.get("characteristics", [])
    if characteristics:
        result["characteristics_count"] = len(characteristics)
        result["characteristics"] = json.dumps(characteristics, ensure_ascii=False)
    else:
        result["characteristics_count"] = 0
        result["characteristics"] = ""
    
    # sizes - массив объектов (ВАЖНО для проверки наличия)
    sizes = card.get("sizes", [])
    if sizes:
        result["sizes_count"] = len(sizes)
        result["sizes"] = json.dumps(sizes, ensure_ascii=False)
        
        # Извлекаем информацию о размерах для анализа
        sizes_info = []
        for size in sizes:
            size_info = {
                "chrtID": size.get("chrtID"),
                "techSize": size.get("techSize"),
                "wbSize": size.get("wbSize"),
                "skus": size.get("skus", []),
                "price": size.get("price"),
                "discountedPrice": size.get("discountedPrice"),
            }
            sizes_info.append(size_info)
        result["sizes_details"] = json.dumps(sizes_info, ensure_ascii=False)
    else:
        result["sizes_count"] = 0
        result["sizes"] = ""
        result["sizes_details"] = ""
    
    # tags - массив
    tags = card.get("tags", [])
    if tags:
        result["tags_count"] = len(tags)
        result["tags"] = json.dumps(tags, ensure_ascii=False)
    else:
        result["tags_count"] = 0
        result["tags"] = ""
    
    # Добавляем все остальные поля, которые могут быть в карточке
    for key, value in card.items():
        if key not in result and key not in ["photos", "wholesale", "dimensions", "characteristics", "sizes", "tags"]:
            if isinstance(value, (dict, list)):
                result[f"_{key}"] = json.dumps(value, ensure_ascii=False)
            else:
                result[f"_{key}"] = value
    
    return result


async def parse_cabinet_articles(api_token: str, cabinet_name: str) -> List[Dict]:
    """Парсит все поля карточек товаров для одного кабинета через официальное API.
    
    Args:
        api_token: API токен продавца (с доступом к разделу "Контент")
        cabinet_name: Название кабинета (MAU, MAB, MMA, COSMO, DREAMLAB, BEAUTYLAB)
    
    Returns:
        Список словарей со всеми полями карточек
    """
    cabinet_id = CABINET_MAPPING.get(cabinet_name)
    if not cabinet_id:
        logger.error(f"❌ Неизвестный кабинет: {cabinet_name}")
        return []
    
    logger.info(f"🚀 Начинаем парсинг кабинета {cabinet_name} (ID: {cabinet_id})...")
    
    all_cards_flat = []
    
    try:
        # Получаем все карточки товаров через официальное API
        cards = await get_cabinet_cards(api_token, cabinet_name)
        
        logger.info(f"📦 Получено {len(cards)} карточек из кабинета {cabinet_name}")
        
        # Преобразуем каждую карточку в плоскую структуру
        for card in cards:
            flat_card = flatten_card(card, cabinet_name, cabinet_id)
            all_cards_flat.append(flat_card)
        
        logger.success(
            f"✅ Кабинет {cabinet_name}: обработано {len(all_cards_flat)} карточек"
        )
    
    except Exception as e:
        logger.error(f"❌ Ошибка при парсинге кабинета {cabinet_name}: {e}")
        logger.exception("Детали ошибки:")
    
    return all_cards_flat


def get_api_tokens() -> Dict[str, str]:
    """Загружает API токены для всех кабинетов из .env.
    
    Returns:
        Словарь {cabinet_name: api_token}
    """
    tokens = {}
    
    # Сначала пробуем общий токен
    common_token = os.getenv("WB_CONTENT_API_TOKEN")
    
    # Затем пробуем токены для каждого кабинета
    for cabinet_name in CABINET_MAPPING.keys():
        # Вариант 1: Токен из WB_API_KEY_{CABINET}
        token = os.getenv(f"WB_API_KEY_{cabinet_name}")
        
        # Вариант 2: Токен из WB_CONTENT_API_TOKEN_{CABINET}
        if not token:
            token = os.getenv(f"WB_CONTENT_API_TOKEN_{cabinet_name}")
        
        # Вариант 3: Используем общий токен
        if not token:
            token = common_token
        
        if token:
            tokens[cabinet_name] = token
        else:
            logger.warning(f"⚠️ Не найден токен для кабинета {cabinet_name}")
    
    return tokens


async def parse_all_cabinets() -> List[Dict]:
    """Парсит все поля карточек товаров по всем 6 кабинетам через официальное API.
    
    Returns:
        Список всех карточек со всеми полями
    """
    # Получаем токены для всех кабинетов
    api_tokens = get_api_tokens()
    
    if not api_tokens:
        logger.error("❌ Не найдены API токены в .env файле")
        logger.error("💡 Добавьте токены в .env:")
        logger.error("   WB_CONTENT_API_TOKEN=your_token_here")
        logger.error("   или")
        logger.error("   WB_API_KEY_MAU=your_token_here")
        logger.error("   WB_API_KEY_MAB=your_token_here")
        logger.error("   и т.д.")
        return []
    
    logger.info("=" * 70)
    logger.info("🚀 НАЧАЛО ПАРСИНГА ВСЕХ ПОЛЕЙ КАРТОЧЕК ТОВАРОВ ПО ВСЕМ КАБИНЕТАМ")
    logger.info("=" * 70)
    logger.info(f"📋 Кабинетов для обработки: {len(api_tokens)}")
    logger.info(f"🔑 Найдено токенов: {len(api_tokens)}")
    logger.info("")
    
    all_cards = []
    start_time = datetime.now()
    
    # Парсим кабинеты последовательно (соблюдаем rate limits)
    for cabinet_name, api_token in api_tokens.items():
        cabinet_cards = await parse_cabinet_articles(api_token, cabinet_name)
        all_cards.extend(cabinet_cards)
        logger.info("")  # Пустая строка для разделения
        
        # Небольшая задержка между кабинетами
        await asyncio.sleep(0.6)
    
    total_time = (datetime.now() - start_time).total_seconds()
    
    logger.info("=" * 70)
    logger.success(f"✅ ПАРСИНГ ЗАВЕРШЕН")
    logger.info(f"📊 Всего получено карточек: {len(all_cards)}")
    logger.info(f"⏱️  Время выполнения: {total_time:.2f} сек")
    logger.info("=" * 70)
    
    return all_cards


def save_to_excel(cards: List[Dict], output_file: Path):
    """Сохраняет все поля карточек в Excel файл.
    
    Args:
        cards: Список словарей со всеми полями карточек
        output_file: Путь к файлу для сохранения
    """
    if not cards:
        logger.warning("⚠️ Нет данных для сохранения")
        return
    
    try:
        import pandas as pd
        from openpyxl.utils import get_column_letter
        
        logger.info(f"💾 Сохраняем {len(cards)} записей в {output_file}...")
        
        # Создаем DataFrame
        df = pd.DataFrame(cards)
        
        # Определяем порядок столбцов (важные поля сначала)
        important_columns = [
            "cabinet_name", "cabinet_id", "nmID", "subjectName", "title", 
            "vendorCode", "brand", "subjectID", "sizes_count", "sizes_details"
        ]
        
        # Сортируем столбцы: сначала важные, потом остальные
        other_columns = [col for col in df.columns if col not in important_columns]
        column_order = [col for col in important_columns if col in df.columns] + sorted(other_columns)
        df = df[column_order]
        
        # Сохраняем в Excel
        with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='AllCards')
            
            # Настраиваем ширину столбцов
            worksheet = writer.sheets['AllCards']
            for idx, col in enumerate(df.columns, 1):
                column_letter = get_column_letter(idx)
                
                # Определяем максимальную длину в столбце
                max_length = max(
                    df[col].astype(str).map(len).max(),  # Максимальная длина данных
                    len(str(col))  # Длина заголовка
                )
                
                # Устанавливаем ширину (с небольшим запасом, но не слишком широко)
                worksheet.column_dimensions[column_letter].width = min(max_length + 2, 50)
        
        logger.success(f"✅ Файл сохранен: {output_file}")
        logger.info(f"📊 Всего записей: {len(cards)}")
        logger.info(f"📋 Всего столбцов: {len(df.columns)}")
        
        # Статистика по кабинетам
        if "cabinet_name" in df.columns:
            cabinet_stats = df["cabinet_name"].value_counts()
            logger.info("📈 Статистика по кабинетам:")
            for cabinet, count in cabinet_stats.items():
                logger.info(f"   • {cabinet}: {count} карточек")
        
        # Статистика по наличию (sizes_count)
        if "sizes_count" in df.columns:
            no_sizes = df[df["sizes_count"] == 0]
            with_sizes = df[df["sizes_count"] > 0]
            logger.info(f"📦 Товаров без размеров (sizes_count=0): {len(no_sizes)}")
            logger.info(f"📦 Товаров с размерами (sizes_count>0): {len(with_sizes)}")
    
    except ImportError:
        logger.error("❌ Ошибка: не установлены необходимые библиотеки")
        logger.info("Установите: pip install pandas openpyxl")
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка при сохранении в Excel: {e}")
        logger.exception("Детали ошибки:")
        raise


async def main():
    """Главная функция парсера."""
    try:
        # Парсим все кабинеты
        all_cards = await parse_all_cabinets()
        
        if not all_cards:
            logger.error("❌ Не получено ни одной карточки. Проверьте настройки и доступность API.")
            return
        
        # Сохраняем в отдельный Excel файл для анализа
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = project_root / f"Articles_Debug_{timestamp}.xlsx"
        save_to_excel(all_cards, output_file)
        
        logger.success("=" * 70)
        logger.success("✅ ПАРСИНГ УСПЕШНО ЗАВЕРШЕН")
        logger.success(f"📁 Результаты сохранены в: {output_file}")
        logger.success("=" * 70)
    
    except KeyboardInterrupt:
        logger.warning("⚠️ Парсинг прерван пользователем")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        logger.exception("Детали ошибки:")
        raise


if __name__ == "__main__":
    asyncio.run(main())
