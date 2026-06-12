from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

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
    OPENROUTER_API_KEY: Optional[str] = None
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENROUTER_MODEL: str = "openai/gpt-4.1"
    USE_MOCK_MODEL: bool = True
    
    # Paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    
    # Configuration
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def has_openrouter_credentials(self) -> bool:
        api_key = (self.OPENROUTER_API_KEY or "").strip()
        return bool(api_key) and api_key != "your_openrouter_api_key_here"

    @property
    def llm_api_key(self) -> str:
        return (self.OPENROUTER_API_KEY or "").strip()

    @property
    def llm_model(self) -> str:
        return self.OPENROUTER_MODEL.strip()

    @property
    def llm_base_url(self) -> str:
        """
        Return an OpenAI-compatible inference endpoint.

        Azure Foundry's project endpoint (/api/projects/<project>) is for the
        Foundry project SDK and requires api-version. The OpenAI client used by
        Strands must instead target the resource's /openai/v1 endpoint.
        """
        raw_url = self.OPENROUTER_BASE_URL.strip()
        parsed = urlsplit(raw_url)
        hostname = (parsed.hostname or "").lower()
        path = parsed.path.rstrip("/")

        if hostname.endswith((".services.ai.azure.com", ".openai.azure.com")):
            if path.startswith("/api/projects/") or not path:
                return urlunsplit((parsed.scheme, parsed.netloc, "/openai/v1/", "", ""))
            if path == "/openai/v1":
                return urlunsplit((parsed.scheme, parsed.netloc, "/openai/v1/", "", ""))

        return raw_url.rstrip("/")

    def llm_model_params_for(self, max_output_tokens: int) -> dict[str, int | float | str]:
        model_name = self.llm_model.lower()
        if model_name.startswith("gpt-5"):
            return {
                "max_completion_tokens": max_output_tokens,
                "reasoning_effort": "minimal",
            }
        if model_name.startswith(("o1", "o3", "o4")):
            return {
                "max_completion_tokens": max_output_tokens,
                "reasoning_effort": "low",
            }
        return {"max_tokens": max_output_tokens, "temperature": 0.7}

    @property
    def llm_model_params(self) -> dict[str, int | float | str]:
        return self.llm_model_params_for(1000)

# Global settings instance
settings = Settings()
