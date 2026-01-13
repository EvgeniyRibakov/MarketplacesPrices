# Настройка Cookies для парсера Wildberries

## Зачем нужны cookies?

Wildberries использует систему защиты от ботов (антибот), которая требует наличия специальных cookies из браузера. Без них запросы будут блокироваться с ошибкой 498.

## Как получить cookies из браузера

### Chrome/Edge:

1. Откройте сайт https://www.wildberries.ru
2. Нажмите `F12` для открытия DevTools
3. Перейдите на вкладку **Application** (Приложение)
4. В левом меню найдите **Cookies** → **https://www.wildberries.ru**
5. Найдите следующие cookies и скопируйте их значения:
   - `wbx-validation-key`
   - `_cp`
   - `routeb`
   - `x_wbaas_token` ⚠️ **ВАЖНО!** Это токен антибота
   - `_wbauid`

### Firefox:

1. Откройте сайт https://www.wildberries.ru
2. Нажмите `F12` для открытия DevTools
3. Перейдите на вкладку **Хранилище** (Storage)
4. Найдите **Cookies** → **https://www.wildberries.ru**
5. Скопируйте значения тех же cookies

## Как добавить cookies в .env файл

Откройте файл `.env` в корне проекта и добавьте следующие строки:

```env
# Cookies из браузера для обхода антибота
WB_COOKIE_WBX_VALIDATION_KEY=ваше_значение_здесь
WB_COOKIE__CP=ваше_значение_здесь
WB_COOKIE_ROUTEB=ваше_значение_здесь
WB_COOKIE_X_WBAAS_TOKEN=ваше_значение_здесь
WB_COOKIE__WBAUID=ваше_значение_здесь
```

**Важно:**
- Замените `ваше_значение_здесь` на реальные значения из браузера
- Не используйте кавычки вокруг значений
- Cookies могут истекать, поэтому их нужно периодически обновлять

## Пример заполненного .env

```env
WB_DEST=-3115289
WB_SPP=30

WB_COOKIE_WBX_VALIDATION_KEY=abc123def456
WB_COOKIE__CP=xyz789
WB_COOKIE_ROUTEB=route_value
WB_COOKIE_X_WBAAS_TOKEN=token_abc123xyz789
WB_COOKIE__WBAUID=wbauid_value
```

## Проверка работы

После добавления cookies запустите парсер:

```bash
python parse_brands.py
```

Если cookies корректны, вы увидите в логах:
```
Используются cookies из .env файла
Загружено 5 cookies из конфигурации: wbx-validation-key, _cp, routeb, x_wbaas_token, _wbauid
```

## Обновление cookies

Cookies могут истекать. Если парсер перестал работать (ошибка 498), обновите cookies:

1. Откройте сайт Wildberries в браузере
2. Получите свежие cookies по инструкции выше
3. Обновите значения в `.env` файле
4. Перезапустите парсер
