from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    app_name: str = "whatsapp-ai-saas"
    environment: str = "development"
    log_level: str = "info"

    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db_name: str = "whatsapp_saas"

    cors_origins: str = "http://localhost:3000"

    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_business_account_id: str = ""
    webhook_verify_token: str = "my_verify_token_123"
    meta_app_secret: str = ""

    openai_api_key: str = ""
    openai_default_model: str = "gpt-4o"
    openai_max_tokens: int = 1024
    openai_temperature: float = 0.7


settings = Settings()
