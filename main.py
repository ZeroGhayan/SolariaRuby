"""Solaria Ruby — bot de trading spot na OKX com decisão via Grok (xAI)."""
import logging
import sys
import time

from configs import load_settings
from services.analysis_service import AnalysisService
from services.exchange_service import ExchangeService
from services.telegram_service import TelegramService
from services.twitter_service import TwitterService
from trader import run_pair

log = logging.getLogger("solaria")


def main():
    s = load_settings()
    logging.basicConfig(level=s.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # evita logar URLs/headers
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    if not s.dry_run and not (s.okx_api_key and s.okx_api_secret and s.okx_api_passphrase):
        log.critical("DRY_RUN=false exige OKX_API_KEY, OKX_API_SECRET e OKX_API_PASSPHRASE.")
        return 1
    if not s.xai_api_key:
        log.critical("XAI_API_KEY ausente.")
        return 1

    exchange = ExchangeService(s.okx_api_key, s.okx_api_secret, s.okx_api_passphrase,
                               sandbox=s.okx_sandbox, dry_run=s.dry_run)
    analysis = AnalysisService(s.xai_api_key, s.xai_model, s.xai_base_url)
    telegram = TelegramService(s.telegram_bot_token, s.telegram_chat_id_main, s.telegram_chat_id_debug)
    twitter = TwitterService(s.twitter_bearer_token, s.twitter_username, s.twitter_hashtag)

    pairs = exchange.validate_pairs(s.trading_pairs)
    if not pairs:
        log.critical("Nenhum par válido em TRADING_PAIRS=%s", ",".join(s.trading_pairs))
        return 1
    log.info("Iniciando. Pares=%s DRY_RUN=%s modelo=%s", pairs, s.dry_run, s.xai_model)

    while True:
        start = time.time()
        tweets = twitter.fetch_and_get_recent()
        for pair in pairs:
            try:
                run_pair(pair, exchange, analysis, telegram, tweets, s.safety_margin)
            except Exception as e:  # noqa: BLE001
                log.exception("Erro no ciclo de %s", pair)
                telegram.send_debug(f"Erro no ciclo de {pair}: {type(e).__name__}: {e}"[:500])
        time.sleep(max(0, s.interval_seconds - (time.time() - start)))


if __name__ == "__main__":
    sys.exit(main())
