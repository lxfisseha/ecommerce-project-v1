from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator


class Settings(BaseSettings):
    DATABASE_URL: str

    # Session / Security — must be set via environment or .env, no default
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # SMS / External
    AFROMESSAGES_API_KEY: str = ""
    AFROMESSAGES_SENDER: str = ""
    AFROMESSAGES_FROM: str = ""
    AFROMESSAGES_CALLBACK: str = ""
    CLOUDINARY_URL: str

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("SECRET_KEY")
    @classmethod
    def secret_key_strength(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters long")
        return v


settings = Settings()
