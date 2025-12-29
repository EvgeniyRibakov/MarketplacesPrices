# Инструкция по установке

## Проблема: "pip" открывается как файл вместо выполнения команды

Если при выполнении `pip install -r requirements.txt` открывается диалог выбора приложения, это означает, что `pip` не найден в PATH или Windows пытается открыть его как файл.

## Решение

### Вариант 1: Использовать `python -m pip` (рекомендуется)

Вместо:
```bash
pip install -r requirements.txt
```

Используйте:
```bash
python -m pip install -r requirements.txt
```

Это работает всегда, так как использует Python из PATH.

### Вариант 2: Добавить Python в PATH

1. Найдите путь к Python:
   ```powershell
   python -c "import sys; print(sys.executable)"
   ```

2. Добавьте в PATH:
   - Путь к Python (например: `C:\Users\Acer\AppData\Local\Programs\Python\Python311`)
   - Путь к Scripts (например: `C:\Users\Acer\AppData\Local\Programs\Python\Python311\Scripts`)

3. Перезапустите терминал

### Вариант 3: Использовать полный путь к pip

Найдите pip:
```powershell
python -m pip show pip
```

Используйте полный путь:
```powershell
C:\Users\Acer\AppData\Local\Programs\Python\Python311\Scripts\pip.exe install -r requirements.txt
```

## Проверка установки

После установки проверьте:

```bash
python -m pip list
```

Должны быть установлены:
- python-dotenv
- aiohttp
- lxml
- openpyxl
- pandas

## Быстрая установка (копировать-вставить)

```powershell
cd wb_price_parser
python -m pip install -r requirements.txt
```

