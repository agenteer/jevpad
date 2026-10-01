from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    typesafe_key_present: bool
    typesafe_base_url: str | None
    typesafe_model: str
    pin_provider: str | None
    fault: str | None
    jev_max_retries: int = 5
    jev_retry_budget_s: float = 60.0
    _typesafe_api_key: str | None = field(default=None, repr=False)

    @property
    def route(self) -> str:
        return "B (gateway)" if self.typesafe_base_url else "A (direct TypeSafe)"

    @property
    def base_host(self) -> str:
        if not self.typesafe_base_url:
            return "api.typesafe.ai"
        return urlparse(self.typesafe_base_url).hostname or "unknown"


def load_settings(env_file: Path | None = None) -> Settings:
    load_dotenv(env_file or ROOT / ".env", override=False)
    typesafe_key = os.getenv("TYPESAFE_API_KEY")
    return Settings(
        typesafe_key_present=bool(typesafe_key),
        typesafe_base_url=os.getenv("TYPESAFE_BASE_URL"),
        typesafe_model=os.getenv("TYPESAFE_DEFAULT_MODEL", "jev-latest"),
        pin_provider=os.getenv("JEV_PIN_PROVIDER"),
        fault=os.getenv("JEV_FAULT"),
        jev_max_retries=int(os.getenv("JEV_MAX_RETRIES", "5")),
        jev_retry_budget_s=float(os.getenv("JEV_RETRY_BUDGET_S", "60")),
        _typesafe_api_key=typesafe_key,
    )


def require_live_key(settings: Settings) -> None:
    if not settings.typesafe_key_present:
        raise RuntimeError(
            "Live mode needs TYPESAFE_API_KEY. Copy .env.example to .env, "
            "configure route A or B, then retry; or choose --mode fixture explicitly."
        )
