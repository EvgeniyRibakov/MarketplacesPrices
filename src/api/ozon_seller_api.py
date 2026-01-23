"""Модуль для работы с официальным Ozon Seller API."""
import asyncio
import time
from typing import List, Dict, Optional
from curl_cffi.requests import AsyncSession
from loguru import logger


class OzonSellerAPI:
    """Клиент для работы с официальным Ozon Seller API."""
    
    BASE_URL = "https://api-seller.ozon.ru"
    
    def __init__(self, client_id: int, api_key: str, request_delay: float = 0.5, max_concurrent: int = 20):
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
                    
                    # Формируем фильтр (обязательный параметр)
                    filter_data = {}
                    
                    if offer_ids:
                        filter_data['offer_id'] = [str(x) for x in offer_ids]
                    if product_ids:
                        filter_data['product_id'] = [str(x) for x in product_ids]
                    
                    # Если нет конкретных фильтров, используем visibility: ALL для получения всех товаров
                    if not filter_data:
                        filter_data = {'visibility': 'ALL'}
                    
                    # Формируем payload
                    payload = {
                        "filter": filter_data,
                        "limit": limit
                    }
                    
                    # Добавляем cursor только если он есть (для пагинации)
                    if cursor:
                        payload["cursor"] = cursor
                    
                    logger.debug(f"📥 Страница {page}: отправка запроса к Seller API...")
                    logger.debug(f"📋 Payload: {payload}")
                    
                    response = await self.session.post(
                        url,
                        headers=self._get_headers(),
                        json=payload
                    )
                    
                    elapsed_time = time.time() - start_time
                    
                    if response.status_code == 200:
                        data = response.json()
                        
                        # Логируем структуру ответа для диагностики
                        logger.debug(f"🔍 Структура ответа API: {list(data.keys())}")
                        if 'result' in data:
                            logger.debug(f"🔍 Структура result: {list(data['result'].keys())}")
                        
                        # API может возвращать items либо в data['items'], либо в data['result']['items']
                        result_data = data.get("result", {})
                        if result_data:
                            # Стандартная структура: data['result']['items']
                            items = result_data.get("items", [])
                            next_cursor = result_data.get("cursor", "")
                            
                            # Логируем если items пустой
                            if not items:
                                logger.warning(
                                    f"⚠️ Страница {page}: items пустой. "
                                    f"Структура result: {list(result_data.keys())}"
                                )
                                # Логируем полный ответ для диагностики (первые 1000 символов)
                                logger.debug(f"🔍 Полный ответ API (первые 1000 символов): {str(data)[:1000]}")
                        else:
                            # Альтернативная структура: data['items'] напрямую
                            items = data.get("items", [])
                            next_cursor = data.get("cursor", "")
                            
                            if not items:
                                logger.warning(
                                    f"⚠️ Страница {page}: items пустой в корне ответа. "
                                    f"Структура data: {list(data.keys())}"
                                )
                        
                        # Логируем структуру ответа, если товаров нет
                        if not items:
                            logger.warning(
                                f"⚠️ Страница {page}: получено 0 товаров. "
                                f"Структура ответа: result={result_data}"
                            )
                            logger.debug(f"📥 Полный ответ API: {data}")
                        
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
    
    async def fetch_products_by_sku(self, sku_list: List[int], limit: int = 1000) -> List[Dict]:
        """Получает информацию о товарах по SKU из entrypoint API.
        
        Использует /v3/product/info/list для сопоставления:
        - sku (из entrypoint API) → product_id и offer_id (из Seller API)
        
        Args:
            sku_list: Список SKU из entrypoint API (глобальные идентификаторы товаров)
            limit: Максимальное количество товаров за запрос (до 1000)
        
        Returns:
            Список товаров с product_id, offer_id и другими данными
        """
        url = f"{self.BASE_URL}/v3/product/info/list"
        all_results = []
        
        # Ограничение: суммарно до 1000 элементов в массивах
        # Разбиваем на батчи по 1000 SKU
        batch_size = limit
        total_batches = (len(sku_list) + batch_size - 1) // batch_size
        
        logger.info(
            f"🚀 Запрос информации о товарах по SKU: {len(sku_list)} SKU, "
            f"{total_batches} батч(ей)"
        )
        
        for batch_num in range(total_batches):
            start_idx = batch_num * batch_size
            end_idx = min(start_idx + batch_size, len(sku_list))
            batch_sku = sku_list[start_idx:end_idx]
            
            logger.debug(
                f"📥 Батч {batch_num + 1}/{total_batches}: "
                f"SKU {start_idx + 1}-{end_idx} из {len(sku_list)}"
            )
            
            async with self.semaphore:
                try:
                    await asyncio.sleep(self.request_delay)
                    
                    # Формируем payload согласно документации
                    payload = {
                        "offer_id": [],
                        "product_id": [],
                        "sku": [str(sku) for sku in batch_sku]  # SKU из entrypoint API
                    }
                    
                    response = await self.session.post(
                        url,
                        headers=self._get_headers(),
                        json=payload
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        
                        # API может вернуть items в двух форматах:
                        # 1. data['result']['items'] (стандартный)
                        # 2. data['items'] (прямо в корне)
                        result_data = data.get("result", {})
                        items = result_data.get("items", [])
                        
                        # Если items не найдены в result, проверяем корень
                        if not items and "items" in data:
                            items = data.get("items", [])
                            logger.debug(
                                f"  📋 Батч {batch_num + 1}: items найдены в корне ответа (не в result)"
                            )
                        
                        if items:
                            all_results.extend(items)
                            logger.success(
                                f"  ✓ Батч {batch_num + 1}: получено {len(items)} товаров"
                            )
                        else:
                            logger.warning(
                                f"  ⚠️ Батч {batch_num + 1}: товары не найдены "
                                f"(SKU не принадлежат вашему кабинету)"
                            )
                            # Логируем детали для диагностики
                            logger.debug(f"  📋 Payload (первые 3 SKU): {payload['sku'][:3] if payload.get('sku') else 'N/A'}")
                            logger.debug(f"  📋 Структура ответа: {list(data.keys())}")
                            if 'result' in data:
                                logger.debug(f"  📋 Структура result: {list(data['result'].keys())}")
                            logger.debug(f"  📋 Полный ответ (первые 500 символов): {str(data)[:500]}")
                    elif response.status_code == 400:
                        logger.warning(
                            f"⚠️ Батч {batch_num + 1}: ошибка 400 - проверьте формат запроса"
                        )
                        try:
                            error_data = response.json()
                            logger.debug(f"  Детали ошибки: {error_data}")
                        except:
                            pass
                    elif response.status_code == 401:
                        logger.error(
                            f"❌ Батч {batch_num + 1}: ошибка 401 - неверный Client-Id или Api-Key"
                        )
                        break
                    else:
                        logger.warning(
                            f"⚠️ Батч {batch_num + 1}: статус {response.status_code}"
                        )
                        
                except Exception as e:
                    logger.error(
                        f"❌ Ошибка при запросе батча {batch_num + 1}: {e}"
                    )
                    logger.exception("Детали ошибки:")
                    continue
        
        logger.success(
            f"✅ Получено информации о {len(all_results)} товарах из {len(sku_list)} SKU"
        )
        
        return all_results
    
    async def fetch_products_by_product_id(self, product_id_list: List[int], limit: int = 1000) -> List[Dict]:
        """Получает информацию о товарах по product_id из Seller API.
        
        Использует /v3/product/info/list для получения названий и других данных:
        - product_id (из Seller API) → name, offer_id и другие данные
        
        Args:
            product_id_list: Список product_id из Seller API
            limit: Максимальное количество товаров за запрос (до 1000)
        
        Returns:
            Список товаров с name, offer_id и другими данными
        """
        url = f"{self.BASE_URL}/v3/product/info/list"
        all_results = []
        
        # Ограничение: суммарно до 1000 элементов в массивах
        # Разбиваем на батчи по 1000 product_id
        batch_size = limit
        total_batches = (len(product_id_list) + batch_size - 1) // batch_size
        
        logger.info(
            f"🚀 Запрос информации о товарах по product_id: {len(product_id_list)} товаров, "
            f"{total_batches} батч(ей)"
        )
        
        for batch_num in range(total_batches):
            start_idx = batch_num * batch_size
            end_idx = min(start_idx + batch_size, len(product_id_list))
            batch_product_ids = product_id_list[start_idx:end_idx]
            
            logger.debug(
                f"📥 Батч {batch_num + 1}/{total_batches}: "
                f"product_id {start_idx + 1}-{end_idx} из {len(product_id_list)}"
            )
            
            async with self.semaphore:
                try:
                    await asyncio.sleep(self.request_delay)
                    
                    # Формируем payload согласно документации
                    payload = {
                        "offer_id": [],
                        "product_id": [str(pid) for pid in batch_product_ids],  # product_id из Seller API
                        "sku": []
                    }
                    
                    response = await self.session.post(
                        url,
                        headers=self._get_headers(),
                        json=payload
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        
                        # API может вернуть items в двух форматах:
                        # 1. data['result']['items'] (стандартный)
                        # 2. data['items'] (прямо в корне)
                        result_data = data.get("result", {})
                        items = result_data.get("items", [])
                        
                        # Если items не найдены в result, проверяем корень
                        if not items and "items" in data:
                            items = data.get("items", [])
                            logger.debug(
                                f"  📋 Батч {batch_num + 1}: items найдены в корне ответа (не в result)"
                            )
                        
                        if items:
                            # Парсим каждый товар
                            parsed_items = [self.parse_product_info_item(item) for item in items]
                            all_results.extend(parsed_items)
                            logger.success(
                                f"  ✓ Батч {batch_num + 1}: получено {len(items)} товаров"
                            )
                        else:
                            logger.warning(
                                f"  ⚠️ Батч {batch_num + 1}: товары не найдены"
                            )
                    elif response.status_code == 400:
                        logger.warning(
                            f"⚠️ Батч {batch_num + 1}: ошибка 400 - проверьте формат запроса"
                        )
                    elif response.status_code == 401:
                        logger.error(
                            f"❌ Батч {batch_num + 1}: ошибка 401 - неверный Client-Id или Api-Key"
                        )
                        break
                    else:
                        logger.warning(
                            f"⚠️ Батч {batch_num + 1}: статус {response.status_code}"
                        )
                        
                except Exception as e:
                    logger.error(
                        f"❌ Ошибка при запросе батча {batch_num + 1}: {e}"
                    )
                    logger.exception("Детали ошибки:")
                    continue
        
        logger.success(
            f"✅ Получено информации о {len(all_results)} товарах из {len(product_id_list)} product_id"
        )
        
        return all_results
    
    @staticmethod
    def parse_product_info_item(item: Dict) -> Dict:
        """Парсит товар из ответа /v3/product/info/list.
        
        Returns:
            Словарь с данными о товаре: product_id, offer_id, sku
        """
        return {
            "product_id": item.get("id"),  # ID товара в кабинете продавца
            "offer_id": item.get("offer_id"),  # Артикул продавца
            "sku": item.get("sku"),  # Глобальный SKU (FBS/FBO)
            "fbs_sku": item.get("fbs_sku"),  # SKU для FBS (если применимо)
            "fbo_sku": item.get("fbo_sku"),  # SKU для FBO (если применимо)
            "name": item.get("name"),  # Название товара
            "source": "seller_api_v3"
        }
    
    @staticmethod
    def parse_price_item(item: Dict) -> Dict:
        """Парсит товар из ответа /v5/product/info/prices.
        
        Returns:
            Словарь с данными о ценах товара
        """
        from loguru import logger
        
        product_id = item.get("product_id")
        offer_id = item.get("offer_id")
        
        # Извлекаем цены
        price_data = item.get("price", {})
        old_price_data = item.get("old_price", {})
        
        # Цена продавца (без акций)
        seller_price = float(price_data.get("price", 0)) if price_data.get("price") else None
        
        # Зачёркнутая цена: проверяем разные варианты структуры
        old_price = None
        
        # Вариант 1: old_price - это объект с полем old_price
        if isinstance(old_price_data, dict):
            old_price_val = old_price_data.get("old_price")
            if old_price_val is not None:
                try:
                    old_price = float(old_price_val)
                except (ValueError, TypeError):
                    pass
        
        # Вариант 2: old_price - это число напрямую (если API вернул не объект)
        if old_price is None and isinstance(old_price_data, (int, float)):
            old_price = float(old_price_data)
        
        # Вариант 3: old_price может быть в price_data (проверяем для диагностики)
        if old_price is None and isinstance(price_data, dict):
            old_price_in_price = price_data.get("old_price")
            if old_price_in_price is not None:
                try:
                    old_price = float(old_price_in_price)
                except (ValueError, TypeError):
                    pass
        
        # Отладочное логирование для товаров с seller_price, но без old_price
        if seller_price is not None and old_price is None:
            logger.debug(
                f"🔍 Товар {product_id} (offer_id={offer_id}): есть seller_price={seller_price}, "
                f"но нет old_price. Структура: old_price_data={old_price_data}, "
                f"price_data.keys()={list(price_data.keys()) if isinstance(price_data, dict) else 'N/A'}"
            )
        
        # Минимальная цена (если есть) - больше не используем, но оставляем для совместимости
        min_price_data = item.get("min_price", {})
        min_price = float(min_price_data.get("min_price", 0)) if min_price_data.get("min_price") else None
        
        return {
            "product_id": product_id,
            "offer_id": offer_id,
            "seller_price": seller_price,
            "old_price": old_price,
            "min_price": min_price,
            "currency": price_data.get("currency_code", "RUB") if isinstance(price_data, dict) else "RUB",
            "source": "seller_api"
        }
