# Парсинг цен по брендам через внутренний API WB

## Описание

Реализован парсинг цен для брендов Wildberries через внутренний API endpoint `__internal/catalog/brands/v4/catalog`.

## Что было сделано

1. **Модуль `src/api/wb_catalog_api.py`**:
   - Асинхронный клиент для работы с внутренним API
   - Автоматическая загрузка всех страниц каталога
   - Парсинг цен: `price.basic`, `price.product` (конвертация из копеек в рубли)
   - Определение кабинета по `supplierId`

2. **Обновлён `src/parsers/wb_parser.py`**:
   - Добавлен метод `parse_brand_catalog()` для парсинга по брендам
   - Сохранена обратная совместимость

3. **Скрипт `parse_brands.py`**:
   - Парсинг всех брендов из `brands_config.json`
   - Экспорт результатов в Excel с полной статистикой

4. **Утилиты**:
   - `src/utils/logger.py` - настройка логирования
   - Скрипты для запуска: `run_parse_brands.bat`, `run_parse_brands.ps1`

## Конфигурация

Конфигурация брендов хранится в `brands_config.json`:
- `likato` (ID: 68941)
- `lavant` (ID: 75848)
- `epilprofi` (ID: 138499)

Общие параметры из `.env`:
- `WB_DEST=-1257786` (ПВЗ: г Москва, ул Никольская д. 7-9, стр. 4)
- `WB_SPP=30`

## Запуск

### Вариант 1: Через Python скрипт
```bash
python parse_brands.py
```

### Вариант 2: Через батч-файл (Windows)
```bash
run_parse_brands.bat
```

### Вариант 3: Через PowerShell скрипт
```powershell
.\run_parse_brands.ps1
```

### Вариант 4: С проверкой окружения
```bash
python scripts/check_and_run.py
```

## Результаты

Результаты сохраняются в `output/wb_brands_prices_YYYY-MM-DD_HH-MM-SS.xlsx` с колонками:
- `brand_id`, `brand_name` - ID и название бренда
- `product_id`, `product_name` - ID и название товара
- `cabinet_id`, `cabinet_name` - ID и название кабинета
- `supplier_id`, `supplier_name` - ID и название поставщика
- `size_id`, `size_name` - ID и название размера
- `price_basic` - базовая цена (рубли)
- `price_product` - цена продукта (рубли)
- `price_card` - цена с картой (будет заполнено позже через XPath)
- `source_price_basic`, `source_price_product`, `source_price_card` - источники данных
