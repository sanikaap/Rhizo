from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    falkordb_host: str = "localhost"
    falkordb_port: int = 6379
    falkordb_password: str = ""
    query_timeout_ms: int = 5000
    connect_timeout_s: float = 2.0

    api_port: int = 8000
    auth_secret: str = Field(default="", repr=False)
    cors_origins: str = "http://localhost:5173"

    anthropic_api_key: str = ""
    llm_model: str = "claude-opus-5-5"
    llm_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    llm_max_tokens: int = 16000
    agent_max_rounds: int = 6
    agent_mode: Literal["llm", "scripted"] = "scripted"
    agent_fallback: Literal["scripted", "none"] = "scripted"
    mcp_enable_writes: bool = False
    agent_token_delay_ms: int = 12

    registry_path: Path = _REPO_ROOT / "backend" / ".data" / "registry.db"
    demo_repo_path: Path = _REPO_ROOT / "data" / "demo"
    github_token: str = Field(default="", repr=False)
    github_max_issue_pages: int = 3
    git_max_commits: int = 3000
    git_timeout_s: int = 300
    max_repo_size_mb: int = 500
    sync_workers: int = 2
    sync_lock_ttl_s: int = 1800
    pseudonymise_authors: bool = True

    edge_expiry_days: int = 90
    cochange_min_support: int = 3
    cochange_min_jaccard: float = 0.25
    cochange_max_files_per_commit: int = 30
    cochange_max_services_per_commit: int = 4

    @field_validator("auth_secret")
    @classmethod
    def _strong_secret(cls, v: str) -> str:
        if v and len(v) < 32:
            raise ValueError("AUTH_SECRET must be at least 32 characters")
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
