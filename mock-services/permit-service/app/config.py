"""Configuration for the mock permit service.

Settings are loaded from environment variables. In production, the real KUBAKA
adapter will use a different config module entirely — this one is mock-only.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = (
        "postgresql+asyncpg://imbonesha:imbonesha_dev@db:5432/permit_mock"
    )

    # Latency injection — real KUBAKA will be slow and we want to develop
    # against realistic conditions from day one.
    inject_latency_ms: int = 300
    inject_latency_jitter_ms: int = 200

    # Error injection — real government APIs are flaky. Force ourselves to
    # build retry and graceful degradation logic.
    error_rate: float = 0.05  # 5% of requests return 503

    # Active scenario for demos — toggles the seed data distribution.
    # See app/seed.py for what each scenario enables.
    scenario: str = "default"


settings = Settings()
