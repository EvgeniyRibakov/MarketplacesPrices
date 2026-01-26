"""Парсер для получения актуальных артикулов и названий товаров по всем 6 кабинетам WB.

Использует официальное API: POST https://content-api.wildberries.ru/content/v2/get/cards/list
Сохраняет результаты в Articles.xlsx
"""
import asyncio
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional
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

# Обратный маппинг ID -> название
CABINET_ID_TO_NAME = {v: k for k, v in CABINET_MAPPING.items()}


async def get_cabinet_cards(api_token: str, cabinet_name: str, limit: int = 100) -> List[Dict]:
    """Получает список карточек товаров для кабинета через официальное API.
    
    Args:
        api_token: API токен продавца (с доступом к разделу "Контент")
        cabinet_name: Название кабинета (MAU, MAB, MMA, COSMO, DREAMLAB, BEAUTYLAB)
        limit: Количество товаров за запрос (максимум 100)
    
    Returns:
        Список карточек товаров с nm_id и названиями
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
                
                # Проверяем, есть ли еще данные для пагинации
                cursor_data = data.get("cursor", {})
                total = cursor_data.get("total", 0)
                
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
                    # Если нет карточек, прекращаем пагинацию
                    break
                
                # Соблюдаем rate limits (600мс между запросами)
                await asyncio.sleep(0.6)
                
            except Exception as e:
                logger.error(f"❌ Ошибка при запросе карточек для {cabinet_name}: {e}")
                logger.exception("Детали ошибки:")
                break
    
    return all_cards


async def parse_cabinet_articles(api_token: str, cabinet_name: str) -> List[Dict]:
    """Парсит артикулы и названия товаров для одного кабинета через официальное API.
    
    Args:
        api_token: API токен продавца (с доступом к разделу "Контент")
        cabinet_name: Название кабинета (MAU, MAB, MMA, COSMO, DREAMLAB, BEAUTYLAB)
    
    Returns:
        Список словарей с артикулами и названиями товаров:
        [
            {
                "nm_id": 12345678,
                "product_name": "Название товара",
                "cabinet_id": 224650,
                "cabinet_name": "COSMO"
            },
            ...
        ]
    """
    cabinet_id = CABINET_MAPPING.get(cabinet_name)
    if not cabinet_id:
        logger.error(f"❌ Неизвестный кабинет: {cabinet_name}")
        return []
    
    logger.info(f"🚀 Начинаем парсинг кабинета {cabinet_name} (ID: {cabinet_id})...")
    
    articles = []
    
    try:
        # Получаем все карточки товаров через официальное API
        cards = await get_cabinet_cards(api_token, cabinet_name)
        
        logger.info(f"📦 Получено {len(cards)} карточек из кабинета {cabinet_name}")
        
        # Извлекаем артикулы и названия
        for card in cards:
            nm_id = card.get("nmID") or card.get("nmId")  # Артикул товара
            product_name = card.get("imtName") or card.get("name") or ""  # Название товара
            
            if nm_id:
                articles.append({
                    "nm_id": nm_id,
                    "product_name": product_name,
                    "cabinet_id": cabinet_id,
                    "cabinet_name": cabinet_name
                })
            else:
                logger.warning(f"⚠️ Карточка без артикула (nmID) в кабинете {cabinet_name}")
        
        logger.success(
            f"✅ Кабинет {cabinet_name}: получено {len(articles)} артикулов "
            f"из {len(cards)} карточек"
        )
    
    except Exception as e:
        logger.error(f"❌ Ошибка при парсинге кабинета {cabinet_name}: {e}")
        logger.exception("Детали ошибки:")
    
    return articles


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
    """Парсит артикулы и названия товаров по всем 6 кабинетам через официальное API.
    
    Returns:
        Список всех артикулов со всех кабинетов
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
    logger.info("🚀 НАЧАЛО ПАРСИНГА АРТИКУЛОВ И НАЗВАНИЙ ТОВАРОВ ПО ВСЕМ КАБИНЕТАМ")
    logger.info("=" * 70)
    logger.info(f"📋 Кабинетов для обработки: {len(api_tokens)}")
    logger.info(f"🔑 Найдено токенов: {len(api_tokens)}")
    logger.info("")
    
    all_articles = []
    start_time = datetime.now()
    
    # Парсим кабинеты последовательно (соблюдаем rate limits)
    for cabinet_name, api_token in api_tokens.items():
        cabinet_articles = await parse_cabinet_articles(api_token, cabinet_name)
        all_articles.extend(cabinet_articles)
        logger.info("")  # Пустая строка для разделения
        
        # Небольшая задержка между кабинетами
        await asyncio.sleep(0.6)
    
    total_time = (datetime.now() - start_time).total_seconds()
    
    logger.info("=" * 70)
    logger.success(f"✅ ПАРСИНГ ЗАВЕРШЕН")
    logger.info(f"📊 Всего получено артикулов: {len(all_articles)}")
    logger.info(f"⏱️  Время выполнения: {total_time:.2f} сек")
    logger.info("=" * 70)
    
    return all_articles


def save_to_excel(articles: List[Dict], output_file: Path):
    """Сохраняет артикулы и названия товаров в Excel файл.
    
    Args:
        articles: Список словарей с артикулами и названиями
        output_file: Путь к файлу для сохранения
    """
    if not articles:
        logger.warning("⚠️ Нет данных для сохранения")
        return
    
    try:
        import pandas as pd
        from openpyxl.utils import get_column_letter
        
        logger.info(f"💾 Сохраняем {len(articles)} записей в {output_file}...")
        
        # Создаем DataFrame
        df = pd.DataFrame(articles)
        
        # Переименовываем столбцы для читаемости
        rename_mapping = {
            "nm_id": "Артикул",
            "product_name": "Название товара",
            "cabinet_id": "ID кабинета",
            "cabinet_name": "Кабинет"
        }
        
        for old_name, new_name in rename_mapping.items():
            if old_name in df.columns:
                df = df.rename(columns={old_name: new_name})
        
        # Определяем порядок столбцов
        column_order = ["Артикул", "Название товара", "Кабинет", "ID кабинета"]
        df = df[[col for col in column_order if col in df.columns]]
        
        # Сохраняем в Excel
        with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Articles')
            
            # Настраиваем ширину столбцов
            worksheet = writer.sheets['Articles']
            for idx, col in enumerate(df.columns, 1):
                column_letter = get_column_letter(idx)
                
                # Определяем максимальную длину в столбце
                max_length = max(
                    df[col].astype(str).map(len).max(),  # Максимальная длина данных
                    len(str(col))  # Длина заголовка
                )
                
                # Устанавливаем ширину (с небольшим запасом)
                worksheet.column_dimensions[column_letter].width = min(max_length + 2, 100)
        
        logger.success(f"✅ Файл сохранен: {output_file}")
        logger.info(f"📊 Всего записей: {len(articles)}")
        
        # Статистика по кабинетам
        if "Кабинет" in df.columns:
            cabinet_stats = df["Кабинет"].value_counts()
            logger.info("📈 Статистика по кабинетам:")
            for cabinet, count in cabinet_stats.items():
                logger.info(f"   • {cabinet}: {count} артикулов")
        
        # Проверка на дубликаты артикулов
        if "Артикул" in df.columns:
            duplicates = df[df.duplicated(subset=["Артикул"], keep=False)]
            if not duplicates.empty:
                logger.warning(f"⚠️ Найдено {len(duplicates)} дубликатов артикулов (товары в нескольких кабинетах)")
            else:
                logger.info("✅ Дубликатов артикулов не найдено")
    
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
        all_articles = await parse_all_cabinets()
        
        if not all_articles:
            logger.error("❌ Не получено ни одного артикула. Проверьте настройки и доступность API.")
            return
        
        # Сохраняем в Articles.xlsx
        output_file = project_root / "Articles.xlsx"
        save_to_excel(all_articles, output_file)
        
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
