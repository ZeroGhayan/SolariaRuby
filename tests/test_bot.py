import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from configs.settings import load_settings
import pytest
from services.analysis_service import AnalysisService, estimate_cost, parse_command, x_search_cost
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


# Casos portados do bloco __main__ do analysis_service.py original do Pedro
@pytest.mark.parametrize("cmd,acao,tipo,valor", [
    ("M0000000", "manter", None, 0.0),
    ("NRBS0200", "comprar", "S", 200.0),
    ("NBRT0000", "vender", "T", None),
    ("NRBT0000", "comprar", "T", None),
    ("NRBS9999", "comprar", "S", 9999.0),
    ("NBRS0050", "vender", "S", 50 / 100_000_000),
    ("INVALIDAR", "manter", None, 0.0),   # comprimento errado
    ("NXRS0000", "manter", None, 0.0),    # XRP não é o par BTC/BRL (e valor 0)
    ("M1234567", "manter", None, 0.0),    # M com lixo => manter
    ("NBRST000", "manter", None, 0.0),    # valor não numérico
])
def test_original_cases(cmd, acao, tipo, valor):
    d = parse_command(cmd, "BTC/BRL")
    assert (d["acao"], d["tipo"], d["valor"]) == (acao, tipo, valor)


@pytest.mark.parametrize("cmd", ["", None, "NRRS0100", "NBDS0100", "NDBS0100", "NBBS0100",
                                 "NRBX0100", "NRBT0100", "NRBS0000", "ZRBS0100", "NRES0100",
                                 "NRBS0200 ok", "nrbs02000"])
def test_invalid_is_hold(cmd):
    assert parse_command(cmd, "BTC/BRL")["acao"] == "manter"


def test_usdt_quote_generalized():
    assert parse_command("NDBS0150", "BTC/USDT")["acao"] == "comprar"
    assert parse_command("NBDT0000", "BTC/USDT")["acao"] == "vender"
    assert parse_command("NRBS0150", "BTC/USDT")["acao"] == "manter"  # R não é a cotação do par
    assert parse_command("  nrbs0200 \n", "BTC/BRL")["valor"] == 200.0


def test_request_is_cheap_and_logs_cost(tmp_path):
    usage = SimpleNamespace(prompt_tokens=200, completion_tokens=4, total_tokens=204,
                            prompt_tokens_details=SimpleNamespace(cached_tokens=100))
    cli = ai_client("NRBS0100", usage=usage)
    a = AnalysisService("k", "grok-4.3", client=cli, cache_path=str(tmp_path / "c.json"))
    m = {"last": 1.0, "high": 1.0, "low": 1.0, "change_pct": 0.0}
    tweets = [{"text": "x " * 1000}] * 10
    assert a.decide("BTC/BRL", m, 0, 0, tweets)["valor"] == 100.0
    kw = cli.chat.completions.create.call_args.kwargs
    assert kw["max_tokens"] == 16 and kw["reasoning_effort"] == "none" and kw["temperature"] == 0
    assert "Solaria Ruby" in kw["messages"][0]["content"]
    assert len(kw["messages"][0]["content"]) + len(kw["messages"][1]["content"]) < 1400
    assert abs(a.total_cost - (100 * 1.25 + 100 * 0.20 + 4 * 2.50) / 1e6) < 1e-12
    cli.responses.create.assert_not_called()  # X Search desligado por padrão
    # cache: mesma pergunta não chama a API de novo
    assert a.decide("BTC/BRL", m, 0, 0, tweets)["acao"] == "comprar"
    assert cli.chat.completions.create.call_count == 1
    assert estimate_cost(None, 1, 1, 1)[0] == 0.0


def test_x_search_optional_uses_responses_api(tmp_path):
    cli = MagicMock()
    cli.responses.create.return_value = SimpleNamespace(
        output_text="NBRS0050",
        usage=SimpleNamespace(input_tokens=3000, output_tokens=10, input_tokens_details=None,
                              server_side_tool_usage_details={"x_posts_fetched": 20, "x_users_fetched": 0}))
    a = AnalysisService("k", "grok-4.3", client=cli, cache_seconds=0, x_search=True,
                        x_handles=["@raicher", "DollynhoCoin"])
    m = {"last": 1.0, "high": 1.0, "low": 1.0, "change_pct": 0.0}
    assert a.decide("BTC/BRL", m, 1, 0, [])["acao"] == "vender"
    kw = cli.responses.create.call_args.kwargs
    assert kw["tools"] == [{"type": "x_search", "allowed_x_handles": ["raicher", "DollynhoCoin"]}]
    assert kw["reasoning"] == {"effort": "none"}
    assert x_search_cost(cli.responses.create.return_value.usage)[0] == 0.1
    assert abs(a.total_cost - (0.1 + (3000 * 1.25 + 10 * 2.5) / 1e6)) < 1e-12


def test_ai_error_returns_hold():
    a = AnalysisService("k", "m", client=ai_client(exc=RuntimeError("boom")))
    m = {"last": 1, "high": 1, "low": 1, "change_pct": 0}
    assert a.decide("BTC/BRL", m, 0, 0, [])["acao"] == "manter"


def test_size_order_limits():
    t = {"acao": "comprar", "tipo": "T", "valor": None}
    side, amt = size_order(t, "BTC/BRL", 500000, 0, 1000, 1e-5, 10, 0.05)
    assert side == "buy" and abs(amt - 950 / 500000) < 1e-12           # all-in respeita margem de 5%
    s_ = {"acao": "comprar", "tipo": "S", "valor": 200.0}
    assert abs(size_order(s_, "BTC/BRL", 500000, 0, 1000, 1e-5, 10, 0.05)[1] - 200 / 500000) < 1e-12
    s_big = {"acao": "comprar", "tipo": "S", "valor": 9999.0}
    assert abs(size_order(s_big, "BTC/BRL", 500000, 0, 1000, 1e-5, 10, 0.05)[1] - 950 / 500000) < 1e-12
    assert size_order(t, "BTC/BRL", 500000, 0, 5, 1e-5, 10, 0.05)[0] is None  # abaixo do mínimo
    v = {"acao": "vender", "tipo": "S", "valor": 0.005}
    side, amt = size_order(v, "BTC/BRL", 500000, 0.01, 0, 1e-5, 10, 0.05)
    assert side == "sell" and abs(amt - 0.005) < 1e-12
    vt = {"acao": "vender", "tipo": "T", "valor": None}
    assert abs(size_order(vt, "BTC/BRL", 500000, 0.01, 0, 1e-5, 10, 0.05)[1] - 0.0095) < 1e-12
    small = {"acao": "vender", "tipo": "S", "valor": 50 / 1e8}           # 50 sats < mínimo OKX
    assert size_order(small, "BTC/BRL", 500000, 0.01, 0, 1e-4, 10, 0.05)[0] is None


def test_dry_run_does_not_place_order_and_notifies():
    cc = fake_ccxt()
    ex = ExchangeService(client=cc, dry_run=True)
    an = AnalysisService("k", "m", client=ai_client("NRBS0100"))
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
    an = AnalysisService("k", "m", client=ai_client("NBRS9999"))
    run_pair("BTC/BRL", ex, an, tg, [], 0.05)
    cc.create_order.assert_called_once_with("BTC/BRL", "market", "sell", 9.999e-05, 500000.0)
    tg.reset_mock(); cc.create_order.reset_mock()
    an = AnalysisService("k", "m", client=ai_client("M0000000"), cache_seconds=0)
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
