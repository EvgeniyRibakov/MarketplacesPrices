"""Настройка логирования."""
from pathlib import Path
from loguru import logger
import sys


def setup_logger(logs_dir: Path, debug: bool = False):
    """Настраивает логирование."""
    logs_dir = Path(logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)
    
    logger.remove()
    
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="DEBUG" if debug else "INFO",
        colorize=True
    )
    
    log_file = logs_dir / "parser_{time:YYYY-MM-DD}.log"
    logger.add(
        log_file,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="DEBUG" if debug else "INFO",
        rotation="00:00",
        retention="30 days",
        compression="zip",
        encoding="utf-8"
    )
