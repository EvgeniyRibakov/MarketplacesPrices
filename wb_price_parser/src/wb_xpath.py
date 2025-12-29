"""
Модуль для парсинга цен через XPath (fallback для price_card)
"""
import asyncio
import aiohttp
import logging
from typing import Optional, List
from lxml import html, etree

from .config import Config
from .utils import extract_price_from_text, sanitize_for_logging


class WBXPathParser:
    """Парсер для извлечения price_card через XPath"""
    
    # XPath выражения для поиска цен
    XPATH_PRICE_CARD = './/span[contains(@class, "price-card")]'
    XPATH_CURRENT_PRICE = './/ins[contains(@class, "price")]'
    XPATH_OLD_PRICE = './/del[contains(@class, "price")]'
    XPATH_PRODUCT_CARD = '//article[contains(@class, "product-card")]'
    
    def __init__(self, config: Config, logger: Optional[logging.Logger] = None):
        """
        Инициализация парсера
        
        Args:
            config: Конфигурация проекта
            logger: Логгер (опционально)
        """
        self.config = config
        self.logger = logger or logging.getLogger(__name__)
        self.semaphore = asyncio.Semaphore(config.concurrency_html)
        self.session: Optional[aiohttp.ClientSession] = None
        
        # Заголовки для запросов
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9",
        }
    
    async def __aenter__(self):
        """Асинхронный контекстный менеджер - вход"""
        timeout = aiohttp.ClientTimeout(total=self.config.request_timeout)
        self.session = aiohttp.ClientSession(
            headers=self.headers,
            timeout=timeout
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Асинхронный контекстный менеджер - выход"""
        if self.session:
            await self.session.close()
    
    async def fetch_price_card_from_url(self, product_url: str) -> Optional[float]:
        """
        Получает price_card с карточки товара через XPath
        
        Args:
            product_url: URL карточки товара
        
        Returns:
            Цена с картой в рублях или None
        """
        if not product_url:
            return None
        
        async with self.semaphore:
            try:
                # Задержка между запросами
                if self.config.request_delay > 0:
                    await asyncio.sleep(self.config.request_delay)
                
                self.logger.debug(f"Парсинг price_card с {product_url}")
                
                async with self.session.get(product_url) as response:
                    if response.status != 200:
                        self.logger.warning(
                            f"Ошибка {response.status} при запросе {product_url}"
                        )
                        return None
                    
                    html_content = await response.text()
                    return self._parse_price_card_from_html(html_content, product_url)
                    
            except asyncio.TimeoutError:
                self.logger.warning(f"Timeout при запросе {product_url}")
                return None
            except Exception as e:
                self.logger.error(
                    f"Ошибка при парсинге {product_url}: {e}"
                )
                return None
    
    def _parse_price_card_from_brand_page(
        self, html_content: str, nm_id: Optional[int] = None
    ) -> Optional[float]:
        """
        Парсит price_card со страницы бренда (список товаров)
        
        Args:
            html_content: HTML содержимое страницы
            nm_id: nmId товара для поиска конкретной карточки
        
        Returns:
            Цена с картой в рублях или None
        """
        try:
            tree = html.fromstring(html_content)
            
            # Ищем все карточки товаров
            product_cards = tree.xpath(self.XPATH_PRODUCT_CARD)
            
            for card in product_cards:
                # Если указан nm_id, проверяем соответствие
                if nm_id:
                    # Пробуем найти nm_id в data-атрибутах или ссылке
                    card_link = card.xpath('.//a[@href]')
                    if card_link:
                        href = card_link[0].get("href", "")
                        if str(nm_id) in href:
                            # Нашли нужную карточку
                            price_card = self._extract_price_from_card(card)
                            if price_card:
                                return price_card
                else:
                    # Без nm_id - берём первую найденную цену
                    price_card = self._extract_price_from_card(card)
                    if price_card:
                        return price_card
            
            return None
            
        except Exception as e:
            self.logger.error(f"Ошибка парсинга страницы бренда: {e}")
            return None
    
    def _parse_price_card_from_html(
        self, html_content: str, url: str = ""
    ) -> Optional[float]:
        """
        Парсит price_card из HTML содержимого
        
        Args:
            html_content: HTML содержимое
            url: URL страницы (для логирования)
        
        Returns:
            Цена с картой в рублях или None
        """
        try:
            tree = html.fromstring(html_content)
            
            # Ищем цену с картой
            price_elements = tree.xpath(self.XPATH_PRICE_CARD)
            
            if price_elements:
                # Берём первый найденный элемент
                price_text = price_elements[0].text_content().strip()
                price = extract_price_from_text(price_text)
                
                if price:
                    self.logger.debug(f"Найдена price_card: {price} руб. ({url})")
                    return price
            
            # Если не нашли через price-card, пробуем другие варианты
            # Ищем текущую цену (ins)
            current_price_elements = tree.xpath(self.XPATH_CURRENT_PRICE)
            if current_price_elements:
                price_text = current_price_elements[0].text_content().strip()
                price = extract_price_from_text(price_text)
                if price:
                    self.logger.debug(f"Найдена текущая цена: {price} руб. ({url})")
                    return price
            
            return None
            
        except etree.XMLSyntaxError as e:
            self.logger.warning(f"Ошибка парсинга HTML {url}: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Неожиданная ошибка при парсинге {url}: {e}")
            return None
    
    def _extract_price_from_card(self, card_element) -> Optional[float]:
        """
        Извлекает цену с картой из элемента карточки товара
        
        Args:
            card_element: Элемент карточки товара
        
        Returns:
            Цена в рублях или None
        """
        try:
            # Ищем цену с картой внутри карточки
            price_elements = card_element.xpath(self.XPATH_PRICE_CARD)
            if price_elements:
                price_text = price_elements[0].text_content().strip()
                return extract_price_from_text(price_text)
            
            # Если не нашли, пробуем текущую цену
            current_price_elements = card_element.xpath(self.XPATH_CURRENT_PRICE)
            if current_price_elements:
                price_text = current_price_elements[0].text_content().strip()
                return extract_price_from_text(price_text)
            
            return None
            
        except Exception as e:
            self.logger.debug(f"Ошибка извлечения цены из карточки: {e}")
            return None
    
    async def fetch_price_card_batch(
        self, product_urls: List[str]
    ) -> Dict[str, Optional[float]]:
        """
        Пакетное получение price_card для списка товаров
        
        Args:
            product_urls: Список URL товаров
        
        Returns:
            Словарь {url: price_card}
        """
        tasks = [
            self.fetch_price_card_from_url(url) for url in product_urls
        ]
        
        prices = await asyncio.gather(*tasks, return_exceptions=True)
        
        result = {}
        for url, price in zip(product_urls, prices):
            if isinstance(price, Exception):
                self.logger.warning(f"Ошибка при получении цены для {url}: {price}")
                result[url] = None
            else:
                result[url] = price
        
        return result


