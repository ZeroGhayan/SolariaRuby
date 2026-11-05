"""Coleta de velas públicas da OKX (ccxt) com memória em SQLite e timeframes customizados.

- 1d, 1w, 1M vêm direto da OKX (UTC).
- 343m e 686m são montados a partir de 1m (343 = 49*7, 686 = 98*7), ancorados no epoch Unix.
- 2D é montado a partir de 1d, também ancorado no epoch.
"""
import logging
import time

import pandas as pd

from services.indicators import MINUTE_MS, drop_open_candle, resample, to_frame

log = logging.getLogger(__name__)

TF_MS = {"1m": MINUTE_MS, "1d": 1440 * MINUTE_MS, "1w": 7 * 1440 * MINUTE_MS, "1M": 31 * 1440 * MINUTE_MS}
DERIVED = {"343m": ("1m", 343), "686m": ("1m", 686), "2D": ("1d", 2880)}
NATIVE = ("1d", "1w", "1M")
HISTORY_START_MS = 1_483_228_800_000  # 2017-01-01: antes disso a OKX não tem BTC/BRL nem BTC/USDT
PAGE = 100  # limite do endpoint de histórico da OKX


def now_ms():
    return int(time.time() * 1000)


class MarketData:
    def __init__(self, client, store, minute_backfill_days=21, minute_retention_days=35,
                 reference_symbol="", reference_rate_symbol="USDT/BRL", min_history=None):
        self.client = client
        self.store = store
        self.minute_backfill_days = minute_backfill_days
        self.minute_retention_days = minute_retention_days
        self.reference_symbol = reference_symbol
        self.reference_rate_symbol = reference_rate_symbol
        # quantas velas fechadas são desejáveis por timeframe antes de recorrer à referência
        self.min_history = min_history or {"1d": 350, "1w": 200, "1M": 77, "2D": 200}

    # ---------- coleta ----------
    def _fetch(self, symbol, tf, since):
        return self.client.fetch_ohlcv(symbol, tf, since=since, limit=PAGE,
                                       params={"method": "publicGetMarketHistoryCandles"})

    def sync(self, symbol, tf, now=None, max_pages=2000):
        """Baixa da OKX tudo desde a última vela salva (ou o backfill inicial) e grava no SQLite."""
        now = now or now_ms()
        step = TF_MS[tf]
        last = self.store.last_ts(symbol, tf)
        if last is not None:
            since = last  # regrava a última (pode ter fechado depois)
        elif tf == "1m":
            since = now - self.minute_backfill_days * 1440 * MINUTE_MS
        else:
            since = HISTORY_START_MS
        added = 0
        for _ in range(max_pages):
            if since >= now:
                break
            rows = self._fetch(symbol, tf, since)
            if not rows:
                since += PAGE * step  # janela vazia (antes do início do mercado): pula
                continue
            added += self.store.upsert(symbol, tf, rows)
            nxt = int(rows[-1][0]) + 1
            if nxt <= since:
                break
            since = nxt
            if int(rows[-1][0]) + step > now:
                break
        if tf == "1m" and self.minute_retention_days:
            self.store.prune(symbol, tf, now - self.minute_retention_days * 1440 * MINUTE_MS)
        if added:
            log.debug("%s %s: %d velas gravadas", symbol, tf, added)
        return added

    def sync_all(self, symbol, now=None):
        for tf in ("1m",) + NATIVE:
            try:
                self.sync(symbol, tf, now)
            except Exception as e:  # noqa: BLE001 - rede/OKX: segue com o que já está salvo
                log.warning("Falha ao baixar %s %s: %s", symbol, tf, type(e).__name__)

    def sync_reference(self, now=None):
        """Velas nativas (1d/1w/1M) do par de referência e da cotação de conversão."""
        for sym in (self.reference_symbol, self.reference_rate_symbol if self.reference_symbol else ""):
            if not sym:
                continue
            for tf in NATIVE:
                try:
                    self.sync(sym, tf, now)
                except Exception as e:  # noqa: BLE001
                    log.warning("Falha ao baixar referência %s %s: %s", sym, tf, type(e).__name__)

    # ---------- leitura ----------
    def frame(self, symbol, tf, now=None):
        """Velas FECHADAS do timeframe (nativo ou derivado) como DataFrame."""
        now = now or now_ms()
        if tf in DERIVED:
            base, minutes = DERIVED[tf]
            since = None
            if base == "1m":
                since = now - self.minute_retention_days * 1440 * MINUTE_MS
            df = to_frame(self.store.load(symbol, base, since_ms=since))
            return resample(df, minutes, base_minutes=1 if base == "1m" else 1440, now_ms=now)
        df = to_frame(self.store.load(symbol, tf))
        if tf == "1M":
            # duração real do mês: a próxima vela começa no 1º dia do mês seguinte
            if df.empty:
                return df
            starts = pd.to_datetime(df["ts"], unit="ms", utc=True) + pd.offsets.MonthBegin(1)
            nxt = starts.map(lambda t: int(t.timestamp() * 1000))
            return df[nxt.values <= now].reset_index(drop=True)
        return drop_open_candle(df, TF_MS[tf], now)

    def frame_with_reference(self, symbol, tf, now=None):
        """Como frame(), mas se o histórico do par for curto e REFERENCE_SYMBOL estiver ligado,
        usa o histórico do par de referência (ex.: BTC/USDT) convertido pela cotação
        USDT/BRL da mesma vela (aproximação), substituído pelos dados reais do par onde houver.
        Retorna (df, origem)."""
        df = self.frame(symbol, tf, now)
        need = self.min_history.get(tf, 0)
        ref = self.reference_symbol
        if not ref or ref == symbol or len(df) >= need or tf not in ("1d", "1w", "1M", "2D"):
            return df, symbol
        ref_df = self.frame(ref, tf, now)
        rate_df = self.frame(self.reference_rate_symbol, tf, now) if self.reference_rate_symbol else None
        if ref_df.empty or rate_df is None or rate_df.empty or len(ref_df) <= len(df):
            return df, symbol
        rate = rate_df.set_index("ts")["close"].reindex(ref_df["ts"]).ffill().bfill().values
        conv = ref_df.copy()
        for c in ("open", "high", "low", "close"):
            conv[c] = conv[c] * rate
        if not df.empty:
            conv = conv[conv["ts"] < df["ts"].iloc[0]]
            conv = pd.concat([conv, df], ignore_index=True)
        return conv.reset_index(drop=True), f"{ref}x{self.reference_rate_symbol}"
