"""Application configuration using pydantic-settings."""

from functools import lru_cache
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Application
    APP_NAME: str = "SigmaPilot Lens"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"

    # Database
    DATABASE_URL: str = Field(..., description="PostgreSQL connection string")
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    RETENTION_DAYS: int = 180

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_MAX_CONNECTIONS: int = 10

    # Security
    # Network-level security is used instead of API keys
    # All services are isolated within Docker network

    # Rate Limiting
    RATE_LIMIT_PER_MIN: int = 60
    RATE_LIMIT_BURST: int = 120
    RATE_LIMIT_ENABLED: bool = True

    # Queue Configuration
    RETRY_MAX: int = 5
    RETRY_BACKOFF: str = "exponential_jitter"
    RETRY_BASE_DELAY_MS: int = 2000
    RETRY_MAX_DELAY_MS: int = 30000
    DLQ_ENABLED: bool = True
    CONSUMER_GROUP: str = "lens-workers"
    CONSUMER_BATCH_SIZE: int = 10

    # Feature Profile
    FEATURE_PROFILE: str = "trend_follow_v1"
    TIMEFRAMES: str = "15m,1h,4h"

    # Stale Data Thresholds (seconds)
    STALE_MID_S: int = 5
    STALE_L2_S: int = 10
    STALE_CTX_S: int = 60
    STALE_CANDLE_MULTIPLIER: int = 2

    # Market Data Providers
    PROVIDER_PRIMARY: str = "hyperliquid"
    PROVIDER_TIMEOUT_MS: int = 10000
    PROVIDER_RETRY_COUNT: int = 3
    HYPERLIQUID_BASE_URL: str = "https://api.hyperliquid.xyz"
    HYPERLIQUID_WS_URL: str = "wss://api.hyperliquid.xyz/ws"

    # AI Models
    AI_MODELS: str = "chatgpt,gemini"

    # WebSocket
    WS_ENABLED: bool = True
    WS_PING_INTERVAL_S: int = 30
    WS_PING_TIMEOUT_S: int = 10
    WS_MAX_CONNECTIONS: int = 100

    # Observability
    METRICS_ENABLED: bool = True
    METRICS_PATH: str = "/metrics"
    HEALTH_PATH: str = "/health"
    READY_PATH: str = "/ready"

    @property
    def timeframes_list(self) -> List[str]:
        """Parse TIMEFRAMES into a list."""
        return [tf.strip() for tf in self.TIMEFRAMES.split(",")]

    @property
    def ai_models_list(self) -> List[str]:
        """Parse AI_MODELS into a list."""
        return [m.strip() for m in self.AI_MODELS.split(",")]

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v = v.upper()
        if v not in valid_levels:
            raise ValueError(f"LOG_LEVEL must be one of {valid_levels}")
        return v

    @field_validator("FEATURE_PROFILE")
    @classmethod
    def validate_feature_profile(cls, v: str) -> str:
        """Validate feature profile."""
        valid_profiles = {"trend_follow_v1", "crypto_perps_v1", "full_v1"}
        if v not in valid_profiles:
            raise ValueError(f"FEATURE_PROFILE must be one of {valid_profiles}")
        return v


class ModelConfig(BaseSettings):
    """Per-model configuration loaded dynamically."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    provider: str
    api_key: str
    model_id: str
    timeout_ms: int = 30000
    max_tokens: int = 1000
    prompt_path: Optional[str] = None

    @classmethod
    def for_model(cls, model_name: str) -> "ModelConfig":
        """Load configuration for a specific model."""
        import os

        prefix = f"MODEL_{model_name.upper()}_"
        return cls(
            provider=os.getenv(f"{prefix}PROVIDER", ""),
            api_key=os.getenv(f"{prefix}API_KEY", ""),
            model_id=os.getenv(f"{prefix}MODEL_ID", ""),
            timeout_ms=int(os.getenv(f"{prefix}TIMEOUT_MS", "30000")),
            max_tokens=int(os.getenv(f"{prefix}MAX_TOKENS", "1000")),
            prompt_path=os.getenv(f"{prefix}PROMPT_PATH"),
        )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
