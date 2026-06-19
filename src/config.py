from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str

    # Session / Security
    SECRET_KEY: str = "your-secret-key-change-this-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # SMS / External
    AFROMESSAGES_API_KEY: str = ""
    AFROMESSAGES_SENDER: str = "AleMart"
    AFROMESSAGES_FROM: str = ""
    AFROMESSAGES_CALLBACK: str = ""
    CLOUDINARY_URL: str

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
