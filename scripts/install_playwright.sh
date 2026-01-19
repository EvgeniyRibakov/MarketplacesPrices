#!/bin/bash
# Скрипт для установки Playwright и браузеров (Linux/macOS)

echo "======================================================================"
echo "Установка Playwright и браузеров для обхода антиботов Ozon"
echo "======================================================================"
echo ""

# Устанавливаем Playwright и playwright-stealth
echo "[1/2] Установка библиотек Playwright..."
python3 -m pip install playwright playwright-stealth

if [ $? -ne 0 ]; then
    echo "ОШИБКА: Не удалось установить библиотеки Playwright"
    exit 1
fi

echo ""
echo "[2/2] Установка браузеров Playwright..."
python3 -m playwright install chromium

if [ $? -ne 0 ]; then
    echo "ОШИБКА: Не удалось установить браузеры Playwright"
    exit 1
fi

echo ""
echo "======================================================================"
echo "✅ Установка завершена успешно!"
echo "======================================================================"
echo ""
