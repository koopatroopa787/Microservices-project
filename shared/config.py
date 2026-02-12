"""Shared configuration."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Base settings for all services."""

    # Service info
    service_name: str = "saga-service"
    service_port: int = 8000

    # Database
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "saga"

    # RabbitMQ
    rabbitmq_user: str = "guest"
    rabbitmq_password: str = "guest"
    rabbitmq_host: str = "localhost"
    rabbitmq_port: int = 5672

    # Redis (for analytics and caching)
    redis_host: str = "localhost"
    redis_port: int = 6379

    # Logging
    log_level: str = "INFO"

    @property
    def database_url(self) -> str:
        """Get async PostgreSQL connection URL."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def rabbitmq_url(self) -> str:
        """Get RabbitMQ connection URL."""
        return (
            f"amqp://{self.rabbitmq_user}:{self.rabbitmq_password}"
            f"@{self.rabbitmq_host}:{self.rabbitmq_port}/"
        )

    @property
    def redis_url(self) -> str:
        """Get Redis connection URL."""
        return f"redis://{self.redis_host}:{self.redis_port}"

    class Config:
        env_file = ".env"
        case_sensitive = False
