"""Модуль для работы с официальным Content API Wildberries.

Эндпоинт: GET /content/v2/object/all
Возвращает список родительских категорий и их предметов с ID.
"""
import asyncio
import time
from typing import List, Dict, Optional
from urllib.parse import urlencode
from curl_cffi.requests import AsyncSession
from loguru import logger


class WBContentAPIError(Exception):
    """Базовое исключение для ошибок Content API."""
    pass


class WBContentAPIAuthError(WBContentAPIError):
    """Ошибка авторизации - токен не имеет доступа к Content API."""
    pass


class WBContentAPI:
    """Клиент для работы с официальным Content API Wildberries.
    
    Эндпоинт content/v2/object/all возвращает список категорий и предметов.
    """
    
    BASE_URL = "https://content-api.wildberries.ru/content/v2/object/all"
    
    # Rate limits согласно документации
    RATE_LIMIT_REQUESTS = 100  # запросов в минуту
    RATE_LIMIT_INTERVAL = 0.6  # секунд между запросами (600 миллисекунд)
    RATE_LIMIT_BURST = 5  # всплеск запросов
    
    def __init__(self, api_token: str, request_delay: float = 0.6, max_concurrent: int = 1):
        """Инициализация клиента.
        
        Args:
            api_token: API токен от аккаунта продавца (с доступом к разделу "Контент")
            request_delay: Задержка между запросами (секунды). По умолчанию 0.6 (600мс)
            max_concurrent: Максимальное количество параллельных запросов (по умолчанию 1)
        """
        if not api_token:
            raise ValueError("API токен обязателен для работы с Content API")
        
        self.api_token = api_token
        self.request_delay = max(request_delay, self.RATE_LIMIT_INTERVAL)  # Не меньше минимального интервала
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.session: Optional[AsyncSession] = None
        
        # Счетчик запросов для rate limiting
        self._request_count = 0
        self._last_request_time = 0
    
    async def __aenter__(self):
        """Асинхронный контекстный менеджер - вход."""
        self.session = AsyncSession(
            impersonate="chrome131",
            timeout=30,
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Асинхронный контекстный менеджер - выход."""
        if self.session:
            await self.session.close()
    
    async def _rate_limit(self):
        """Соблюдает rate limits API.
        
        Лимиты:
        - 100 запросов в минуту
        - 600 миллисекунд между запросами
        - Всплеск 5 запросов
        """
        current_time = time.time()
        time_since_last = current_time - self._last_request_time
        
        # Если прошло меньше минимального интервала, ждем
        if time_since_last < self.request_delay:
            wait_time = self.request_delay - time_since_last
            await asyncio.sleep(wait_time)
        
        self._last_request_time = time.time()
        self._request_count += 1
    
    async def get_objects(
        self,
        locale: str = "ru",
        limit: int = 1000,
        offset: int = 0,
        parent_id: Optional[int] = None,
        name: Optional[str] = None
    ) -> List[Dict]:
        """Получает список категорий и предметов.
        
        Args:
            locale: Язык полей ответа (ru, en, zh). По умолчанию ru
            limit: Количество предметов (максимум 1000). По умолчанию 1000
            offset: Смещение для пагинации. По умолчанию 0
            parent_id: ID родительской категории для фильтрации. Опционально
            name: Поиск по названию предмета (по подстроке). Опционально
        
        Returns:
            Список словарей с категориями/предметами:
            [
                {
                    "name": "Название категории",
                    "id": 212,
                    "isVisible": true
                },
                ...
            ]
        
        Raises:
            ValueError: Если limit > 1000
            Exception: При ошибке запроса
        """
        if limit > 1000:
            raise ValueError("limit не может быть больше 1000")
        
        async with self.semaphore:
            await self._rate_limit()
            
            # Формируем параметры запроса
            params = {
                "locale": locale,
                "limit": limit,
                "offset": offset
            }
            
            if parent_id is not None:
                params["parentID"] = parent_id
            
            if name:
                params["name"] = name
            
            url = f"{self.BASE_URL}?{urlencode(params)}"
            
            headers = {
                "Authorization": self.api_token,  # Токен без префиксов
                "Content-Type": "application/json"
            }
            
            try:
                logger.debug(f"Запрос к Content API: {url}")
                response = await self.session.get(url, headers=headers)
                
                # Специальная обработка ошибки 401 (Unauthorized)
                if response.status_code == 401:
                    error_data = {}
                    try:
                        error_data = response.json()
                    except:
                        error_data = {"detail": response.text[:200]}
                    
                    detail = error_data.get("detail", "Unknown error")
                    code = error_data.get("code", "")
                    
                    logger.error("=" * 70)
                    logger.error("❌ ОШИБКА АВТОРИЗАЦИИ (401 Unauthorized)")
                    logger.error("=" * 70)
                    logger.error(f"Причина: {detail}")
                    if code:
                        logger.error(f"Код ошибки: {code}")
                    logger.error("")
                    logger.error("🔍 ПРОБЛЕМА: Токен не имеет доступа к разделу 'Контент' API")
                    logger.error("")
                    logger.error("💡 РЕШЕНИЕ:")
                    logger.error("   1. Перейдите в личный кабинет продавца WB")
                    logger.error("   2. Интеграции → Создать токен")
                    logger.error("   3. Обязательно выберите раздел доступа: 'Контент'")
                    logger.error("   4. Скопируйте новый токен и добавьте в .env:")
                    logger.error("      WB_CONTENT_API_TOKEN=your_new_token_here")
                    logger.error("")
                    logger.error("⚠️  ВАЖНО: Токены для других разделов (discounts, prices и т.д.)")
                    logger.error("   не работают с Content API. Нужен отдельный токен с доступом к 'Контент'")
                    logger.error("=" * 70)
                    
                    raise WBContentAPIAuthError(
                        f"Токен не имеет доступа к Content API. "
                        f"Создайте новый токен с разделом доступа 'Контент'. "
                        f"Детали: {detail}"
                    )
                
                response.raise_for_status()
                
                data = response.json()
                
                logger.debug(
                    f"Получено {len(data) if isinstance(data, list) else 0} категорий "
                    f"(offset={offset}, limit={limit})"
                )
                
                return data if isinstance(data, list) else []
                
            except WBContentAPIAuthError:
                # Пробрасываем ошибку авторизации дальше
                raise
            except Exception as e:
                logger.error(f"Ошибка при запросе к Content API: {e}")
                logger.error(f"URL: {url}")
                logger.error(f"Response status: {response.status_code if 'response' in locals() else 'N/A'}")
                if 'response' in locals():
                    try:
                        error_text = response.text[:500]
                        logger.error(f"Response text: {error_text}")
                    except:
                        pass
                raise WBContentAPIError(f"Ошибка при запросе к Content API: {e}") from e
    
    async def get_all_objects(
        self,
        locale: str = "ru",
        parent_id: Optional[int] = None,
        name: Optional[str] = None
    ) -> List[Dict]:
        """Получает все категории/предметы с автоматической пагинацией.
        
        Args:
            locale: Язык полей ответа (ru, en, zh). По умолчанию ru
            parent_id: ID родительской категории для фильтрации. Опционально
            name: Поиск по названию предмета. Опционально
        
        Returns:
            Список всех категорий/предметов
        """
        all_objects = []
        offset = 0
        limit = 1000  # Максимальное значение
        
        logger.info("Начинаем получение всех категорий/предметов с пагинацией...")
        
        while True:
            try:
                batch = await self.get_objects(
                    locale=locale,
                    limit=limit,
                    offset=offset,
                    parent_id=parent_id,
                    name=name
                )
                
                if not batch:
                    break
                
                all_objects.extend(batch)
                logger.info(f"Получено {len(batch)} категорий (всего: {len(all_objects)})")
                
                # Если получили меньше limit, значит это последняя страница
                if len(batch) < limit:
                    break
                
                offset += limit
                
            except WBContentAPIAuthError:
                # Ошибка авторизации - пробрасываем дальше, не продолжаем
                raise
            except Exception as e:
                logger.error(f"Ошибка при получении batch (offset={offset}): {e}")
                # Если это первая страница и произошла ошибка, пробрасываем её
                if offset == 0:
                    raise
                # Иначе просто прерываем пагинацию
                break
        
        if all_objects:
            logger.success(f"Всего получено категорий/предметов: {len(all_objects)}")
        else:
            logger.warning("Не получено ни одной категории. Возможно, произошла ошибка.")
        
        return all_objects
    
    async def search_by_name(self, name: str, locale: str = "ru") -> List[Dict]:
        """Поиск категорий/предметов по названию.
        
        Args:
            name: Название для поиска (работает по подстроке)
            locale: Язык полей ответа. По умолчанию ru
        
        Returns:
            Список найденных категорий/предметов
        """
        return await self.get_all_objects(locale=locale, name=name)
    
    async def get_by_parent_id(self, parent_id: int, locale: str = "ru") -> List[Dict]:
        """Получает все предметы конкретной родительской категории.
        
        Args:
            parent_id: ID родительской категории
            locale: Язык полей ответа. По умолчанию ru
        
        Returns:
            Список предметов родительской категории
        """
        return await self.get_all_objects(locale=locale, parent_id=parent_id)
