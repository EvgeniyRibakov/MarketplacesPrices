#!/bin/bash
# Скрипт авто-установки для Linux/Mac

echo "🚀 Установка Ozon парсера (LIGHT режим)..."
echo ""

# Проверяем Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 не найден. Установите Python 3.8+ и повторите."
    exit 1
fi

# Создаем виртуальное окружение
echo "📦 Создание виртуального окружения..."
python3 -m venv venv

# Активируем виртуальное окружение
echo "🔧 Активация виртуального окружения..."
source venv/bin/activate

# Устанавливаем основные зависимости
echo "📥 Установка основных зависимостей (requirements-core.txt)..."
pip install --upgrade pip
pip install -r requirements-core.txt

echo ""
echo "✅ Установка завершена (LIGHT режим)"
echo ""
echo "💡 Для FULL режима (с Playwright fallback):"
echo "   pip install -r requirements-playwright.txt"
echo "   playwright install chromium"
echo ""
echo "🚀 Для запуска парсера:"
echo "   source venv/bin/activate"
echo "   python parse_ozon_sellers.py"
echo ""
