"""Настройка логирования."""
import sys
from pathlib import Path
from loguru import logger


def setup_logger(logs_dir: Path, debug: bool = False) -> None:
    """Настройка логирования.
    
    Args:
        logs_dir: Папка для логов
        debug: Режим отладки
    """
    # Удаляем стандартный обработчик
    logger.remove()
    
    # Уровень логирования
    level = "DEBUG" if debug else "INFO"
    
    # Формат логов
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )
    
    # Логирование в консоль
    # Используем UTF-8 для Windows консоли
    import sys
    if sys.platform == "win32":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    
    logger.add(
        sys.stdout,
        format=log_format,
        level=level,
        colorize=True,
        encoding="utf-8",
    )
    
    # Логирование в файл (все логи)
    logger.add(
        logs_dir / "app_{time:YYYY-MM-DD}.log",
        format=log_format,
        level=level,
        rotation="00:00",
        retention="30 days",
        compression="zip",
        encoding="utf-8",
    )
    
    # Логирование ошибок в отдельный файл
    logger.add(
        logs_dir / "errors_{time:YYYY-MM-DD}.log",
        format=log_format,
        level="ERROR",
        rotation="00:00",
        retention="30 days",
        compression="zip",
        encoding="utf-8",
    )

