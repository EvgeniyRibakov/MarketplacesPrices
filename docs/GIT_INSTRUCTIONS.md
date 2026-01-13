# Инструкция по коммиту и пушу изменений

## Проблема с терминалом

В PowerShell все команды получают префикс "qс" (кириллическая "с"), что делает невозможным их выполнение. Это проблема с кодировкой или алиасами в профиле PowerShell.

## Решения

### Решение 1: Использовать батч-файл (рекомендуется)

Просто запустите:
```bash
scripts/bat/git_commit_push.bat
```

Этот файл выполнит все необходимые git операции:
1. `git status` - проверка статуса
2. `git add .` - добавление всех изменений
3. `git commit` - создание коммита с описанием
4. `git push origin main` - отправка в ветку main

### Решение 2: Использовать Python скрипт

```bash
python scripts/git_commit_push.py
```

### Решение 3: Использовать cmd напрямую

Откройте обычную командную строку (cmd, не PowerShell) и выполните:
```bash
cd "C:\Users\Acer\Cursor projects\MParsing"
git add .
git commit -m "Добавлен парсинг цен по брендам через внутренний API WB"
git push origin main
```

## ⚠️ Важно: Проблема с rebase

Если коммит был создан во время активного rebase (detached HEAD), изменения могут не попасть в ветку main.

### Решение проблемы rebase:

**Вариант 1: Использовать специальный скрипт (рекомендуется)**
```bash
scripts/bat/fix_rebase_and_push.bat
```
или
```bash
python scripts/fix_rebase_and_push.py
```

Этот скрипт:
1. Завершит или прервёт активный rebase
2. Переключится на ветку main
3. Применит все изменения
4. Запушит в main

**Вариант 2: Вручную через cmd**
```bash
# Завершить или прервать rebase
git rebase --continue
# или
git rebase --abort

# Переключиться на main
git checkout main

# Получить последние изменения
git pull origin main

# Добавить и закоммитить
git add .
git commit -m "Добавлен парсинг цен по брендам через внутренний API WB"
git push origin main
```
