"""Configuração centralizada lida do .env (python-dotenv)."""
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv


def _bool(value, default=False):
    if value is None or value == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "sim", "on")


@dataclass
class Settings:
    okx_api_key: str = ""
    okx_api_secret: str = field(default="", repr=False)
    okx_api_passphrase: str = field(default="", repr=False)
    okx_sandbox: bool = False
    xai_api_key: str = field(default="", repr=False)
    xai_model: str = "grok-4-1-fast-reasoning"
    xai_base_url: str = "https://api.x.ai/v1"
    telegram_bot_token: str = field(default="", repr=False)
    telegram_chat_id_main: str = ""
    telegram_chat_id_debug: str = ""
    twitter_bearer_token: str = field(default="", repr=False)
    twitter_username: str = "allanraicher"
    twitter_hashtag: str = "#nostreidamos"
    trading_pairs: list = field(default_factory=lambda: ["BTC/BRL"])
    dry_run: bool = True
    interval_seconds: int = 600
    safety_margin: float = 0.05
    log_level: str = "INFO"


def load_settings(env_file=None) -> Settings:
    load_dotenv(env_file)
    g = os.getenv
    pairs = [p.strip().upper() for p in (g("TRADING_PAIRS") or "BTC/BRL").split(",") if p.strip()]
    return Settings(
        okx_api_key=g("OKX_API_KEY", ""),
        okx_api_secret=g("OKX_API_SECRET", ""),
        okx_api_passphrase=g("OKX_API_PASSPHRASE", ""),
        okx_sandbox=_bool(g("OKX_SANDBOX"), False),
        xai_api_key=g("XAI_API_KEY", ""),
        xai_model=g("XAI_MODEL") or "grok-4-1-fast-reasoning",
        xai_base_url=g("XAI_BASE_URL") or "https://api.x.ai/v1",
        telegram_bot_token=g("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id_main=g("TELEGRAM_CHAT_ID_MAIN", ""),
        telegram_chat_id_debug=g("TELEGRAM_CHAT_ID_DEBUG", ""),
        twitter_bearer_token=g("TWITTER_BEARER_TOKEN", ""),
        twitter_username=g("TWITTER_USERNAME") or "allanraicher",
        twitter_hashtag=(g("TWITTER_HASHTAG") or "#nostreidamos").lower(),
        trading_pairs=pairs,
        dry_run=_bool(g("DRY_RUN"), True),
        interval_seconds=int(g("INTERVAL_SECONDS") or 600),
        safety_margin=float(g("SAFETY_MARGIN") or 0.05),
        log_level=(g("LOG_LEVEL") or "INFO").upper(),
    )
