import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    db_host: str = "localhost"
    db_port: int = 5432
    db_user: str = "ft_user"
    db_password: str = "ft_password"
    db_name: str = "ft_platform"

    # Fantacalcio.it
    fanta_username: str = ""
    fanta_password: str = ""
    fanta_base_url: str = "https://www.fantacalcio.it/"
    fanta_api: str = "api/v1/"
    fanta_leghe_base_url: str = "https://leghe.fantacalcio.it/"
    fanta_year_quotazioni: str = "24"
    fanta_lega_name: str = ""
    fanta_session_file: str = "./tamarros_session.json"
    fanta_app_key_fallback: str = "bZ2FAQDZYYBVEehhFuM9pAsJ3waL0Vsg"

    # App
    debug: bool = False
    log_level: str = "INFO"
    download_folder: str = "./downloads/"
    upload_folder: str = "./uploads/logos/"
    cors_origins: list[str] = ["http://localhost:4200"]

    @property
    def database_url(self) -> str:
        return (
            f"postgresql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    model_config = {"env_file": ".env", "case_sensitive": False}


settings = Settings()
