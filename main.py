"""Solaria Ruby — bot de trading spot na OKX com estratégia local (Raicher) e revisão semanal do Grok."""
import logging
import sys
import time
from datetime import datetime, timedelta

from configs import load_settings
from services.analysis_service import AnalysisService
from services.candle_store import CandleStore
from services.market_data import MarketData
from services.strategy import LocalStrategy, summary_lines
from services.weekly_review import WeeklyReview
from services.exchange_service import ExchangeService
from services.telegram_service import TelegramService
from services.twitter_service import TwitterService
from trader import run_pair

log = logging.getLogger("solaria")


def seconds_until_next(times, now=None):
    """Segundos até o próximo horário fixo (lista de (hora, minuto), horário local)."""
    now = now or datetime.now()
    for day in (0, 1):
        for h, m in times:
            t = (now + timedelta(days=day)).replace(hour=h, minute=m, second=0, microsecond=0)
            if t > now:
                return (t - now).total_seconds()
    return 86400.0


def after_local_cycle(s, strategy, review, telegram, pair, cycle, order, first=True):
    """Pós-ciclo da estratégia local: log, revisão semanal (1x/semana) e gráfico no Telegram."""
    rep = strategy.last_report.get(pair)
    frames = getattr(strategy, "last_frames", None)
    if not rep or frames is None:
        return
    lines = summary_lines(rep)
    log.info("Sinais: %s", " | ".join(lines))
    if review is not None:
        review.record(rep["cmd"])
        if first:
            review.run(frames)
    if s.telegram_charts and telegram.enabled and (order or cycle % max(1, s.chart_every_n_cycles) == 0):
        from services.chart_service import render  # matplotlib só é carregado se usado
        png = render(frames, title=f"Solaria Ruby {pair}")
        telegram.send_photo(png, "\n".join(lines))


def main():
    s = load_settings()
    logging.basicConfig(level=s.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # evita logar URLs/headers
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    if not s.dry_run and not (s.okx_api_key and s.okx_api_secret and s.okx_api_passphrase):
        log.critical("DRY_RUN=false exige OKX_API_KEY, OKX_API_SECRET e OKX_API_PASSPHRASE.")
        return 1
    if s.x_source not in ("x_api", "xai", "off"):
        log.critical("X_SOURCE deve ser x_api, xai ou off (atual: %s).", s.x_source)
        return 1
    if s.strategy_mode not in ("local", "grok"):
        log.critical("STRATEGY_MODE deve ser local ou grok (atual: %s).", s.strategy_mode)
        return 1
    if s.strategy_mode == "grok" and not s.xai_api_key:
        log.critical("STRATEGY_MODE=grok exige XAI_API_KEY.")
        return 1

    exchange = ExchangeService(s.okx_api_key, s.okx_api_secret, s.okx_api_passphrase,
                               sandbox=s.okx_sandbox, dry_run=s.dry_run)
    review = None
    if s.strategy_mode == "local":
        md = MarketData(exchange.client, CandleStore(s.candles_db), s.minute_backfill_days,
                        s.minute_retention_days, s.reference_symbol, s.reference_rate_symbol)
        review = WeeklyReview(s.xai_api_key, s.xai_model, s.xai_base_url, s.xai_reasoning_effort,
                              enabled=s.weekly_review, weekday=s.weekly_review_weekday,
                              hour=s.weekly_review_hour, max_tokens=s.xai_max_tokens,
                              prices=(s.xai_price_in, s.xai_price_cached, s.xai_price_out))
        if s.weekly_review and not review.enabled:
            log.info("Revisão semanal desligada (sem XAI_API_KEY): viés neutro.")
        analysis = LocalStrategy(md, s, review=review)
    else:
        analysis = AnalysisService(s.xai_api_key, s.xai_model, s.xai_base_url,
                                   reasoning_effort=s.xai_reasoning_effort, max_tokens=s.xai_max_tokens,
                                   prices=(s.xai_price_in, s.xai_price_cached, s.xai_price_out),
                                   cache_seconds=s.xai_cache_seconds, x_search=(s.x_source == "xai"),
                                   x_handles=s.x_handles, x_search_max_turns=s.xai_x_search_max_turns)
    telegram = TelegramService(s.telegram_bot_token, s.telegram_chat_id_main, s.telegram_chat_id_debug)
    twitter = TwitterService(s.twitter_bearer_token if s.x_source == "x_api" else "", s.x_handles,
                             s.x_query_filter, s.x_max_posts_per_day)

    pairs = exchange.validate_pairs(s.trading_pairs)
    if not pairs:
        log.critical("Nenhum par válido em TRADING_PAIRS=%s", ",".join(s.trading_pairs))
        return 1
    agenda = (",".join(f"{h:02d}:{m:02d}" for h, m in s.schedule_times)
              if s.schedule_times else f"a cada {s.interval_seconds}s")
    log.info("Iniciando. Pares=%s DRY_RUN=%s estratégia=%s modelo=%s agenda=%s fonte X=%s",
             pairs, s.dry_run, s.strategy_mode, s.xai_model, agenda, s.x_source)
    if s.schedule_times:
        time.sleep(seconds_until_next(s.schedule_times))

    cycle = 0
    while True:
        start = time.time()
        tweets = twitter.fetch_and_get_recent() if s.x_source != "off" else []
        for i, pair in enumerate(pairs):
            try:
                if s.strategy_mode == "local" and i == 0 and s.reference_symbol:
                    analysis.md.sync_reference()
                order = run_pair(pair, exchange, analysis, telegram, tweets, s.safety_margin)
                if s.strategy_mode == "local":
                    after_local_cycle(s, analysis, review, telegram, pair, cycle, order, first=(i == 0))
            except Exception as e:  # noqa: BLE001
                log.exception("Erro no ciclo de %s", pair)
                telegram.send_debug(f"Erro no ciclo de {pair}: {type(e).__name__}: {e}"[:500])
        cycle += 1
        if s.schedule_times:
            time.sleep(seconds_until_next(s.schedule_times) + 1)
        else:
            time.sleep(max(0, s.interval_seconds - (time.time() - start)))


if __name__ == "__main__":
    sys.exit(main())
