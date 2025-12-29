# WB Price Parser

Универсальный парсер цен Wildberries для сбора финальных цен по товарам (~900 SKU) с экспортом в .xlsx.

## Описание

Проект собирает цены товаров Wildberries через внутренний JSON API и экспортирует результаты в Excel файл. Поддерживает сбор:
- `price_basic` - цена продавца без скидки
- `price_product` - цена после СПП (чёрная цена)
- `price_card` - цена с картой Wildberries (через API или XPath fallback)

## Требования

- Python 3.10+
- pip

## Установка

1. Клонируйте репозиторий или скопируйте проект
2. Установите зависимости:
```bash
# Используйте python -m pip вместо просто pip (решает проблемы с PATH на Windows)
python -m pip install -r requirements.txt

# Или если pip доступен напрямую:
pip install -r requirements.txt
```

3. Создайте файл `.env` на основе `env.example`:

**Windows PowerShell:**
```powershell
cd wb_price_parser
python create_env.py
```

**Или вручную:**
```powershell
Copy-Item env.example .env
```

**Linux/Mac:**
```bash
cp env.example .env
```

4. Заполните `.env` своими значениями (см. раздел Конфигурация)
   - Обязательно укажите `WB_BRAND_ID` и `WB_DEST`

## Запуск

### Основной парсинг

**Вариант 1: Из папки проекта (рекомендуется)**
```bash
cd wb_price_parser
python -m src.main
```

**Вариант 2: Из корня проекта**
```bash
python wb_price_parser/run.py
```

### Discovery (исследование API)

Перед первым запуском рекомендуется выполнить discovery для изучения структуры API:

**Из папки проекта:**
```bash
cd wb_price_parser
# Анализ одной страницы
python -m src.discovery

# Анализ нескольких страниц
python -m src.discovery 3
```

**Из корня:**
```bash
python wb_price_parser/run_discovery.py
```

Результаты сохраняются в `samples/`:
- `json_page_N.json` - полные ответы API
- `products_summary_page_N.json` - сводка по товарам
- `products_report_page_N.txt` - текстовый отчёт
- `mapping.json` - файл мэппинга JSON ↔ DOM

### Health Check

Проверка работоспособности системы:

**Из папки проекта:**
```bash
cd wb_price_parser
python -m src.health_check
```

**Из корня:**
```bash
python wb_price_parser/run_health_check.py
```

Проверяет:
- Корректность конфигурации
- Доступность API
- Структуру данных товаров

## Конфигурация

Все параметры настраиваются через файл `.env`. Основные переменные:

- `WB_BRAND_ID` - ID бренда для парсинга
- `WB_DEST` - Регион/ПВЗ для получения цен
- `WB_SPP` - Параметр СПП
- `CONCURRENCY` - Количество одновременных запросов (по умолчанию 40)
- `OUTPUT_FILE` - Имя выходного файла .xlsx

Полный список переменных см. в `env.example`

## Структура проекта

```
wb_price_parser/
├── src/
│   ├── main.py          # Точка входа - основной парсер
│   ├── discovery.py     # Discovery скрипт для исследования API
│   ├── health_check.py  # Health-check скрипт
│   ├── config.py        # Чтение и валидация .env
│   ├── wb_api.py        # Асинхронный клиент для internal API
│   ├── wb_xpath.py      # Парсинг price-card через XPath (fallback)
│   ├── mapper.py        # Маппинг JSON ↔ DOM
│   ├── models.py        # Структуры данных (Product, Cabinet)
│   ├── exporter.py      # Экспорт в .xlsx
│   └── utils.py          # Вспомогательные функции
├── samples/             # Примеры JSON и HTML для discovery
│   └── html/            # HTML страницы для ручной сверки
├── logs/                # Логи работы
├── output/              # Выходные файлы .xlsx
├── env.example          # Пример конфигурации
├── requirements.txt     # Зависимости
├── .gitignore          # Игнорируемые файлы
└── README.md           # Этот файл
```

## Формат выходного файла

Файл `.xlsx` содержит следующие колонки:
- `cabinet_name` - Название кабинета
- `cabinet_id` - ID кабинета
- `article` - Артикул товара
- `name` - Название товара
- `price_basic` - Цена без скидки (руб.)
- `price_product` - Цена после СПП (руб.)
- `price_card` - Цена с картой (руб., если есть)
- `source_price_basic` - Источник цены basic
- `source_price_product` - Источник цены product
- `source_price_card` - Источник цены card
- `product_url` - Ссылка на товар
- `timestamp` - Время сбора (UTC)

## Кабинеты продавцов

Поддерживаемые кабинеты:
- MAU → 53607
- MAB → 121614
- MMA → 174711
- cosmo → 224650
- dreamlab → 1140223
- beautylab → 4428365

## Производительность

- Целевое время выполнения для 900 SKU: 5-10 минут
- Частота обновления: каждые 1-2 часа
- Асинхронная обработка с настраиваемым concurrency

## Тестирование

### Unit-тесты

```bash
# Запуск unit-тестов
python -m pytest tests/

# Или через unittest
python -m unittest discover tests
```

### Health Check

Перед запуском парсера рекомендуется проверить систему:

```bash
python -m src.health_check
```

## Примеры использования

### Базовый запуск

```bash
# 1. Установка зависимостей
pip install -r requirements.txt

# 2. Настройка .env
cp env.example .env
# Отредактируйте .env и укажите WB_BRAND_ID, WB_DEST и другие параметры

# 3. Проверка конфигурации
python -m src.health_check

# 4. Discovery (опционально, для первого запуска)
python -m src.discovery

# 5. Запуск парсера
python -m src.main
```

### Настройка concurrency

В `.env` можно настроить параллелизм:

```env
# Для JSON API запросов
CONCURRENCY=40

# Для HTML парсинга (ниже, чтобы не перегружать сервер)
CONCURRENCY_HTML=5

# Задержка между запросами (секунды)
REQUEST_DELAY=0.5
```

## Troubleshooting

### Ошибка "Обязательный параметр не найден в .env"

Убедитесь, что все обязательные параметры заполнены в `.env`:
- `WB_BRAND_ID`
- `WB_DEST`
- `WB_SPP`
- `CONCURRENCY`
- `OUTPUT_FILE`

### API возвращает пустые ответы

1. Проверьте корректность `WB_BRAND_ID` и `WB_DEST`
2. Выполните health-check: `python -m src.health_check`
3. Проверьте логи в `logs/`

### Rate limiting (429 ошибки)

Уменьшите `CONCURRENCY` и увеличьте `REQUEST_DELAY` в `.env`:

```env
CONCURRENCY=20
REQUEST_DELAY=1.0
```

### price_card не заполняется

Если `price_card` отсутствует в JSON API, парсер автоматически попытается получить её через XPath. Убедитесь, что:
- `product_url` корректно заполнен
- XPath селекторы актуальны (могут измениться на сайте)

## Технические детали

### Источники данных

1. **Primary source**: Внутренний JSON API (`__internal/catalog/brands/v4/catalog`)
   - Используется для `price_basic` и `price_product`
   - Быстрый и надёжный источник

2. **Fallback source**: XPath парсинг HTML
   - Используется только для `price_card`, если её нет в JSON
   - Минимизировано количество HTML запросов

### Конвертация цен

Все цены в API приходят в копейках и автоматически конвертируются в рубли (деление на 100).

### Логирование

Логи сохраняются в `logs/` с ротацией по дням. API ключи автоматически скрываются в логах.

## Лицензия

Внутренний проект

