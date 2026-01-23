"""Адаптивный контроллер задержек для обхода антибота.

Реализует PID-подобный контроллер, который автоматически регулирует задержки
на основе успешности запросов и блокировок.
"""
from typing import Optional
from loguru import logger


class AdaptiveDelayer:
    """Адаптивный контроллер задержек для запросов.
    
    Автоматически увеличивает задержку при блокировках (403) и уменьшает
    при успешных запросах, имитируя умное поведение.
    """
    
    def __init__(
        self,
        initial_delay: float = 1.0,
        min_delay: float = 0.5,
        max_delay: float = 5.0,
        increase_factor: float = 1.5,  # +50% при блокировке
        decrease_factor: float = 0.8,  # -20% при успехе
        success_threshold: int = 5  # Количество успешных запросов для уменьшения
    ):
        """Инициализация адаптивного контроллера.
        
        Args:
            initial_delay: Начальная задержка (секунды)
            min_delay: Минимальная задержка (секунды)
            max_delay: Максимальная задержка (секунды)
            increase_factor: Множитель увеличения при блокировке (1.5 = +50%)
            decrease_factor: Множитель уменьшения при успехе (0.8 = -20%)
            success_threshold: Количество успешных запросов подряд для уменьшения delay
        """
        self.current_delay = initial_delay
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.increase_factor = increase_factor
        self.decrease_factor = decrease_factor
        self.success_threshold = success_threshold
        
        # Счетчики для адаптации
        self.success_count = 0
        self.block_count = 0
        self.total_requests = 0
        
        logger.info(
            f"🔧 AdaptiveDelayer инициализирован: "
            f"начальная задержка={initial_delay:.2f}с, "
            f"диапазон=[{min_delay:.2f}, {max_delay:.2f}]с"
        )
    
    def on_success(self):
        """Вызывается при успешном запросе (статус 200)."""
        self.total_requests += 1
        self.success_count += 1
        self.block_count = 0  # Сбрасываем счетчик блокировок
        
        # Если накопилось достаточно успешных запросов - уменьшаем delay
        if self.success_count >= self.success_threshold:
            old_delay = self.current_delay
            self.current_delay = max(
                self.min_delay,
                self.current_delay * self.decrease_factor
            )
            self.success_count = 0  # Сбрасываем счетчик
            
            if old_delay != self.current_delay:
                logger.info(
                    f"📉 AdaptiveDelayer: уменьшена задержка с {old_delay:.2f}с "
                    f"до {self.current_delay:.2f}с ({self.success_threshold} успешных запросов)"
                )
    
    def on_block(self):
        """Вызывается при блокировке (статус 403 с ozon-antibot)."""
        self.total_requests += 1
        self.block_count += 1
        self.success_count = 0  # Сбрасываем счетчик успехов
        
        # Увеличиваем delay при блокировке
        old_delay = self.current_delay
        self.current_delay = min(
            self.max_delay,
            self.current_delay * self.increase_factor
        )
        
        if old_delay != self.current_delay:
            logger.warning(
                f"📈 AdaptiveDelayer: увеличена задержка с {old_delay:.2f}с "
                f"до {self.current_delay:.2f}с (блокировка антиботом)"
            )
    
    def get_delay(self) -> float:
        """Возвращает текущую задержку.
        
        Returns:
            Текущая задержка в секундах
        """
        return self.current_delay
    
    def get_stats(self) -> dict:
        """Возвращает статистику работы контроллера.
        
        Returns:
            Словарь со статистикой
        """
        success_rate = (
            (self.total_requests - self.block_count) / self.total_requests * 100
            if self.total_requests > 0
            else 0.0
        )
        
        return {
            "current_delay": self.current_delay,
            "total_requests": self.total_requests,
            "block_count": self.block_count,
            "success_rate": success_rate,
            "success_count": self.success_count,
        }
    
    def reset(self):
        """Сбрасывает счетчики (но не delay)."""
        self.success_count = 0
        self.block_count = 0
        self.total_requests = 0
        logger.debug("AdaptiveDelayer: счетчики сброшены")
