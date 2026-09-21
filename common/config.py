import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")

    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "postgres")
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT: str = os.getenv("POSTGRES_PORT", "5432")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "tender_db")

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def DATABASE_URL_SYNC(self) -> str:
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    SECRET_KEY: str = os.getenv("SECRET_KEY", "")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))

    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "http://localhost:5173")

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    ROSTENDER_EMAIL: str = os.getenv("ROSTENDER_EMAIL", "")
    ROSTENDER_PASSWORD: str = os.getenv("ROSTENDER_PASSWORD", "")
    ROSTENDER_BASE_URL: str = "https://rostender.info"

    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    NOTIFICATION_THRESHOLD: float = float(os.getenv("NOTIFICATION_THRESHOLD", "0.8"))

    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    EMBEDDING_DIMENSIONS: int = int(os.getenv("EMBEDDING_DIMENSIONS", "1536"))
    SIMILARITY_THRESHOLD: float = float(os.getenv("SIMILARITY_THRESHOLD", "0.5"))

    TENDER_CATEGORIES: list[str] = ["target", "prospective", "possible", "low"]

    TENDER_STATUSES: list[str] = ["new", "viewed", "participating", "won", "lost"]

    TEMPLATE_TYPES: list[str] = ["proposal", "letter", "requirements"]

    def validate(self) -> list[str]:
        errors = []

        if not self.OPENAI_API_KEY:
            errors.append("OPENAI_API_KEY is required")

        if not self.TELEGRAM_BOT_TOKEN:
            errors.append("TELEGRAM_BOT_TOKEN is required")

        return errors

    def validate_web(self) -> list[str]:
        """Проверки для веб-приложения: боту Telegram и OpenAI тут не нужны."""
        errors = []

        if not self.SECRET_KEY:
            errors.append(
                "SECRET_KEY is required: без него JWT подписывается пустым " "ключом и токен может подделать кто угодно"
            )
        elif len(self.SECRET_KEY) < 32:
            errors.append("SECRET_KEY must be at least 32 characters long")

        return errors


config = Config()
OPENAI_API_KEY = config.OPENAI_API_KEY
