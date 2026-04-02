"""Configuration loaded from environment variables."""
import os
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Config:
    """Immutable application configuration."""

    telegram_token: str
    proxy_url: Optional[str] = None

    @classmethod
    def from_env(cls) -> "Config":
        """Build Config from environment variables.

        Raises:
            ValueError: If TELEGRAM_BOT_TOKEN is not set.
        """
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not token:
            raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")

        return cls(
            telegram_token=token,
            proxy_url=os.getenv("PROXY_URL") or None,
        )
