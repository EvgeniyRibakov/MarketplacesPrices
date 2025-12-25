"""API клиент для Ozon."""
import time
from typing import Dict, List, Optional
from loguru import logger
import requests


class OzonAPI:
    """Клиент для работы с официальным API Ozon."""
    
    BASE_URL = "https://api-seller.ozon.ru"
    
    def __init__(self, api_key: str, client_id: str, request_delay: float = 0.5):
        """Инициализация API клиента.
        
        Args:
            api_key: API ключ Ozon
            client_id: Client ID Ozon
            request_delay: Задержка между запросами (секунды)
        """
        self.api_key = api_key
        self.client_id = client_id
        self.request_delay = request_delay
        self.session = requests.Session()
        self.session.headers.update({
            "Client-Id": client_id,
            "Api-Key": api_key,
            "Content-Type": "application/json",
        })
    
    def _make_request(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[Dict] = None,
        timeout: int = 30,
    ) -> Optional[Dict]:
        """Выполнить запрос к API.
        
        Args:
            method: HTTP метод (GET, POST, etc.)
            endpoint: Endpoint API
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
                json=json_data,
                timeout=timeout,
            )
            response.raise_for_status()
            
            # Задержка между запросами
            time.sleep(self.request_delay)
            
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка запроса к Ozon API {endpoint}: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Статус: {e.response.status_code}, Ответ: {e.response.text}")
            return None
    
    def get_product_prices(self, product_ids: List[int]) -> Optional[List[Dict]]:
        """Получить цены для товаров.
        
        Args:
            product_ids: Список ID товаров (product_id или offer_id)
            
        Returns:
            Список товаров с ценами или None
        """
        endpoint = "/v4/product/info/prices"
        
        # Разбиваем на батчи (нужно проверить лимит API)
        batch_size = 1000
        all_results = []
        
        for i in range(0, len(product_ids), batch_size):
            batch = product_ids[i:i + batch_size]
            
            json_data = {
                "product_id": batch,
                "offer_id": [],  # Можно использовать offer_id вместо product_id
            }
            
            result = self._make_request("POST", endpoint, json_data=json_data)
            
            if result and "result" in result:
                all_results.extend(result["result"].get("items", []))
        
        return all_results if all_results else None
    
    def get_product_list(
        self,
        limit: int = 1000,
        last_id: Optional[str] = None,
        filter_options: Optional[Dict] = None,
    ) -> Optional[Dict]:
        """Получить список товаров.
        
        Args:
            limit: Количество товаров на странице (макс 1000)
            last_id: ID последнего товара для пагинации
            filter_options: Дополнительные фильтры
            
        Returns:
            Словарь с товарами и информацией о пагинации или None
        """
        # Пробуем разные возможные endpoints
        endpoints_to_try = [
            "/v2/product/info/list",  # Возможный правильный endpoint
            "/v3/product/info/list",
            "/v2/product/list",
            "/v1/product/list",
        ]
        
        json_data = {
            "limit": min(limit, 1000),
        }
        
        if last_id:
            json_data["last_id"] = last_id
        
        if filter_options:
            json_data.update(filter_options)
        
        # Пробуем каждый endpoint до первого успешного
        for endpoint in endpoints_to_try:
            result = self._make_request("POST", endpoint, json_data=json_data)
            if result and ("result" in result or "items" in result):
                logger.info(f"Успешно использован endpoint: {endpoint}")
                return result
            elif result:
                # Если есть ответ, но не в ожидаемом формате, возвращаем его
                logger.warning(f"Endpoint {endpoint} вернул неожиданный формат: {result}")
                return result
        
        # Если ничего не сработало, возвращаем None
        logger.error("Не удалось найти рабочий endpoint для получения списка товаров")
        return None
    
    def get_all_products(self) -> List[Dict]:
        """Получить все товары из кабинета.
        
        Returns:
            Список всех товаров
        """
        all_products = []
        last_id = None
        limit = 1000
        
        logger.info("Начинаем получение списка товаров из Ozon...")
        
        # Пробуем использовать метод создания отчёта для получения товаров
        # Это более надёжный способ получить все товары
        try:
            endpoint = "/v1/report/products/create"
            json_data = {
                "language": "DEFAULT",
            }
            
            result = self._make_request("POST", endpoint, json_data=json_data)
            
            if result and "result" in result:
                report_code = result["result"].get("code")
                logger.info(f"Создан отчёт с кодом: {report_code}")
                logger.warning("⚠️ Для получения данных отчёта нужно использовать отдельный метод получения отчёта")
                logger.info("Пробуем альтернативный метод получения товаров...")
        except Exception as e:
            logger.warning(f"Не удалось создать отчёт: {e}")
            logger.info("Пробуем прямой метод получения товаров...")
        
        # Пробуем прямой метод получения списка товаров
        while True:
            result = self.get_product_list(limit=limit, last_id=last_id)
            
            if not result:
                break
            
            # Проверяем разные форматы ответа
            items = []
            if "result" in result:
                if "items" in result["result"]:
                    items = result["result"]["items"]
                elif isinstance(result["result"], list):
                    items = result["result"]
            elif "items" in result:
                items = result["items"]
            
            if not items:
                break
            
            all_products.extend(items)
            logger.info(f"Получено товаров: {len(all_products)}")
            
            # Проверяем, есть ли ещё товары
            if "result" in result and "last_id" in result["result"]:
                last_id = result["result"]["last_id"]
            elif "last_id" in result:
                last_id = result["last_id"]
            else:
                break
        
        logger.success(f"Всего получено товаров: {len(all_products)}")
        return all_products

