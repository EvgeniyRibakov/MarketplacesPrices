# Требования для работы с эндпоинтом WB API: content/v2/object/all

## Описание метода

Метод возвращает список названий родительских категорий предметов и их предметов с ID. Например, у категории Игрушки будут предметы Калейдоскопы, Куклы, Мячики.

## URL эндпоинта
```
GET https://content-api.wildberries.ru/content/v2/object/all
```

## Необходимые данные для начала работы

### 1. API Токен (ОБЯЗАТЕЛЬНО)
**Тип:** API ключ от аккаунта продавца  
**Где получить:**
- Личный кабинет Wildberries → Интеграции → Создать токен
- Выберите раздел доступа: **Контент**

**Формат передачи в заголовке:**
```
Authorization: <ваш_токен>
```
**Важно:** Используется формат `HeaderApiKey` - токен передаётся напрямую без префиксов `Bearer` или `ApiKey`

**Срок действия:** 180 дней (стандартный API токен)

### 2. Параметры запроса (опционально)

#### `locale` (опционально)
- **Тип:** string
- **Описание:** Язык полей ответа
- **Допустимые значения:** `ru` (русский), `en` (английский), `zh` (китайский)
- **По умолчанию:** `ru`
- **Пример:** `locale=en`

#### `name` (опционально)
- **Тип:** string
- **Описание:** Поиск по названию предмета (работает по подстроке, можно искать на любом из поддерживаемых языков)
- **Пример:** `name=Носки`

#### `limit` (опционально)
- **Тип:** integer
- **Описание:** Количество предметов в ответе
- **Максимальное значение:** 1000
- **По умолчанию:** 30
- **Пример:** `limit=1000`

#### `offset` (опционально)
- **Тип:** integer
- **Описание:** Сколько элементов пропустить. Например, для значения 10 ответ начнется с 11 элемента
- **По умолчанию:** 0
- **Пример:** `offset=5000`

#### `parentID` (опционально)
- **Тип:** integer
- **Описание:** ID родительской категории предмета для фильтрации
- **Пример:** `parentID=1000`

### 3. HTTP заголовки

**Обязательные:**
```
Authorization: <ваш_токен>
```

**Рекомендуемые:**
```
Content-Type: application/json
User-Agent: <название_приложения>/<версия>
```

### 4. Формат ответа

**Успешный ответ:**
```json
[
  {
    "name": "Название категории",
    "id": 212,
    "isVisible": true
  },
  ...
]
```

**Поля ответа:**
- `name` (string) - Название категории/предмета
- `id` (integer) - ID категории (subjectID)
- `isVisible` (boolean) - Видимость категории

### 5. Ограничения и особенности

**Rate Limits (лимиты запросов):**
- **Период:** 1 минута
- **Лимит:** 100 запросов
- **Интервал:** 600 миллисекунд между запросами
- **Всплеск:** 5 запросов

**Примечание:** Эти лимиты применяются для всех методов категории Контент, кроме:
- создания карточек товаров
- создания карточек товаров с присоединением
- редактирования карточек товаров
- получения несозданных карточек товаров с ошибками

**Пагинация:** Для получения всех данных нужно использовать `limit` (макс. 1000) и `offset`

**Назначение:** Эндпоинт возвращает список родительских категорий и их предметов с ID, необходимых для создания карточек товаров

### 6. Пример запроса

```python
import requests
import time

url = "https://content-api.wildberries.ru/content/v2/object/all"
headers = {
    "Authorization": "<ваш_токен>",  # Токен без префиксов
    "Content-Type": "application/json"
}
params = {
    "locale": "ru",      # опционально: ru, en, zh
    "limit": 1000,       # максимум 1000
    "offset": 0,         # для пагинации
    "parentID": None,    # опционально: фильтр по родительской категории
    "name": None         # опционально: поиск по названию
}

# Соблюдаем rate limits: 600мс между запросами
response = requests.get(url, headers=headers, params=params)
data = response.json()
time.sleep(0.6)  # Задержка между запросами
```

### 7. Пример с пагинацией (получение всех категорий)

```python
import requests
import time

url = "https://content-api.wildberries.ru/content/v2/object/all"
headers = {
    "Authorization": "<ваш_токен>",
    "Content-Type": "application/json"
}

all_categories = []
offset = 0
limit = 1000

while True:
    params = {
        "limit": limit,
        "offset": offset,
        "locale": "ru"
    }
    
    response = requests.get(url, headers=headers, params=params)
    data = response.json()
    
    if not data:
        break
    
    all_categories.extend(data)
    offset += limit
    
    # Соблюдаем rate limits
    time.sleep(0.6)
    
    # Если получили меньше limit, значит это последняя страница
    if len(data) < limit:
        break

print(f"Всего получено категорий: {len(all_categories)}")
```

## Использование в проекте

### Готовый скрипт парсинга

В проекте создан скрипт `parse_wb_categories.py` для парсинга категорий через Content API.

**Использование:**

1. Убедитесь, что в `.env` файле указан токен:
   ```
   WB_CONTENT_API_TOKEN=your_content_api_token_here
   ```

2. Запустите скрипт:
   ```bash
   python parse_wb_categories.py
   ```

3. Результаты будут сохранены в `output/wb_categories_all_ru.json`

**Настройка параметров в скрипте:**

В файле `parse_wb_categories.py` можно изменить:
- `locale` - язык полей ответа (ru, en, zh)
- `parent_id` - фильтрация по родительской категории
- `search_name` - поиск по названию предмета

### API клиент

Также доступен класс `WBContentAPI` в `src/api/wb_content_api.py` для использования в других скриптах:

```python
from src.api.wb_content_api import WBContentAPI

async with WBContentAPI(api_token="your_token") as api:
    # Получить все категории
    all_categories = await api.get_all_objects(locale="ru")
    
    # Поиск по названию
    results = await api.search_by_name("Носки", locale="ru")
    
    # Получить предметы конкретной категории
    items = await api.get_by_parent_id(parent_id=1000, locale="ru")
```

## Дополнительная документация

- Официальная документация: https://dev.wildberries.ru/openapi/work-with-products
- Swagger/OpenAPI: https://dev.wildberries.ru/openapi/work-with-products
