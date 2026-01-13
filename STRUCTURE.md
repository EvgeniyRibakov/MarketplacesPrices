# Структура проекта

## Финальная организация

```
MParsing/
├── src/                    # Основной код
│   ├── api/               # API клиенты
│   │   └── wb_catalog_api.py
│   ├── parsers/           # Парсеры
│   │   └── wb_parser.py
│   └── utils/             # Утилиты
│       └── logger.py
│
├── config/                 # Конфигурация
│   └── brands_config.json
│
├── scripts/                # Скрипты
│   ├── bat/               # Батч-файлы для git операций
│   │   ├── git_commit_push.bat
│   │   ├── fix_rebase_and_push.bat
│   │   └── ...
│   ├── run_parse_brands.bat
│   ├── run_parse_brands.ps1
│   └── *.py               # Вспомогательные Python скрипты
│
├── docs/                   # Документация
│   └── *.md
│
├── parse_brands.py         # Основной скрипт (в корне для удобства)
├── .env                    # Секреты (не коммитится, остается в корне)
├── requirements.txt        # Зависимости
└── README.md               # Главная документация
```

## Что в корне

В корне остаются только:
- `parse_brands.py` - основной рабочий скрипт
- `.env` - файлы с секретами (не коммитятся)
- `requirements.txt` - зависимости
- `README.md` - документация

## Что в папках

- **src/** - весь основной код
- **config/** - вся конфигурация
- **scripts/** - все скрипты (включая git операции)
- **docs/** - вся документация
