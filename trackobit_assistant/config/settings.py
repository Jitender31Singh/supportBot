from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')
    app_env: str = 'local'
    app_name: str = 'TrackoBit Support Assistant'
    api_host: str = '127.0.0.1'
    api_port: int = 8000
    ui_api_base_url: str = 'http://127.0.0.1:8000'
    llm_provider: str = 'mock'
    anthropic_api_key: str | None = None
    anthropic_model: str = 'claude-sonnet-4-5'
    anthropic_vision_model: str = 'claude-sonnet-4-5'
    openai_api_key: str | None = None
    openai_model: str = 'gpt-4o-mini'
    openai_vision_model: str = 'gpt-4o-mini'
    langsmith_tracing: bool = False
    langsmith_api_key: str | None = None
    langsmith_project: str = 'trackobit-support-local'
    data_dir: Path = Path('./data')
    session_dir: Path = Path('./data/sessions')
    upload_dir: Path = Path('./data/uploads')
    knowledge_dir: Path = Path('./data/knowledge_base')
    commands_dir: Path = Path('./data/commands')
    vehicle_api_base_url: str | None = None
    vehicle_api_key: str | None = None
    vehicle_api_url_template: str | None = None
    api_auth_token: str | None = None
    vehicle_api_path: str = '/vehicles/{vehicle_no}/status'
    vehicle_api_timeout_seconds: float = 8.0
    ticket_api_url: str | None = None
    ticket_api_key: str | None = None
    ticket_api_timeout_seconds: float = 10.0
    vehicle_no_regex: str = r'^(?:[A-Z]{2}\d{1,2}[A-Z]{0,4}\d{4}|\d{2}BH\d{4}[A-Z]{1,2})$'
    intent_confidence_threshold: float = 0.65
    query_confidence_threshold: float = 0.60
    rag_confidence_threshold: float = 0.60
    freshness_threshold_minutes: int = 10
    max_input_retries: int = 3
    max_troubleshoot_rounds: int = 2
    max_unreadable_screenshot_retries: int = 2
    paused_frame_ttl_minutes: int = 60
    paused_frame_max_age_hours: int = 72
    app_timezone: str = 'Asia/Kolkata'
    assign_to_support_user: str = 'trackobit-support'
    prompt_versions: str = ''
    pinecone_api_key: str | None = None
    pinecone_index_name: str = 'manual-bugs'

    def ensure_directories(self) -> None:
        for path in (self.data_dir, self.session_dir, self.upload_dir, self.knowledge_dir, self.commands_dir):
            path.mkdir(parents=True, exist_ok=True)

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings
