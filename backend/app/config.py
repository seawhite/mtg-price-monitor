from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_default_region: str = "us-west-2"
    sns_topic_arn: str = "arn:aws:sns:us-west-2:328883027245:cwhitepersonal"
    alert_cooldown_minutes: int = 30
    check_interval_seconds: int = 60
    database_url: str = "sqlite:///data/monitors.db"

    class Config:
        env_file = "mtg-price-monitor.env"


settings = Settings()
