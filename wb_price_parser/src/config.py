"""
Конфигурация проекта - загрузка и валидация параметров из .env
"""
import os
from pathlib import Path
from typing import Dict, Optional
from dotenv import load_dotenv

from .models import Cabinet


class Config:
    """Класс для управления конфигурацией проекта"""
    
    # Кабинеты продавцов (фиксированные значения из ТЗ)
    CABINETS = {
        "MAU": 53607,
        "MAB": 121614,
        "MMA": 174711,
        "cosmo": 224650,
        "dreamlab": 1140223,
        "beautylab": 4428365,
    }
    
    def __init__(self, env_file: Optional[str] = None):
        """
        Инициализация конфигурации
        
        Args:
            env_file: Путь к .env файлу (по умолчанию ищет в корне проекта)
        """
        # Определяем корень проекта (на уровень выше src/)
        project_root = Path(__file__).parent.parent
        
        # Загружаем .env
        if env_file:
            env_path = Path(env_file)
        else:
            env_path = project_root / ".env"
        
        if env_path.exists():
            load_dotenv(env_path)
        else:
            # Пробуем загрузить из корня проекта
            load_dotenv(project_root / ".env")
        
        # Загружаем обязательные параметры
        self._load_required_params()
        
        # Загружаем опциональные параметры
        self._load_optional_params()
        
        # Загружаем кабинеты
        self._load_cabinets()
    
    def _load_required_params(self):
        """Загрузка обязательных параметров с валидацией"""
        self.wb_brand_id = self._get_int("WB_BRAND_ID", required=True)
        self.wb_dest = self._get_int("WB_DEST", required=True)
        self.wb_spp = self._get_int("WB_SPP", default=30)
        self.concurrency = self._get_int("CONCURRENCY", default=40)
        self.output_file = self._get_str("OUTPUT_FILE", default="wb_prices.xlsx")
    
    def _load_optional_params(self):
        """Загрузка опциональных параметров"""
        self.concurrency_html = self._get_int("CONCURRENCY_HTML", default=5)
        self.request_delay = self._get_float("REQUEST_DELAY", default=0.5)
        self.request_timeout = self._get_int("REQUEST_TIMEOUT", default=30)
        self.log_level = self._get_str("LOG_LEVEL", default="INFO")
        self.debug = self._get_bool("DEBUG", default=False)
        
        # Пути
        project_root = Path(__file__).parent.parent
        output_dir = self._get_str("OUTPUT_DIR", default="./output")
        logs_dir = self._get_str("LOGS_DIR", default="./logs")
        
        self.output_dir = Path(output_dir) if not Path(output_dir).is_absolute() else Path(output_dir)
        self.logs_dir = Path(logs_dir) if not Path(logs_dir).is_absolute() else Path(logs_dir)
        
        # Создаём директории если их нет
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
    
    def _load_cabinets(self):
        """Загрузка кабинетов продавцов"""
        self.cabinets: Dict[str, Cabinet] = {}
        
        for name, cabinet_id in self.CABINETS.items():
            api_key = self._get_str(f"WB_API_KEY_{name}", required=False)
            env_cabinet_id = self._get_int(f"WB_CABINET_{name}_ID", default=cabinet_id)
            
            # Используем ID из .env если указан, иначе из фиксированного списка
            final_id = env_cabinet_id if env_cabinet_id != cabinet_id else cabinet_id
            
            self.cabinets[name] = Cabinet(
                name=name,
                cabinet_id=final_id,
                api_key=api_key
            )
    
    def _get_str(self, key: str, default: Optional[str] = None, required: bool = False) -> str:
        """Получить строковое значение из окружения"""
        value = os.getenv(key, default)
        if required and value is None:
            raise ValueError(f"Обязательный параметр {key} не найден в .env")
        return value or ""
    
    def _get_int(self, key: str, default: Optional[int] = None, required: bool = False) -> int:
        """Получить целочисленное значение из окружения"""
        value = os.getenv(key)
        if value is None:
            if required:
                raise ValueError(f"Обязательный параметр {key} не найден в .env")
            return default or 0
        try:
            return int(value)
        except ValueError:
            raise ValueError(f"Параметр {key} должен быть целым числом, получено: {value}")
    
    def _get_float(self, key: str, default: Optional[float] = None, required: bool = False) -> float:
        """Получить значение с плавающей точкой из окружения"""
        value = os.getenv(key)
        if value is None:
            if required:
                raise ValueError(f"Обязательный параметр {key} не найден в .env")
            return default or 0.0
        try:
            return float(value)
        except ValueError:
            raise ValueError(f"Параметр {key} должен быть числом, получено: {value}")
    
    def _get_bool(self, key: str, default: bool = False) -> bool:
        """Получить булево значение из окружения"""
        value = os.getenv(key, str(default)).lower()
        return value in ("true", "1", "yes", "on")
    
    def get_cabinet_by_id(self, cabinet_id: int) -> Optional[Cabinet]:
        """Получить кабинет по ID"""
        for cabinet in self.cabinets.values():
            if cabinet.cabinet_id == cabinet_id:
                return cabinet
        return None
    
    def get_cabinet_by_name(self, name: str) -> Optional[Cabinet]:
        """Получить кабинет по имени"""
        return self.cabinets.get(name)


# Глобальный экземпляр конфигурации (будет инициализирован при первом импорте)
_config: Optional[Config] = None


def get_config(env_file: Optional[str] = None) -> Config:
    """
    Получить экземпляр конфигурации (singleton)
    
    Args:
        env_file: Путь к .env файлу
    
    Returns:
        Экземпляр Config
    """
    global _config
    if _config is None:
        _config = Config(env_file)
    return _config


