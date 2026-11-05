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
    xai_model: str = "grok-4.3"
    xai_reasoning_effort: str = "none"
    xai_max_tokens: int = 16
    xai_price_in: float = 1.25
    xai_price_cached: float = 0.20
    xai_price_out: float = 2.50
    xai_base_url: str = "https://api.x.ai/v1"
    xai_cache_seconds: int = 600
    xai_x_search_max_turns: int = 1
    telegram_bot_token: str = field(default="", repr=False)
    telegram_chat_id_main: str = ""
    telegram_chat_id_debug: str = ""
    twitter_bearer_token: str = field(default="", repr=False)
    x_source: str = "off"
    x_handles: list = field(default_factory=lambda: ["raicher", "DollynhoCoin"])
    x_query_filter: str = ""
    x_max_posts_per_day: int = 20
    trading_pairs: list = field(default_factory=lambda: ["BTC/BRL"])
    dry_run: bool = True
    interval_seconds: int = 14400
    schedule_times: list = field(default_factory=list)
    safety_margin: float = 0.05
    log_level: str = "INFO"
    # estratégia local (Raicher)
    strategy_mode: str = "local"
    candles_db: str = "data/candles.db"
    minute_backfill_days: int = 21
    minute_retention_days: int = 35
    reference_symbol: str = "BTC/USDT"
    reference_rate_symbol: str = "USDT/BRL"
    near_band_pct: float = 3.0
    buy_fraction: float = 0.10
    bbb_fraction: float = 1.0
    buy_cooldown_hours: float = 24
    filter_343_required: bool = False
    rsi_ma_length: int = 14
    sell_enabled: bool = True
    sell_timeframes: list = field(default_factory=lambda: ["1w", "1M"])
    sell_require_profit: bool = True
    sell_min_profit_pct: float = 2.0
    min_order_btc: float = 0.0001
    telegram_charts: bool = True
    chart_every_n_cycles: int = 6
    weekly_review: bool = True
    weekly_review_weekday: int = 6
    weekly_review_hour: int = 21


def _times(value):
    """'01:00,04:00' -> [(1, 0), (4, 0)]; formato inválido gera erro."""
    out = []
    for item in (value or "").split(","):
        item = item.strip()
        if not item:
            continue
        h, m = item.split(":")
        h, m = int(h), int(m)
        if not (0 <= h < 24 and 0 <= m < 60):
            raise ValueError(f"Horário inválido em SCHEDULE_TIMES: {item}")
        out.append((h, m))
    return sorted(set(out))


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
        xai_model=g("XAI_MODEL") or "grok-4.3",
        xai_reasoning_effort=g("XAI_REASONING_EFFORT", "none").strip().lower(),
        xai_max_tokens=int(g("XAI_MAX_TOKENS") or 16),
        xai_price_in=float(g("XAI_PRICE_INPUT_PER_M") or 1.25),
        xai_price_cached=float(g("XAI_PRICE_CACHED_PER_M") or 0.20),
        xai_price_out=float(g("XAI_PRICE_OUTPUT_PER_M") or 2.50),
        xai_base_url=g("XAI_BASE_URL") or "https://api.x.ai/v1",
        xai_cache_seconds=int(g("XAI_CACHE_SECONDS") or 600),
        xai_x_search_max_turns=int(g("XAI_X_SEARCH_MAX_TURNS") or 1),
        telegram_bot_token=g("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id_main=g("TELEGRAM_CHAT_ID_MAIN", ""),
        telegram_chat_id_debug=g("TELEGRAM_CHAT_ID_DEBUG", ""),
        twitter_bearer_token=g("TWITTER_BEARER_TOKEN", ""),
        x_source=(g("X_SOURCE") or "off").strip().lower(),
        x_handles=[h.strip().lstrip("@") for h in (g("X_HANDLES") or "raicher,DollynhoCoin").split(",") if h.strip()],
        x_query_filter=g("X_QUERY_FILTER", ""),
        x_max_posts_per_day=int(g("X_MAX_POSTS_PER_DAY") or 20),
        trading_pairs=pairs,
        dry_run=_bool(g("DRY_RUN"), True),
        interval_seconds=int(g("INTERVAL_SECONDS") or 14400),
        schedule_times=_times(g("SCHEDULE_TIMES")),
        safety_margin=float(g("SAFETY_MARGIN") or 0.05),
        log_level=(g("LOG_LEVEL") or "INFO").upper(),
        strategy_mode=(g("STRATEGY_MODE") or "local").strip().lower(),
        candles_db=g("CANDLES_DB") or "data/candles.db",
        minute_backfill_days=int(g("MINUTE_BACKFILL_DAYS") or 21),
        minute_retention_days=int(g("MINUTE_RETENTION_DAYS") or 35),
        reference_symbol=(g("REFERENCE_SYMBOL", "BTC/USDT") or "").strip().upper(),
        reference_rate_symbol=(g("REFERENCE_RATE_SYMBOL") or "USDT/BRL").strip().upper(),
        near_band_pct=float(g("NEAR_BAND_PCT") or 3.0),
        buy_fraction=float(g("BUY_FRACTION") or 0.10),
        bbb_fraction=float(g("BBB_FRACTION") or 1.0),
        buy_cooldown_hours=float(g("BUY_COOLDOWN_HOURS") or 24),
        filter_343_required=_bool(g("FILTER_343_REQUIRED"), False),
        rsi_ma_length=int(g("RSI_MA_LENGTH") or 14),
        sell_enabled=_bool(g("SELL_ENABLED"), True),
        sell_timeframes=[t.strip() for t in (g("SELL_TIMEFRAMES") or "1w,1M").split(",") if t.strip()],
        sell_require_profit=_bool(g("SELL_REQUIRE_PROFIT"), True),
        sell_min_profit_pct=float(g("SELL_MIN_PROFIT_PCT") or 2.0),
        min_order_btc=float(g("MIN_ORDER_BTC") or 0.0001),
        telegram_charts=_bool(g("TELEGRAM_CHARTS"), True),
        chart_every_n_cycles=int(g("CHART_EVERY_N_CYCLES") or 6),
        weekly_review=_bool(g("WEEKLY_REVIEW"), True),
        weekly_review_weekday=int(g("WEEKLY_REVIEW_WEEKDAY") or 6),
        weekly_review_hour=int(g("WEEKLY_REVIEW_HOUR") or 21),
    )
