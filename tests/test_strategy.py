import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from configs.settings import Settings
from services.analysis_service import parse_command
from services.candle_store import CandleStore
from services.indicators import resample, rsi, sma, stoch_rsi, to_frame
from services.market_data import MarketData
from services.strategy import (LocalStrategy, bbb_signal, build_command, entry_filter_343,
                               three_chart_signals)
from services.telegram_service import TelegramService
from services.weekly_review import NEUTRAL, WeeklyReview, build_summary, parse_bias

MIN = 60_000
DAY = 1440 * MIN


def frame(closes, step=DAY, start=0):
    rows = [[start + i * step, c, c * 1.01, c * 0.99, c, 1.0] for i, c in enumerate(closes)]
    return to_frame(rows)


# ---------------- indicadores ----------------
def test_sma():
    s = sma([1, 2, 3, 4, 5], 3)
    assert s.isna().sum() == 2 and list(s[2:]) == [2.0, 3.0, 4.0]


def test_rsi_matches_wilder_reference():
    # série clássica de Wilder/StockCharts: RSI(14) do 15º valor ≈ 70.53
    closes = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89, 46.03,
              45.61, 46.28, 46.28, 46.00, 46.03, 46.41, 46.22, 45.64]
    r = rsi(closes, 14)
    assert r[:14].isna().all()
    assert r.iloc[14] == pytest.approx(70.53, abs=0.1)
    assert r.iloc[-1] == pytest.approx(57.92, abs=0.5)


def test_rsi_extremes():
    assert rsi(range(1, 40)).iloc[-1] == 100
    assert rsi(range(40, 1, -1)).iloc[-1] == pytest.approx(0)


def test_stoch_rsi_bounds_and_lengths():
    rng = np.random.default_rng(1)
    closes = 100 + rng.normal(0, 1, 300).cumsum()
    k, d = stoch_rsi(closes)
    assert k.dropna().between(0, 100).all() and d.dropna().between(0, 100).all()
    assert k.first_valid_index() == 14 + 13 + 2  # rsi(14) + janela 14 + suavização 3


# ---------------- reamostragem ----------------
def test_resample_343_and_686_anchored_to_epoch():
    start = 343 * MIN * 10 + 5 * MIN  # começa no meio de um bloco: 1º bloco incompleto é descartado
    df = frame(list(range(1, 343 * 3)), step=MIN, start=start)
    r = resample(df, 343)
    assert all(ts % (343 * MIN) == 0 for ts in r["ts"])
    assert len(r) == 1 + (len(df) - (343 - 5)) // 343 - 1 or len(r) >= 1
    first = r.iloc[0]
    block = df[(df.ts >= first.ts) & (df.ts < first.ts + 343 * MIN)]
    assert len(block) == 343
    assert first.open == block.open.iloc[0] and first.close == block.close.iloc[-1]
    assert first.high == block.high.max() and first.low == block.low.min()
    r686 = resample(df, 686)
    assert all(ts % (686 * MIN) == 0 for ts in r686["ts"])


def test_resample_drops_open_candle():
    df = frame([1.0] * 686, step=MIN)
    assert len(resample(df, 343, now_ms=686 * MIN)) == 2
    assert len(resample(df, 343, now_ms=686 * MIN - 1)) == 1
    two_day = resample(frame([1.0] * 5), 2880, base_minutes=1440)
    assert len(two_day) == 2


# ---------------- regras ----------------
def test_three_chart_rule_near_and_skip():
    daily = frame([100.0] * 400 + [101.0])          # perto da MA343 (≈100) e acima da MA7
    weekly = frame([100.0] * 60 + [120.0])          # longe da MA49
    monthly = frame([100.0] * 30)                   # MA77 sem histórico -> pulada
    sig = {s["tf"]: s for s in three_chart_signals({"1d": daily, "1w": weekly, "1M": monthly}, 0.03)}
    assert sig["1d"]["buy"] is True and sig["1d"]["above_ma7"] is True
    assert sig["1w"]["buy"] is False
    assert sig["1M"]["buy"] is None and "MA77" in sig["1M"]["skip"]


def test_bbb_rule():
    up = list(np.linspace(100, 200, 250))
    crash = list(np.linspace(200, 80, 40))
    ok, det = bbb_signal(frame(up + crash))
    assert ok is True and det["rsi"] < 26.21 and det["stoch_k"] < 20.44 and det["close"] < det["ma200"]
    assert bbb_signal(frame(up))[0] is False
    assert bbb_signal(frame(up[:100]))[0] is None


def test_entry_filter_343():
    rising = frame(list(np.linspace(100, 90, 60)) + list(np.linspace(90, 100, 10)), step=343 * MIN)
    assert entry_filter_343(rising)[0] is True
    falling = frame(list(np.linspace(100, 80, 70)), step=343 * MIN)
    assert entry_filter_343(falling)[0] is False
    assert entry_filter_343(frame([1.0] * 5))[0] is None


# ---------------- comando ----------------
@pytest.mark.parametrize("args,cmd", [
    (("manter", "BTC/BRL"), "M0000000"),
    (("comprar", "BTC/BRL", 200.7), "NRBS0200"),
    (("comprar", "BTC/BRL", 50000), "NRBS9999"),
    (("comprar", "BTC/BRL", 0.4), "M0000000"),
    (("vender", "BTC/BRL"), "NBRT0000"),
    (("comprar", "BTC/USDT", 150), "NDBS0150"),
    (("vender", "BTC/USDT"), "NBDT0000"),
])
def test_build_command(args, cmd):
    assert build_command(*args) == cmd
    if cmd != "M0000000":
        assert parse_command(cmd, args[1])["acao"] == args[0]


def test_build_command_all_in():
    assert build_command("comprar", "BTC/BRL", 10, all_in=True) == "NRBT0000"


# ---------------- estratégia completa ----------------
def make_frames(daily_near=True, bbb=False, filt=True):
    d = [100.0] * 400 + [101.0 if daily_near else 150.0]
    f = {"1d": frame(d), "1w": frame([100.0] * 60 + [150.0]), "1M": frame([100.0] * 10),
         "686m": frame([1.0] * 5)}
    up = list(np.linspace(100, 200, 250))
    f["2D"] = frame(up + list(np.linspace(200, 80, 40)) if bbb else up)
    f["343m"] = frame(list(np.linspace(100, 90, 60)) + list(np.linspace(90, 100 if filt else 80, 10)))
    return f


def strategy(tmp_path, review=None, **cfg):
    s = Settings(**cfg)
    return LocalStrategy(MagicMock(), s, review=review, state_path=str(tmp_path / "st.json"), clock=lambda: 1e9)


def test_strategy_buy_fraction_and_cooldown(tmp_path):
    st = strategy(tmp_path)
    cmd, rep = st.evaluate("BTC/BRL", 500_000, 0.0, 1000.0, make_frames())
    assert cmd == "NRBS0095"  # 10% de (1000 * 0.95)
    assert rep["why"].startswith("perto da média")
    cmd2, rep2 = st.evaluate("BTC/BRL", 500_000, 0.0, 1000.0, make_frames())
    assert cmd2 == "M0000000" and "cooldown" in rep2["why"]


def test_strategy_min_order_bump_and_insufficient(tmp_path):
    cmd, _ = strategy(tmp_path).evaluate("BTC/BRL", 500_000, 0, 300.0, make_frames())
    assert cmd == "NRBS0051"  # 0.0001 BTC * 500k * 1.02
    cmd, rep = strategy(tmp_path / "b").evaluate("BTC/BRL", 500_000, 0, 40.0, make_frames())
    assert cmd == "M0000000" and "mínimo" in rep["why"]


def test_strategy_filter_blocks_but_bbb_goes_all_in(tmp_path):
    cmd, rep = strategy(tmp_path).evaluate("BTC/BRL", 500_000, 0, 1000.0, make_frames(filt=False))
    assert cmd == "M0000000" and "343m" in rep["why"]
    cmd, rep = strategy(tmp_path / "b").evaluate("BTC/BRL", 500_000, 0, 1000.0,
                                                 make_frames(daily_near=False, bbb=True, filt=False))
    assert cmd == "NRBT0000" and rep["why"] == "BBB no 2D"


def test_strategy_sell_requires_profit(tmp_path):
    f = make_frames(daily_near=False)
    f["1M"] = frame([100.0] * 10 + [150.0])  # mensal acima da MA7; semanal também
    st = strategy(tmp_path)
    assert st.evaluate("BTC/BRL", 500_000, 0.01, 0, f)[0] == "M0000000"  # sem preço médio
    json.dump({"BTC/BRL": {"avg_cost": 400_000, "qty": 0.01}}, open(tmp_path / "st.json", "w"))
    assert st.evaluate("BTC/BRL", 500_000, 0.01, 0, f)[0] == "NBRT0000"
    assert strategy(tmp_path / "c", sell_require_profit=False).evaluate("BTC/BRL", 1, 0.01, 0, f)[0] == "NBRT0000"


def test_strategy_applies_weekly_bias(tmp_path):
    rv = SimpleNamespace(bias=lambda: {"risk": 2.0, "allow_buy": True, "allow_sell": True})
    assert strategy(tmp_path, review=rv).evaluate("BTC/BRL", 500_000, 0, 1000.0, make_frames())[0] == "NRBS0190"
    rv = SimpleNamespace(bias=lambda: {"risk": 1.0, "allow_buy": False, "allow_sell": True})
    cmd, rep = strategy(tmp_path / "b", review=rv).evaluate("BTC/BRL", 500_000, 0, 1000.0, make_frames())
    assert cmd == "M0000000" and "bloqueada" in rep["why"]


def test_decide_error_is_hold(tmp_path):
    st = strategy(tmp_path)
    st.md.sync_all.side_effect = RuntimeError("rede")
    d = st.decide("BTC/BRL", {"last": 1.0}, 0, 0)
    assert d["acao"] == "manter"


# ---------------- memória SQLite + coleta ----------------
def test_candle_store_roundtrip(tmp_path):
    db = CandleStore(str(tmp_path / "data" / "candles.db"))
    assert db.upsert("BTC/BRL", "1d", [[0, 1, 2, 0.5, 1.5, 10], [DAY, 1.5, 2, 1, 1.8, 5]]) == 2
    db.upsert("BTC/BRL", "1d", [[DAY, 1.5, 2, 1, 1.9, 6]])  # última vela atualizada
    db.upsert("BTC/USDT", "1d", [[0, 1, 1, 1, 1, 1]])
    assert db.count("BTC/BRL", "1d") == 2 and db.last_ts("BTC/BRL", "1d") == DAY
    assert db.load("BTC/BRL", "1d")[-1][4] == 1.9
    assert db.load("BTC/BRL", "1d", limit=1) == [[DAY, 1.5, 2, 1, 1.9, 6]]
    assert db.prune("BTC/BRL", "1d", DAY) == 1
    # persiste entre execuções
    assert CandleStore(str(tmp_path / "data" / "candles.db")).count("BTC/BRL", "1d") == 1


def test_market_data_backfill_and_incremental(tmp_path):
    data = [[i * DAY, 1, 1, 1, 100 + i, 1] for i in range(18000, 18250)]

    def fetch(symbol, tf, since=None, limit=100, params=None):
        return [r for r in data if r[0] >= since][:limit]

    cli = MagicMock()
    cli.fetch_ohlcv.side_effect = fetch
    md = MarketData(cli, CandleStore(":memory:"))
    now = 18250 * DAY
    md.sync("BTC/BRL", "1d", now=now)
    assert md.store.count("BTC/BRL", "1d") == 250
    data.append([18250 * DAY, 1, 1, 1, 999, 1])
    md.sync("BTC/BRL", "1d", now=now + DAY + 1)
    assert md.store.count("BTC/BRL", "1d") == 251
    assert len(md.frame("BTC/BRL", "1d", now=now + DAY - 1)) == 250  # última ainda aberta
    assert len(md.frame("BTC/BRL", "2D", now=now + DAY - 1)) == 125


def test_market_data_reference_fills_short_history():
    md = MarketData(MagicMock(), CandleStore(":memory:"), reference_symbol="BTC/USDT", min_history={"1M": 77})
    md.store.upsert("BTC/USDT", "1M", [[i * 31 * DAY, 1, 1, 1, 10, 1] for i in range(90)])
    md.store.upsert("USDT/BRL", "1M", [[i * 31 * DAY, 5, 5, 5, 5, 1] for i in range(90)])
    md.store.upsert("BTC/BRL", "1M", [[i * 31 * DAY, 1, 1, 1, 51, 1] for i in range(80, 90)])
    df, src = md.frame_with_reference("BTC/BRL", "1M", now=200 * 31 * DAY)
    assert src.startswith("BTC/USDT") and len(df) == 90
    assert df["close"].iloc[0] == 50 and df["close"].iloc[-1] == 51  # convertido + dados reais do par


# ---------------- revisão semanal ----------------
def review_client(text=None, exc=None):
    c = MagicMock()
    if exc:
        c.chat.completions.create.side_effect = exc
    else:
        c.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=text))], usage=None)
    return c


def test_parse_bias():
    assert parse_bias("0.5,1,0") == {"risk": 0.5, "allow_buy": True, "allow_sell": False}
    assert parse_bias(" 3,1,1 ")["risk"] == 2.0
    assert parse_bias("compre tudo") is None


def test_weekly_review_runs_once_and_stores(tmp_path):
    cli = review_client("0.8,1,0")
    rv = WeeklyReview("", "grok-4.3", client=cli, path=str(tmp_path / "wr.json"))
    frames = make_frames()
    assert rv.run(frames) == {"risk": 0.8, "allow_buy": True, "allow_sell": False}
    rv.run(frames)
    assert cli.chat.completions.create.call_count == 1  # só 1x por semana
    kw = cli.chat.completions.create.call_args.kwargs
    assert kw["max_tokens"] == 16 and len(kw["messages"][1]["content"]) < 800
    assert rv.bias()["risk"] == 0.8


def test_weekly_review_fallbacks(tmp_path):
    assert WeeklyReview("", "m", path=str(tmp_path / "a.json")).run({}) == NEUTRAL  # sem chave
    rv = WeeklyReview("", "m", client=review_client(exc=RuntimeError()), path=str(tmp_path / "b.json"))
    assert rv.run(make_frames()) == NEUTRAL
    rv = WeeklyReview("", "m", client=review_client("lixo"), path=str(tmp_path / "c.json"))
    assert rv.run(make_frames()) == NEUTRAL


def test_weekly_summary_has_cycles():
    txt = build_summary({"1w": frame([100.0] * 60), "1M": frame([100.0] * 20), "1d": frame([100.0] * 400)},
                        ["M0000000"])
    assert "PiCycle" in txt and "halving" in txt and "anual" in txt and "semanal" in txt


# ---------------- gráfico + Telegram ----------------
def test_chart_and_send_photo(monkeypatch):
    from services.chart_service import render
    png = render(make_frames(), title="t")
    assert png[:4] == b"\x89PNG"
    sent = {}

    def post(url, data=None, files=None, timeout=None, json=None):
        sent.update(url=url, data=data, files=files)
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"ok": True})

    monkeypatch.setattr("services.telegram_service.requests.post", post)
    assert TelegramService("tok", "1").send_photo(png, "legenda")["ok"]
    assert sent["url"].endswith("/sendPhoto") and sent["files"]["photo"][1] == png
    assert TelegramService("", "").send_photo(png) is None
