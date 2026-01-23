# Dockerfile для HTTP-only режима (LIGHT режим)
# Используется для хостинга на Railway/Fly.io без Playwright

FROM python:3.12-slim

WORKDIR /app

# Копируем только requirements-core.txt (без Playwright)
COPY requirements-core.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements-core.txt

# Копируем код проекта
COPY . .

# Создаем директорию для cookies (если используется Cookies-as-a-Service)
RUN mkdir -p cookies

# Устанавливаем переменные окружения по умолчанию
ENV OZON_MODE=light
ENV PYTHONUNBUFFERED=1

# Команда запуска
CMD ["python", "parse_ozon_sellers.py"]
