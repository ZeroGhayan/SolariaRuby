import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from configs.settings import load_settings
from services.analysis_service import AnalysisService, estimate_cost, parse_command
from services.exchange_service import ExchangeService
from services.telegram_service import TelegramService
from services.twitter_service import TwitterService
from trader import run_pair, size_order


def ai_client(content=None, exc=None, usage=None):
    c = MagicMock()
    if exc:
        c.chat.completions.create.side_effect = exc
    else:
        c.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))], usage=usage)
    return c


def fake_ccxt():
    c = MagicMock()
    c.load_markets.return_value = {"BTC/BRL": {"spot": True, "active": True,
                                               "limits": {"amount": {"min": 1e-5}, "cost": {"min": 10}}}}
    c.fetch_ticker.return_value = {"last": 500000, "high": 510000, "low": 490000, "baseVolume": 1, "percentage": 1.2}
    c.fetch_balance.return_value = {"free": {"BTC": 0.01, "BRL": 1000}}
    c.amount_to_precision.side_effect = lambda p, a: f"{a:.8f}"
    c.fetch_open_orders.return_value = []
    c.create_order.return_value = {"id": "1", "status": "closed"}
    return c


def test_parse_command_valid():
    d = parse_command("C025BTC_", "BTC/BRL")
    assert (d["acao"], d["pct"]) == ("comprar", 25)
    assert parse_command(" `v100btc_` ", "BTC/BRL")["acao"] == "vender"
    assert parse_command("M000USDT", "USDT/BRL")["acao"] == "manter"


def test_parse_command_invalid_is_hold():
    for raw in ["", None, "COMPRAR", "C25BTC_", "C0250BTC", "C101BTC_", "M010BTC_", "C000BTC_",
                "C025ETH_", "X025BTC_", "C025BTC_ extra", '{"acao":"comprar"}']:
        d = parse_command(raw, "BTC/BRL")
        assert d["acao"] == "manter" and d["pct"] == 0, raw


def test_request_is_cheap_and_logs_cost():
    usage = SimpleNamespace(prompt_tokens=200, completion_tokens=4, total_tokens=204,
                            prompt_tokens_details=SimpleNamespace(cached_tokens=100), completion_tokens_details=None)
    cli = ai_client("C010BTC_", usage=usage)
    a = AnalysisService("k", "grok-4.3", client=cli)
    m = {"last": 1.0, "high": 1.0, "low": 1.0, "change_pct": 0.0}
    tweets = [{"text": "x" * 1000}] * 10
    assert a.decide("BTC/BRL", m, 0, 0, tweets)["pct"] == 10
    kw = cli.chat.completions.create.call_args.kwargs
    assert kw["max_tokens"] == 16 and kw["reasoning_effort"] == "none" and kw["model"] == "grok-4.3"
    assert len(kw["messages"][1]["content"]) < 800
    cost = (100 * 1.25 + 100 * 0.20 + 4 * 2.50) / 1e6
    assert abs(a.total_cost - cost) < 1e-12
    assert estimate_cost(None, 1, 1, 1)[0] == 0.0


def test_ai_error_returns_hold():
    a = AnalysisService("k", "m", client=ai_client(exc=RuntimeError("boom")))
    m = {"last": 1, "high": 1, "low": 1, "change_pct": 0}
    assert a.decide("BTC/BRL", m, 0, 0, [])["acao"] == "manter"


def test_size_order_limits():
    d = {"acao": "comprar", "pct": 100}
    side, amt = size_order(d, "BTC/BRL", 500000, 0, 1000, 1e-5, 10, 0.05)
    assert side == "buy" and abs(amt - 950 / 500000) < 1e-12
    assert size_order(d, "BTC/BRL", 500000, 0, 5, 1e-5, 10, 0.05)[0] is None
    v = {"acao": "vender", "pct": 50}
    side, amt = size_order(v, "BTC/BRL", 500000, 0.01, 0, 1e-5, 10, 0.05)
    assert side == "sell" and abs(amt - 0.00475) < 1e-12


def test_dry_run_does_not_place_order_and_notifies():
    cc = fake_ccxt()
    ex = ExchangeService(client=cc, dry_run=True)
    an = AnalysisService("k", "m", client=ai_client("C010BTC_"))
    tg = MagicMock()
    order = run_pair("BTC/BRL", ex, an, tg, [], 0.05)
    assert order["status"] == "simulated"
    cc.create_order.assert_not_called()
    tg.send_message.assert_called_once()
    assert "SIMULAÇÃO" in tg.send_message.call_args[0][0]


def test_live_order_and_hold_not_notified():
    cc = fake_ccxt()
    ex = ExchangeService(client=cc, dry_run=False)
    tg = MagicMock()
    an = AnalysisService("k", "m", client=ai_client("V020BTC_"))
    run_pair("BTC/BRL", ex, an, tg, [], 0.05)
    cc.create_order.assert_called_once_with("BTC/BRL", "market", "sell", 0.0019, 500000.0)
    tg.reset_mock(); cc.create_order.reset_mock()
    an = AnalysisService("k", "m", client=ai_client("M000BTC_"))
    assert run_pair("BTC/BRL", ex, an, tg, [], 0.05) is None
    cc.create_order.assert_not_called(); tg.send_message.assert_not_called()


def test_validate_pairs():
    ex = ExchangeService(client=fake_ccxt())
    assert ex.validate_pairs(["BTC/BRL", "FOO/BRL"]) == ["BTC/BRL"]


def test_settings(tmp_path, monkeypatch):
    for k in ("TRADING_PAIRS", "DRY_RUN"):
        monkeypatch.delenv(k, raising=False)
    f = tmp_path / ".env"
    f.write_text("TRADING_PAIRS=btc/brl, BTC/USDT\n")
    s = load_settings(str(f))
    assert s.trading_pairs == ["BTC/BRL", "BTC/USDT"] and s.dry_run is True
    assert "secret" not in repr(s).lower() or "okx_api_secret" not in repr(s)


def test_telegram_uses_config_token(monkeypatch):
    calls = {}
    def fake_post(url, json, timeout):
        calls["url"] = url
        return MagicMock(json=lambda: {"ok": True}, raise_for_status=lambda: None)
    monkeypatch.setattr("services.telegram_service.requests.post", fake_post)
    TelegramService("TOKEN123", "42").send_message("oi")
    assert calls["url"] == "https://api.telegram.org/botTOKEN123/sendMessage"


def test_twitter_flattens_nested_logs(tmp_path):
    p = tmp_path / "t.json"
    p.write_text(json.dumps([[{"id": "1", "text": "a", "created_at": "2025"}], [], {"id": "2", "text": "b", "created_at": "2026"}]))
    tw = TwitterService("", "u", log_path=str(p))
    assert [t["id"] for t in tw.recent()] == ["2", "1"]
    assert tw.get_user_tweets() == []


def test_schedule(tmp_path, monkeypatch):
    from datetime import datetime
    from main import seconds_until_next
    for k in ("SCHEDULE_TIMES", "INTERVAL_SECONDS", "XAI_MODEL", "XAI_REASONING_EFFORT"):
        monkeypatch.delenv(k, raising=False)
    f = tmp_path / ".env"
    f.write_text("SCHEDULE_TIMES=22:00,01:00\n")
    s = load_settings(str(f))
    assert s.schedule_times == [(1, 0), (22, 0)] and s.interval_seconds == 14400
    assert s.xai_model == "grok-4.3" and s.xai_reasoning_effort == "none"
    assert seconds_until_next(s.schedule_times, datetime(2026, 1, 1, 23, 0)) == 7200
    assert seconds_until_next(s.schedule_times, datetime(2026, 1, 1, 12, 0)) == 36000
