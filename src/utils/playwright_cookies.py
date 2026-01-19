"""Модуль для получения cookies через Playwright с обходом антиботов."""
import asyncio
import time
from typing import Dict, Optional
from pathlib import Path
from loguru import logger


async def get_ozon_cookies_playwright(headless: bool = True) -> Optional[str]:
    """Получает cookies Ozon через Playwright с обходом антиботов.
    
    Использует playwright-stealth для обхода антибот-защиты Ozon.
    Это более надежный способ получения cookies, чем headless Chrome.
    
    Args:
        headless: Запускать браузер в headless режиме (True) или показывать окно (False).
                  Используйте False для отладки и проверки прохождения антибота.
    
    Returns:
        Строка с cookies в формате "name1=value1; name2=value2" или None
    """
    try:
        from playwright.async_api import async_playwright
        from playwright_stealth import stealth
        
        logger.info("🚀 Запуск Playwright для получения cookies Ozon (с обходом антиботов)...")
        
        async with async_playwright() as p:
            # Запускаем браузер с обходом детекции (ChatGPT рекомендация)
            browser = await p.chromium.launch(
                headless=headless,  # Можно отключить для отладки
                args=[
                    '--no-sandbox',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                ]
            )
            
            if not headless:
                logger.info("🖥️  Браузер запущен в видимом режиме для отладки")
            
            # Создаем контекст с реалистичными настройками
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                locale='ru-RU',
                timezone_id='Europe/Moscow',
            )
            
            page = await context.new_page()
            
            # Применяем stealth плагин для обхода антиботов
            # stealth - синхронная функция, но работает с async page
            try:
                # Проверяем, что stealth - это функция, а не модуль
                if callable(stealth):
                    stealth(page)
                else:
                    logger.warning("⚠️ stealth не является функцией, пропускаем применение")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось применить stealth плагин: {e}. Продолжаем без него...")
            
            # Шаг 1: Открываем главную страницу Ozon
            logger.debug("Открываем главную страницу https://www.ozon.ru...")
            await page.goto('https://www.ozon.ru/', wait_until='networkidle', timeout=30000)
            await asyncio.sleep(3)  # Даем время на установку cookies
            
            # Улучшенная имитация поведения пользователя (ChatGPT рекомендация)
            logger.debug("Имитация поведения пользователя: скролл и движения мыши...")
            
            # Прокручиваем страницу плавно
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
            await asyncio.sleep(1.5)
            
            # Имитация движения мыши (случайные координаты)
            import random
            await page.mouse.move(random.randint(100, 500), random.randint(100, 400))
            await asyncio.sleep(0.5)
            await page.mouse.move(random.randint(200, 600), random.randint(200, 500))
            await asyncio.sleep(1)
            
            await page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(2)
            
            # Шаг 2: Открываем страницу продавца для получения специфичных cookies
            seller_url = "https://www.ozon.ru/seller/cosmo-beauty-176640/"
            logger.debug(f"Открываем страницу продавца {seller_url}...")
            await page.goto(seller_url, wait_until='networkidle', timeout=30000)
            await asyncio.sleep(5)  # Даем время на установку cookies
            
            # Прокручиваем страницу несколько раз для имитации поведения пользователя
            logger.debug("Имитация просмотра страницы продавца...")
            for i in range(4):
                scroll_position = (i + 1) * 25  # 25%, 50%, 75%, 100%
                await page.evaluate(f"window.scrollTo(0, document.body.scrollHeight * {scroll_position / 100})")
                await asyncio.sleep(random.uniform(1, 2))  # Случайные задержки
                
                # Случайные движения мыши
                await page.mouse.move(random.randint(100, 800), random.randint(100, 600))
                await asyncio.sleep(0.5)
            
            # Возвращаемся наверх
            await page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(2)
            
            # Шаг 3: Делаем запрос к entrypoint API через Playwright для получения cookies
            logger.debug("Запрос к entrypoint API через Playwright для получения cookies...")
            try:
                api_url = 'https://www.ozon.ru/api/entrypoint-api.bx/page/json/v2?url=%2Fseller%2Fcosmo-beauty-176640%2F%3Fpage%3D1'
                response = await page.request.get(
                    api_url,
                    headers={
                        'Accept': 'application/json, text/plain, */*',
                        'Referer': 'https://www.ozon.ru/seller/cosmo-beauty-176640/',
                        'Origin': 'https://www.ozon.ru'
                    }
                )
                logger.debug(f"API request status: {response.status}")
                if response.status == 200:
                    logger.debug("✅ Успешный запрос к API через Playwright")
                await asyncio.sleep(2)  # Даем время на установку cookies после запроса
            except Exception as e:
                logger.debug(f"Ошибка при запросе к API: {e}")
            
            # Получаем все cookies
            cookies = await context.cookies()
            await browser.close()
            
            # Фильтруем cookies для домена ozon.ru
            ozon_cookies = {}
            for cookie in cookies:
                domain = cookie.get('domain', '')
                if 'ozon.ru' in domain or domain == '':
                    ozon_cookies[cookie['name']] = cookie['value']
            
            if ozon_cookies:
                # Формируем строку cookies
                cookies_string = "; ".join([f"{k}={v}" for k, v in ozon_cookies.items()])
                cookie_names = list(ozon_cookies.keys())
                logger.success(
                    f"✅ Успешно получено {len(ozon_cookies)} cookies через Playwright: "
                    f"{', '.join(cookie_names[:10])}{'...' if len(cookie_names) > 10 else ''}"
                )
                logger.debug(f"  • Все cookies: {cookie_names}")
                return cookies_string
            else:
                logger.warning("⚠️ Не получено cookies через Playwright")
                return None
                
    except ImportError as e:
        logger.error(f"❌ Playwright не установлен: {e}")
        logger.info("Установите: python -m pip install playwright playwright-stealth")
        logger.info("Затем выполните: playwright install chromium")
        return None
    except Exception as e:
        logger.error(f"❌ Ошибка при получении cookies через Playwright: {e}")
        logger.debug("Детали ошибки:", exc_info=True)
        return None
