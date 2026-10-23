from pydantic_settings import BaseSettings
from pathlib import Path
from typing import Literal


class Settings(BaseSettings):
    state_path: Path = Path("state/").resolve()
    # The GCS bucket mounted at state_path, if it is one. Records that must be
    # changed atomically across instances go through the GCS API instead of the
    # mount, which can't do that.
    state_bucket: str | None = None
    oidc_server_url: str = "http://localhost:4499"
    fulcra_environment: str = "stdio"
    fulcra_contacts_debug: bool = False
    port: int = 4499
    oidc_client_id: str | None = None
    fulcra_oidc_domain: str | None = None
    fulcra_api: str | None = None
    log_format: Literal["console", "json"] = "console"
    # Process-wide bound on every outbound HTTP request (the fulcra-api client
    # uses urllib, which honors socket.setdefaulttimeout).
    http_timeout_seconds: float = 30.0


settings = Settings()
