import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Project-wide settings and configuration management.
    Uses pydantic-settings to handle environment variables and .env files.
    """
    # Project Identity
    PROJECT_NAME: str = "MultiAgentSystem"
    VERSION: str = "0.1.0"
    
    # LLM Settings (Placeholders for credentials)
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    
    # Paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    
    # Configuration
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

# Global settings instance
settings = Settings()
