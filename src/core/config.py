import os
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # App
    app_name: str = "FinFlow"
    environment: str = "development"
    debug: bool = True
    port: int = 8000

    # Database
    database_url: str = Field(
        default="sqlite+aiosqlite:///./finflow.db",
        description="Async SQLAlchemy database URL (Postgres or SQLite)"
    )

    # MinIO / S3 Storage
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadminpassword"
    minio_bucket: str = "finflow-documents"
    minio_secure: bool = False

    # LLM Settings
    llm_model: str = "gpt-4o-mini"
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None

    # Langfuse Observability
    langfuse_public_key: Optional[str] = None
    langfuse_secret_key: Optional[str] = None
    langfuse_host: str = "http://localhost:3000"

    # Financial & Policy Thresholds
    max_auto_approve_amount: float = 5000.00
    high_risk_threshold_amount: float = 25000.00
    price_variance_tolerance_pct: float = 0.05
    quantity_variance_tolerance_pct: float = 0.00

    # Restricted Vendor / Category List
    restricted_categories: list[str] = [
        "Gambling",
        "Cryptocurrency",
        "Luxury Goods",
        "Unapproved Hardware",
        "Personal Expenses"
    ]


settings = Settings()
