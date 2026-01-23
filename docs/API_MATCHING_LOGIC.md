# Логика сопоставления данных из разных API

## 🔑 Ключ сопоставления: SKU

**РЕШЕНИЕ:** Используем `/v3/product/info/list` для правильного сопоставления!

### Правильный метод сопоставления

**Endpoint:** `/v3/product/info/list` (или `/v2/product/info/list`)

**Как работает:**
- Принимает массив `sku` из entrypoint API (глобальные идентификаторы товаров)
- Возвращает `product_id` (ID товара в кабинете продавца) и `offer_id` (артикул продавца)
- **SKU здесь совпадает с тем, что возвращает Entrypoint API!**

**Преимущества:**
- ✅ Прямое сопоставление по SKU
- ✅ Получаем и `product_id`, и `offer_id` за один запрос
- ✅ Надёжный и быстрый способ

---

## 📊 Схема сопоставления

```
┌─────────────────────────────────────────────────────────────┐
│ ШАГ 1: Публичный Entrypoint API                            │
│ URL: https://www.ozon.ru/api/entrypoint-api.bx/page/json/v2 │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ Возвращает товары с полем "sku"
                            ▼
        ┌───────────────────────────────────────┐
        │ Товар 1:                              │
        │   sku: 1262984053  ←─── КЛЮЧ          │
        │   product_name: "..."                 │
        │   current_price: 548                  │
        │   original_price: 1732                │
        └───────────────────────────────────────┘
                            │
                            │ Извлекаем все SKU
                            ▼
        ┌───────────────────────────────────────┐
        │ sku_list = [                          │
        │   1262984053,                         │
        │   649437772,                          │
        │   3031537561,                         │
        │   ...                                 │
        │ ]                                     │
        └───────────────────────────────────────┘
                            │
                            │ Запрос в Seller API
                            │ POST /v3/product/info/list
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ ШАГ 2: Seller API /v3/product/info/list                     │
│ POST: {"sku": ["1262984053", ...]}                          │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ Возвращает product_id и offer_id
                            ▼
        ┌───────────────────────────────────────┐
        │ Товар 1:                              │
        │   sku: 1262984053  ←─── ТОТ ЖЕ SKU     │
        │   id: 123456  (product_id)            │
        │   offer_id: "ART-12345"               │
        └───────────────────────────────────────┘
                            │
                            │ СОПОСТАВЛЕНИЕ ПО SKU
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ ШАГ 3: Объединение данных                                   │
│                                                              │
│ catalog_by_sku = {                                          │
│   1262984053: {sku, name, price, ...}  ← из публичного API │
│ }                                                            │
│                                                              │
│ seller_info_by_sku = {                                      │
│   1262984053: {product_id, offer_id, ...}  ← из Seller API  │
│ }                                                            │
│                                                              │
│ for sku, catalog_data in catalog_by_sku.items():            │
│     seller_info = seller_info_by_sku.get(sku, {})          │
│     # Объединяем данные                                      │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔍 Детальный процесс

### 1. Публичный API (entrypoint) - из F12

**Что возвращает:**
```json
{
  "widgetStates": {
    "tileGridDesktop-...": {
      "items": [
        {
          "sku": 1262984053,  // ← Глобальный идентификатор товара на Ozon
          "offer_id": "ART-12345",  // ← Артикул продавца (если извлечён)
          "product_name": "Likato Professional...",
          "current_price": 548,
          "original_price": 1732
        }
      ]
    }
  }
}
```

**Извлекаем:**
- `sku` → глобальный идентификатор товара на Ozon (НЕ совпадает с product_id из Seller API!)
- `offer_id` → артикул продавца (если извлечён из структуры) - **ОСНОВНОЙ КЛЮЧ**
- `product_name` → название товара
- `current_price` → цена покупателя
- `original_price` → зачёркнутая цена

---

### 2. Формирование запроса в Seller API (/v3/product/info/list)

**Собираем все SKU:**
```python
sku_list = []
for product in catalog_products:
    sku = product.get("sku")
    if sku:
        sku_list.append(sku)

# Результат: [1262984053, 649437772, 3031537561, ...]
```

**Запрос в Seller API:**
```python
# POST https://api-seller.ozon.ru/v3/product/info/list
payload = {
    "offer_id": [],
    "product_id": [],
    "sku": ["1262984053", "649437772", "3031537561", ...]  # SKU из entrypoint API
}
```

**Ограничения:**
- До 1000 элементов суммарно в массивах (offer_id + product_id + sku)
- Если больше — разбиваем на батчи по 1000 SKU

---

### 3. Seller API (/v3/product/info/list)

**Что возвращает:**
```json
{
  "result": {
    "items": [
      {
        "id": 123456,          // ← product_id (ID товара в кабинете продавца)
        "offer_id": "ART-12345",  // ← offer_id (артикул продавца)
        "sku": 1262984053,     // ← Глобальный SKU (совпадает с entrypoint API!)
        "fbs_sku": 1262984053,  // SKU для FBS (если применимо)
        "fbo_sku": 987654321,   // SKU для FBO (если применимо)
        "name": "Название товара"
      }
    ]
  }
}
```

**Извлекаем:**
- `id` → `product_id` (ID товара в кабинете продавца)
- `offer_id` → артикул продавца
- `sku` → глобальный SKU (совпадает с entrypoint API!) - **КЛЮЧ для сопоставления**

---

### 4. Сопоставление по SKU (через /v3/product/info/list)

**Создаём индексы:**
```python
# Индекс данных из публичного API (по SKU)
catalog_by_sku = {
    1262984053: {
        "sku": 1262984053,  # Глобальный SKU
        "product_name": "Likato Professional...",
        "current_price": 548,
        "original_price": 1732
    },
    ...
}

# Индекс данных из Seller API (по SKU - правильное сопоставление!)
seller_info_by_sku = {
    1262984053: {
        "product_id": 123456,  # ID товара в кабинете продавца
        "offer_id": "ART-12345",  # Артикул продавца
        "sku": 1262984053  # Тот же SKU (для проверки)
    },
    ...
}

# Индекс цен из Seller API (по offer_id)
seller_prices_by_offer_id = {
    "ART-12345": {
        "seller_price": 548,
        "old_price": 1732,
        "min_price": 500
    },
    ...
}
```

**Сопоставление:**
```python
for sku, catalog_data in catalog_by_sku.items():
    # Получаем product_id и offer_id из сопоставления по SKU
    seller_info = seller_info_by_sku.get(sku, {})
    product_id_from_seller = seller_info.get("product_id")
    offer_id_from_seller = seller_info.get("offer_id")
    
    # Получаем цены по offer_id (если нужно)
    seller_price_data = {}
    if offer_id_from_seller:
        seller_price_data = seller_prices_by_offer_id.get(offer_id_from_seller, {})
    
    # Объединяем данные
    result = {
        "product_id": sku,  # SKU из публичного API
        "product_id_seller": product_id_from_seller,  # ID товара в кабинете продавца
        "offer_id": offer_id_from_seller,  # Артикул продавца из /v3/product/info/list
        "product_name": catalog_data.get("product_name"),  # Из публичного API
        "price_current": catalog_data.get("current_price"),  # Из публичного API
        "price_seller": seller_price_data.get("seller_price"),  # Из Seller API
        ...
    }
```

---

## ⚠️ Важные моменты

### 1. SKU - правильный ключ для сопоставления

- `sku` из entrypoint API совпадает с `sku` в `/v3/product/info/list`
- Используем `/v3/product/info/list` для получения `product_id` и `offer_id` по SKU
- Это **единственный надёжный способ** сопоставления

### 2. SKU ≠ product_id (но это не проблема!)

- `sku` из entrypoint API - глобальный идентификатор товара на Ozon
- `product_id` из Seller API - идентификатор товара в кабинете продавца
- **Они разные, но `/v3/product/info/list` решает эту проблему!**
- Мы получаем оба идентификатора через правильный эндпоинт

### 3. Не все товары могут быть сопоставлены

**Причины:**
- Seller API возвращает только товары вашего кабинета
- Если парсите чужого продавца (`OZON_ACCOUNT_TYPE=foreign`), Seller API вернёт 0 товаров
- Некоторые товары могут отсутствовать в Seller API

**Решение:**
- Используем данные из публичного API как основной источник
- Данные из Seller API - дополнительный источник (если доступны)

### 3. Fallback для offer_id

Если `offer_id` отсутствует в Seller API:
- Пробуем извлечь из публичного API (если там есть)
- Если нет - оставляем пустым

---

## 📝 Пример результата

```python
{
    "product_id": 1262984053,  # SKU (ключ сопоставления)
    "offer_id": "ART-12345",   # Из Seller API (если доступен)
    "product_name": "Likato Professional...",  # Из публичного API
    "price_current": 548,       # Из публичного API (цена покупателя)
    "price_original": 1732,    # Из публичного API (зачёркнутая цена)
    "price_seller": 548,       # Из Seller API (цена продавца, если доступна)
    "source_catalog": "catalog_api",
    "source_seller": "seller_api"  # или None, если не сопоставлено
}
```

---

## 🔄 Альтернативные ключи (если SKU недоступен)

Если по какой-то причине SKU недоступен, можно попробовать:

1. **offer_id** - но он уникален для каждого продавца, поэтому не подходит для сопоставления между разными продавцами
2. **product_name** - не надёжен (могут быть различия в названиях)
3. **URL товара** - можно извлечь SKU из URL

**Вывод:** SKU - единственный надёжный ключ для сопоставления.

---

**Дата создания:** 2026-01-21  
**Версия:** 1.0
