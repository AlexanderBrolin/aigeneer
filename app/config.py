from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM
    aitunnel_base_url: str = "https://api.aitunnel.ru/v1/"
    aitunnel_api_key: str = ""
    model_main: str = "claude-sonnet-4-6"
    model_fast: str = "claude-haiku-4-5"

    # Telegram
    tg_bot_token: str = ""
    tg_allowed_users: str = ""  # comma-separated user IDs
    tg_chat_id: str = ""

    # Database
    database_url: str = "mysql+aiomysql://opsagent:changeme@db:3306/opsagent"

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # Web panel
    secret_key: str = "change-me"
    admin_username: str = "admin"
    admin_password: str = "changeme"

    # SSH defaults
    ssh_default_key_path: str = "~/.ssh/id_rsa"
    ssh_default_user: str = "deploy"

    # Schedule
    check_interval_minutes: int = 5

    @property
    def tg_allowed_user_ids(self) -> list[int]:
        if not self.tg_allowed_users:
            return []
        return [int(uid.strip()) for uid in self.tg_allowed_users.split(",") if uid.strip()]


settings = Settings()
