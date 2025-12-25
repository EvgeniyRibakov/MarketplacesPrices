"""API клиент для Wildberries."""
import time
from typing import Dict, List, Optional
from loguru import logger
import requests


class WildberriesAPI:
    """Клиент для работы с официальным API Wildberries."""
    
    # Базовый URL для работы с товарами (suppliers API)
    BASE_URL = "https://suppliers-api.wildberries.ru"
    
    # Базовый URL для получения цен и скидок (discounts-prices API)
    PRICES_BASE_URL = "https://discounts-prices-api.wildberries.ru"
    
    def __init__(self, api_key: str, request_delay: float = 0.5):
        """Инициализация API клиента.
        
        Args:
            api_key: API ключ Wildberries
            request_delay: Задержка между запросами (секунды)
        """
        self.api_key = api_key
        self.request_delay = request_delay
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": api_key,
            "Content-Type": "application/json",
        })
    
    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        json_data: Optional[Dict] = None,
        timeout: int = 30,
    ) -> Optional[Dict]:
        """Выполнить запрос к API.
        
        Args:
            method: HTTP метод (GET, POST, etc.)
            endpoint: Endpoint API
            params: Параметры запроса
            json_data: JSON данные для POST запросов
            timeout: Таймаут запроса
            
        Returns:
            Ответ API или None в случае ошибки
        """
        url = f"{self.BASE_URL}{endpoint}"
        
        try:
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                json=json_data,
                timeout=timeout,
            )
            response.raise_for_status()
            
            # Задержка между запросами
            time.sleep(self.request_delay)
            
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка запроса к WB API {endpoint}: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Статус: {e.response.status_code}, Ответ: {e.response.text}")
            return None
    
    def get_content(self, limit: int = 1000, offset: int = 0) -> Optional[List[Dict]]:
        """Получить список товаров (контент).
        
        Args:
            limit: Количество товаров на странице (макс 1000)
            offset: Смещение для пагинации
            
        Returns:
            Список товаров или None
        """
        endpoint = "/content/v1/cards/cursor/list"
        params = {
            "limit": min(limit, 1000),
            "offset": offset,
        }
        
        result = self._make_request("POST", endpoint, json_data=params)
        
        if result and "data" in result:
            return result["data"].get("cards", [])
        
        return None
    
    def get_all_products(self) -> List[Dict]:
        """Получить все товары из кабинета.
        
        Returns:
            Список всех товаров
        """
        all_products = []
        offset = 0
        limit = 1000
        
        logger.info("Начинаем получение списка товаров из WB...")
        
        while True:
            products = self.get_content(limit=limit, offset=offset)
            
            if not products:
                break
            
            all_products.extend(products)
            logger.info(f"Получено товаров: {len(all_products)}")
            
            if len(products) < limit:
                break
            
            offset += limit
        
        logger.success(f"Всего получено товаров: {len(all_products)}")
        return all_products
    
    def get_prices_by_articles(self, articles: List[str]) -> Optional[List[Dict]]:
        """Получить цены для товаров по артикулам.
        
        Args:
            articles: Список артикулов товаров (до 100 артикулов за запрос)
            
        Returns:
            Список товаров с ценами или None
        """
        endpoint = "/api/v2/list/goods/filter"
        
        # Разбиваем на батчи по 100 артикулов (лимит API)
        batch_size = 100
        all_results = []
        
        for i in range(0, len(articles), batch_size):
            batch = articles[i:i + batch_size]
            
            json_data = {
                "vendorCodes": batch
            }
            
            # Используем PRICES_BASE_URL для запроса цен
            url = f"{self.PRICES_BASE_URL}{endpoint}"
            
            try:
                response = self.session.request(
                    method="POST",
                    url=url,
                    json=json_data,
                    timeout=30,
                )
                response.raise_for_status()
                
                result = response.json()
                if result and "data" in result:
                    all_results.extend(result["data"])
                
                # Задержка между запросами
                time.sleep(self.request_delay)
                
            except requests.exceptions.RequestException as e:
                logger.error(f"Ошибка запроса цен по артикулам: {e}")
                if hasattr(e, 'response') and e.response is not None:
                    logger.error(f"Статус: {e.response.status_code}, Ответ: {e.response.text}")
                continue
        
        return all_results if all_results else None
    
    def get_prices_by_nm_id(self, nm_id: int) -> Optional[Dict]:
        """Получить цены для всех размеров товара по nm_id.
        
        Args:
            nm_id: Номенклатура товара
            
        Returns:
            Информация о размерах с ценами или None
        """
        endpoint = f"/api/v2/list/goods/size/nm"
        
        url = f"{self.PRICES_BASE_URL}{endpoint}"
        params = {"nm": nm_id}
        
        try:
            response = self.session.request(
                method="GET",
                url=url,
                params=params,
                timeout=30,
            )
            response.raise_for_status()
            
            result = response.json()
            
            # Задержка между запросами
            time.sleep(self.request_delay)
            
            return result
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка запроса цен по nm_id {nm_id}: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Статус: {e.response.status_code}, Ответ: {e.response.text}")
            return None
    

