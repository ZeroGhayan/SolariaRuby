"""Indicadores técnicos em pandas/numpy (sem TA-Lib) e reamostragem de velas.

Todas as funções recebem/retornam pandas.Series ou DataFrames com colunas
ts (ms, abertura da vela, UTC), open, high, low, close, volume.
"""
import numpy as np
import pandas as pd

MA_LENGTHS = (7, 21, 49, 77, 200, 231, 343, 686, 1372, 2744)
# cores do indicador "Raicher Strategy 2" (resposta ao @rafilsqui); as demais escolhidas por nós
MA_COLORS = {7: "lime", 21: "red", 49: "purple", 77: "orange", 200: "deepskyblue",
             231: "gray", 343: "gold", 686: "saddlebrown", 1372: "navy", 2744: "black"}
COLUMNS = ["ts", "open", "high", "low", "close", "volume"]
MINUTE_MS = 60_000


def sma(series, length):
    """Média móvel simples; NaN enquanto não houver `length` valores."""
    return pd.Series(series, dtype="float64").rolling(length, min_periods=length).mean()


def rma(values, length):
    """Média de Wilder (ta.rma do TradingView): semente = SMA dos primeiros `length` valores."""
    v = np.asarray(values, dtype="float64")
    out = np.full(len(v), np.nan)
    valid = np.flatnonzero(~np.isnan(v))
    if len(valid) < length:
        return out
    start = valid[0] + length - 1
    out[start] = v[valid[0]:start + 1].mean()
    for i in range(start + 1, len(v)):
        out[i] = (out[i - 1] * (length - 1) + v[i]) / length
    return out


def rsi(close, length=14):
    """RSI de Wilder (mesmo do TradingView)."""
    close = pd.Series(close, dtype="float64").reset_index(drop=True)
    delta = close.diff()
    avg_gain = rma(delta.clip(lower=0), length)
    avg_loss = rma(-delta.clip(upper=0), length)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = 100 - 100 / (1 + avg_gain / avg_loss)
    out = np.where(avg_loss == 0, np.where(avg_gain == 0, 50.0, 100.0), out)
    out = np.where(np.isnan(avg_gain), np.nan, out)
    return pd.Series(out, index=close.index)


def stoch_rsi(close, rsi_length=14, stoch_length=14, k=3, d=3):
    """StochRSI do TradingView: retorna (%K, %D) em 0-100."""
    r = rsi(close, rsi_length)
    lo = r.rolling(stoch_length, min_periods=stoch_length).min()
    hi = r.rolling(stoch_length, min_periods=stoch_length).max()
    rng = (hi - lo).replace(0, np.nan)
    stoch = ((r - lo) / rng * 100).fillna(0.0).where(lo.notna())
    k_line = stoch.rolling(k, min_periods=k).mean()
    d_line = k_line.rolling(d, min_periods=d).mean()
    return k_line, d_line


def to_frame(rows):
    df = pd.DataFrame(rows, columns=COLUMNS)
    if df.empty:
        return df
    df = df.drop_duplicates("ts").sort_values("ts").reset_index(drop=True)
    df[COLUMNS[1:]] = df[COLUMNS[1:]].astype("float64")
    df["ts"] = df["ts"].astype("int64")
    return df


def resample(df, minutes, base_minutes=1, now_ms=None, anchor_ms=0):
    """Agrega velas de `base_minutes` em velas de `minutes` ancoradas no epoch Unix (anchor_ms).

    343 = 49*7 e 686 = 98*7 não dividem 1 h/1 dia, por isso partimos de 1m. A âncora no
    epoch deixa os cortes estáveis entre execuções. Só retorna velas completas (todas as
    sub-velas presentes e já fechadas).
    """
    if df is None or df.empty:
        return to_frame([])
    if minutes % base_minutes:
        raise ValueError("minutes precisa ser múltiplo de base_minutes")
    size = minutes * MINUTE_MS
    need = minutes // base_minutes
    d = df.copy()
    d["bucket"] = (d["ts"] - anchor_ms) // size * size + anchor_ms
    g = d.groupby("bucket", sort=True)
    out = pd.DataFrame({
        "ts": g["ts"].first().index.astype("int64"),
        "open": g["open"].first().values,
        "high": g["high"].max().values,
        "low": g["low"].min().values,
        "close": g["close"].last().values,
        "volume": g["volume"].sum().values,
        "n": g["ts"].count().values,
    })
    complete = out["n"] >= need
    if now_ms is not None:
        complete &= (out["ts"] + size) <= now_ms
    return out[complete].drop(columns="n").reset_index(drop=True)


def drop_open_candle(df, tf_ms, now_ms):
    """Remove a vela ainda em formação (abertura + duração > agora)."""
    if df is None or df.empty or tf_ms is None:
        return df
    return df[df["ts"] + tf_ms <= now_ms].reset_index(drop=True)


def last(series):
    """Último valor finito ou None."""
    if series is None or len(series) == 0:
        return None
    v = series.iloc[-1]
    return None if pd.isna(v) else float(v)


def pi_cycle(daily_close):
    """Pi Cycle Top: SMA111 vs 2*SMA350 do diário. Retorna dict ou None se faltar histórico."""
    s111, s350 = last(sma(daily_close, 111)), last(sma(daily_close, 350))
    if s111 is None or s350 is None:
        return None
    return {"sma111": s111, "sma350x2": 2 * s350, "ratio": s111 / (2 * s350)}
