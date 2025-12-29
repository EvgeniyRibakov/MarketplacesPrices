# Инструкции по завершению операций с git

## Что уже сделано:

1. ✅ Создана ветка `development`
2. ✅ Переключились на ветку `development` (для сохранения файлов)
3. ✅ Переключились обратно на `main`
4. ✅ Удалены большинство ненужных файлов

## Что нужно сделать вручную:

### Вариант 1: Использовать готовый скрипт

Запустите скрипт `complete_git_operations.py`:

```bash
python complete_git_operations.py
```

или

```bash
py complete_git_operations.py
```

Скрипт автоматически:
- Сохранит все файлы в ветку `development`
- Очистит ветку `main`
- Закоммитит изменения

### Вариант 2: Выполнить команды вручную

#### Шаг 1: Сохранение всех файлов в development

```bash
git checkout development
git add -A
git commit -m "chore: сохранение текущего прогресса в ветку development"
```

#### Шаг 2: Очистка main ветки

```bash
git checkout main
```

Затем удалите папку `src` и временные скрипты:
- Запустите `python remove_src.py` (удалит папку src и временные скрипты)
- Или удалите вручную: папку `src`, файлы `complete_git_operations.py` и `remove_src.py`

#### Шаг 3: Коммит изменений в main

```bash
git add -A
git commit -m "chore: очистка main ветки, оставлены только необходимые файлы"
```

#### Шаг 4: Отправка в GitHub

```bash
# Отправка ветки development
git checkout development
git push -u origin development

# Отправка ветки main
git checkout main
git push origin main
```

## Файлы, которые должны остаться в main:

- `.git` (папка)
- `.gitignore`
- `context_project`
- `Articles.xlsx`
- `.env` (если есть)
- `.env_sample`
- `.cursor` (папка)

Все остальные файлы должны быть удалены из main, но сохранены в ветке `development`.


