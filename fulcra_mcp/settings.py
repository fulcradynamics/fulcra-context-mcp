from pydantic_settings import BaseSettings
from pathlib import Path

class Settings(BaseSettings):
    state_path: Path = Path("state/").resolve()
    oidc_server_url: str = "http://localhost:4499"
    fulcra_environment: str = "stdio"
    port: int = 4499
    oidc_client_id: str | None = None
    fulcra_oidc_domain: str | None = None
    fulcra_api: str | None = None


settings = Settings()


