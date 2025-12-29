"""
Unit-тесты для вспомогательных функций
"""
import unittest
from src.utils import convert_price_to_rubles, extract_price_from_text


class TestPriceConversion(unittest.TestCase):
    """Тесты конвертации цен"""
    
    def test_convert_kopecks_to_rubles(self):
        """Тест конвертации копеек в рубли"""
        # Тест из ТЗ: 43200 коп. = 432.00 руб.
        self.assertEqual(convert_price_to_rubles(43200), 432.00)
        
        # Тест из ТЗ: 97300 коп. = 973.00 руб.
        self.assertEqual(convert_price_to_rubles(97300), 973.00)
        
        # Обычные случаи
        self.assertEqual(convert_price_to_rubles(100), 1.00)
        self.assertEqual(convert_price_to_rubles(1000), 10.00)
        self.assertEqual(convert_price_to_rubles(12345), 123.45)
        
        # Ноль
        self.assertEqual(convert_price_to_rubles(0), 0.0)
        
        # None
        self.assertIsNone(convert_price_to_rubles(None))
    
    def test_extract_price_from_text(self):
        """Тест извлечения цены из текста"""
        # Различные форматы
        self.assertEqual(extract_price_from_text("432,00 ₽"), 432.00)
        self.assertEqual(extract_price_from_text("432.00"), 432.00)
        self.assertEqual(extract_price_from_text("1 234,56"), 1234.56)
        self.assertEqual(extract_price_from_text("999.99"), 999.99)
        
        # Пустые значения
        self.assertIsNone(extract_price_from_text(""))
        self.assertIsNone(extract_price_from_text(None))
        self.assertIsNone(extract_price_from_text("N/A"))


if __name__ == "__main__":
    unittest.main()


