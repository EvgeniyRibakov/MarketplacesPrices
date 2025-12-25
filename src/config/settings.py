"""Настройки приложения."""
import os
from pathlib import Path
from typing import Dict, Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Настройки приложения."""
    
    # ============================================
    # WILDBERRIES
    # ============================================
    # API ключи для кабинетов WB
    wb_api_key_mau: Optional[str] = Field(default=None, alias="WB_API_KEY_MAU")
    wb_api_key_mab: Optional[str] = Field(default=None, alias="WB_API_KEY_MAB")
    wb_api_key_mma: Optional[str] = Field(default=None, alias="WB_API_KEY_MMA")
    wb_api_key_cosmo: Optional[str] = Field(default=None, alias="WB_API_KEY_COSMO")
    wb_api_key_dreamlab: Optional[str] = Field(default=None, alias="WB_API_KEY_DREAMLAB")
    wb_api_key_beautylab: Optional[str] = Field(default=None, alias="WB_API_KEY_BEAUTYLAB")
    
    # ID кабинетов WB
    wb_cabinet_mau_id: str = Field(default="53607", alias="WB_CABINET_MAU_ID")
    wb_cabinet_mab_id: str = Field(default="121614", alias="WB_CABINET_MAB_ID")
    wb_cabinet_mma_id: str = Field(default="174711", alias="WB_CABINET_MMA_ID")
    wb_cabinet_cosmo_id: str = Field(default="224650", alias="WB_CABINET_COSMO_ID")
    wb_cabinet_dreamlab_id: str = Field(default="1140223", alias="WB_CABINET_DREAMLAB_ID")
    wb_cabinet_beautylab_id: str = Field(default="4428365", alias="WB_CABINET_BEAUTYLAB_ID")
    
    # ============================================
    # OZON
    # ============================================
    # API ключи для 3 кабинетов Ozon
    ozon_api_key_cosmo: Optional[str] = Field(default=None, alias="OZON_API_KEY_cosmo")
    ozon_client_id_cosmo: Optional[str] = Field(default=None, alias="OZON_CLIENT_ID_cosmo")
    
    ozon_api_key_dream: Optional[str] = Field(default=None, alias="OZON_API_KEY_dream")
    ozon_client_id_dream: Optional[str] = Field(default=None, alias="OZON_CLIENT_ID_dream")
    
    ozon_api_key_beauty: Optional[str] = Field(default=None, alias="OZON_API_KEY_beauty")
    ozon_client_id_beauty: Optional[str] = Field(default=None, alias="OZON_CLIENT_ID_beauty")
    
    # ============================================
    # НАСТРОЙКИ ПАРСЕРА
    # ============================================
    request_delay: float = Field(default=0.5, alias="REQUEST_DELAY")
    max_concurrent_requests: int = Field(default=10, alias="MAX_CONCURRENT_REQUESTS")
    request_timeout: int = Field(default=30, alias="REQUEST_TIMEOUT")
    
    output_dir: Path = Field(default=Path("./output"), alias="OUTPUT_DIR")
    logs_dir: Path = Field(default=Path("./logs"), alias="LOGS_DIR")
    
    debug: bool = Field(default=False, alias="DEBUG")
    
    class Config:
        """Конфигурация Pydantic."""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
    
    def __init__(self, **kwargs):
        """Инициализация настроек."""
        super().__init__(**kwargs)
        # Создаём необходимые папки
        self.output_dir = Path(self.output_dir).resolve()
        self.logs_dir = Path(self.logs_dir).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
    
    def get_wb_api_keys(self) -> Dict[str, Optional[str]]:
        """Получить все API ключи WB.
        
        Returns:
            Словарь {cabinet_name: api_key}
        """
        return {
            "mau": self.wb_api_key_mau,
            "mab": self.wb_api_key_mab,
            "mma": self.wb_api_key_mma,
            "cosmo": self.wb_api_key_cosmo,
            "dreamlab": self.wb_api_key_dreamlab,
            "beautylab": self.wb_api_key_beautylab,
        }
    
    def get_wb_cabinet_ids(self) -> Dict[str, str]:
        """Получить все ID кабинетов WB.
        
        Returns:
            Словарь {cabinet_name: cabinet_id}
        """
        return {
            "mau": self.wb_cabinet_mau_id,
            "mab": self.wb_cabinet_mab_id,
            "mma": self.wb_cabinet_mma_id,
            "cosmo": self.wb_cabinet_cosmo_id,
            "dreamlab": self.wb_cabinet_dreamlab_id,
            "beautylab": self.wb_cabinet_beautylab_id,
        }
    
    def get_ozon_api_keys(self) -> Dict[str, Optional[str]]:
        """Получить все API ключи Ozon.
        
        Returns:
            Словарь {cabinet_name: api_key}
        """
        return {
            "cosmo": self.ozon_api_key_cosmo,
            "dream": self.ozon_api_key_dream,
            "beauty": self.ozon_api_key_beauty,
        }
    
    def get_ozon_client_ids(self) -> Dict[str, Optional[str]]:
        """Получить все Client ID для кабинетов Ozon.
        
        Returns:
            Словарь {cabinet_name: client_id}
        """
        return {
            "cosmo": self.ozon_client_id_cosmo,
            "dream": self.ozon_client_id_dream,
            "beauty": self.ozon_client_id_beauty,
        }

