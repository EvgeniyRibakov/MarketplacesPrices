# Парсер цен для маркетплейсов

## Структура проекта

```
MParsing/
├── src/                    # Основной код
│   ├── api/               # API клиенты
│   ├── parsers/           # Парсеры
│   └── utils/             # Утилиты
│
├── config/                 # Конфигурация
│   └── brands_config.json
│
├── scripts/                # Скрипты
│   ├── bat/               # Батч-файлы
│   ├── run_parse_brands.bat
│   └── run_parse_brands.ps1
│
├── docs/                   # Документация
│
├── parse_brands.py         # Основной скрипт (в корне для удобства)
├── .env                    # Секреты (не коммитится)
└── requirements.txt        # Зависимости
```

## Установка зависимостей

```bash
python -m pip install -r requirements.txt
```

или используйте скрипт:

```bash
scripts/install_dependencies.bat
```

## Настройка Cookies

⚠️ **ВАЖНО**: Для работы парсера необходимы cookies из браузера для обхода антибота Wildberries.

Подробная инструкция: [docs/COOKIES_SETUP.md](docs/COOKIES_SETUP.md)

Кратко:
1. Откройте https://www.wildberries.ru в браузере
2. Откройте DevTools (F12) → Application → Cookies
3. Скопируйте значения cookies: `wbx-validation-key`, `_cp`, `routeb`, `x_wbaas_token`, `_wbauid`
4. Добавьте их в `.env` файл в формате:
   ```env
   WB_COOKIE_WBX_VALIDATION_KEY=значение
   WB_COOKIE__CP=значение
   WB_COOKIE_ROUTEB=значение
   WB_COOKIE_X_WBAAS_TOKEN=значение
   WB_COOKIE__WBAUID=значение
   ```

## Запуск

```bash
python parse_brands.py
```

или

```bash
scripts/run_parse_brands.bat
```

## Решение проблем с pip

КРИТИЧНО: В Windows PowerShell команда `pip` может открывать файл `pip.exe` вместо выполнения.

### Правильное использование:
- ❌ НЕ использовать: `pip install <пакет>` (может открыть файл)
- ✅ ВСЕГДА использовать: `python -m pip install <пакет>`

### Установка зависимостей:
```bash
python -m pip install -r requirements.txt
```

или используйте скрипт (автоматически использует `python -m pip`):

```bash
scripts/install_dependencies.bat
```

### Почему это происходит:
PowerShell может пытаться открыть `pip.exe` как файл вместо выполнения команды. Использование `python -m pip` обходит эту проблему, так как Python сам вызывает pip как модуль.
