"""Модуль для работы с официальным Ozon Seller API."""
import asyncio
import time
from typing import List, Dict, Optional
from curl_cffi.requests import AsyncSession
from loguru import logger


class OzonSellerAPI:
    """Клиент для работы с официальным Ozon Seller API."""
    
    BASE_URL = "https://api-seller.ozon.ru"
    
    def __init__(self, client_id: int, api_key: str, request_delay: float = 0.5, max_concurrent: int = 5):
        """Инициализация клиента.
        
        Args:
            client_id: Client ID продавца (число)
            api_key: API ключ продавца
            request_delay: Задержка между запросами (секунды) - безопасное значение 0.5
            max_concurrent: Максимальное количество параллельных запросов
        """
        self.client_id = client_id
        self.api_key = api_key
        self.request_delay = request_delay
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.session: Optional[AsyncSession] = None
    
    async def __aenter__(self):
        """Асинхронный контекстный менеджер - вход."""
        # Создаем сессию curl_cffi с эмуляцией Chrome 131
        self.session = AsyncSession(
            impersonate="chrome131",
            timeout=30,
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Асинхронный контекстный менеджер - выход."""
        if self.session:
            await self.session.close()
    
    def _get_headers(self) -> Dict[str, str]:
        """Формирует заголовки для API запроса."""
        return {
            'Client-Id': str(self.client_id),
            'Api-Key': self.api_key,
            'Content-Type': 'application/json'
        }
    
    async def fetch_product_prices(self, offer_ids: Optional[List[str]] = None, 
                                   product_ids: Optional[List[int]] = None,
                                   limit: int = 1000) -> List[Dict]:
        """Получает цены товаров через /v5/product/info/prices.
        
        ИСПРАВЛЕНИЕ: Если не переданы фильтры (offer_ids и product_ids), 
        возвращает ВСЕ товары продавца (visibility: ALL).
        
        Args:
            offer_ids: Список offer_id товаров (артикулы продавца). Если None - все товары
            product_ids: Список product_id товаров (SKU Ozon). Если None - все товары
            limit: Количество товаров за запрос (max 1000)
        
        Returns:
            Список товаров с ценами
        """
        url = f"{self.BASE_URL}/v5/product/info/prices"
        all_results = []
        cursor = ""
        page = 1
        
        # Определяем режим работы
        if offer_ids or product_ids:
            logger.info(
                f"🚀 Запрос цен товаров из Seller API (с фильтрами): "
                f"offer_ids={len(offer_ids) if offer_ids else 0}, "
                f"product_ids={len(product_ids) if product_ids else 0}"
            )
        else:
            logger.info(
                f"🚀 Запрос ВСЕХ товаров продавца из Seller API (без фильтров)"
            )
        
        while True:
            start_time = time.time()
            
            async with self.semaphore:
                try:
                    await asyncio.sleep(self.request_delay)
                    
                    # Формируем фильтр
                    filter_data = {'visibility': 'ALL'}  # Получаем все товары (видимые и невидимые)
                    
                    if offer_ids:
                        filter_data['offer_id'] = [str(x) for x in offer_ids]
                    if product_ids:
                        filter_data['product_id'] = [str(x) for x in product_ids]
                    
                    payload = {
                        "cursor": cursor,
                        "filter": filter_data,
                        "limit": limit
                    }
                    
                    logger.debug(f"📥 Страница {page}: отправка запроса к Seller API...")
                    
                    response = await self.session.post(
                        url,
                        headers=self._get_headers(),
                        json=payload
                    )
                    
                    elapsed_time = time.time() - start_time
                    
                    if response.status_code == 200:
                        data = response.json()
                        
                        result_data = data.get("result", {})
                        items = result_data.get("items", [])
                        next_cursor = result_data.get("cursor", "")
                        
                        all_results.extend(items)
                        
                        logger.info(
                            f"✅ Страница {page}: получено {len(items)} товаров "
                            f"за {elapsed_time:.2f} сек. Всего собрано: {len(all_results)}"
                        )
                        
                        # Проверяем, есть ли следующая страница
                        if not next_cursor or not items:
                            break
                        
                        cursor = next_cursor
                        page += 1
                        
                    elif response.status_code == 429:
                        # Rate limiting
                        wait_time = 2.0
                        logger.warning(
                            f"⚠️ Rate limit (429) на странице {page}. "
                            f"Ожидание {wait_time} сек..."
                        )
                        await asyncio.sleep(wait_time)
                        continue
                        
                    else:
                        logger.error(
                            f"❌ Ошибка на странице {page}: статус {response.status_code}. "
                            f"Ответ: {response.text[:500]}"
                        )
                        break
                        
                except asyncio.TimeoutError:
                    elapsed_time = time.time() - start_time
                    logger.error(
                        f"❌ Таймаут при запросе страницы {page} "
                        f"(время ожидания: {elapsed_time:.2f} сек)"
                    )
                    break
                except Exception as e:
                    elapsed_time = time.time() - start_time
                    logger.error(
                        f"❌ Исключение при запросе страницы {page} "
                        f"(время: {elapsed_time:.2f} сек): {e}"
                    )
                    logger.exception("Детали исключения:")
                    break
        
        logger.success(
            f"✅ Seller API: получено {len(all_results)} товаров за {page} страниц"
        )
        
        return all_results
    
    @staticmethod
    def parse_price_item(item: Dict) -> Dict:
        """Парсит товар из ответа /v5/product/info/prices.
        
        Returns:
            Словарь с данными о ценах товара
        """
        product_id = item.get("product_id")
        offer_id = item.get("offer_id")
        
        # Извлекаем цены
        price_data = item.get("price", {})
        old_price_data = item.get("old_price", {})
        
        # Цена продавца (без акций)
        seller_price = float(price_data.get("price", 0)) if price_data.get("price") else None
        
        # Зачёркнутая цена
        old_price = float(old_price_data.get("old_price", 0)) if old_price_data.get("old_price") else None
        
        # Минимальная цена (если есть)
        min_price_data = item.get("min_price", {})
        min_price = float(min_price_data.get("min_price", 0)) if min_price_data.get("min_price") else None
        
        return {
            "product_id": product_id,
            "offer_id": offer_id,
            "seller_price": seller_price,
            "old_price": old_price,
            "min_price": min_price,
            "currency": price_data.get("currency_code", "RUB"),
            "source": "seller_api"
        }
