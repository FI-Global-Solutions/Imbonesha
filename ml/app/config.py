"""ML service configuration via environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    checkpoint_path: str = "/app/checkpoints/siamese_unet_v2.pth"
    detection_threshold: float = 0.5
    min_polygon_sqm: float = 50.0
    max_polygon_sqm: float = 10_000.0
    # Approximate metres per degree at Kacyiru latitude (-1.94°)
    metres_per_degree: float = 111_000.0

    log_level: str = "INFO"


settings = Settings()
