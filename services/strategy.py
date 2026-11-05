"""Estratégia local (sem IA por ciclo) baseada nos ensinamentos de Allan Raicher (@raicher).

Regras (médias móveis simples do fechamento, velas FECHADAS):
1. "3 gráficos" (x.com/raicher/status/1936947812811620862):
   diário  compra perto da MA343, venda acima da MA7
   semanal compra perto da MA49,  venda acima da MA7
   mensal  compra perto da MA77,  venda acima da MA7
   "perto" = fechamento <= MA * (1 + NEAR_BAND_PCT/100) (abaixo da média também conta: é ainda mais barato).
2. BBB no 2D (x.com/raicher/status/1990938405883289764): fechamento < MA200 E RSI14 < 26.21
   E StochRSI %K (14,14,3,3) < 20.44 => compra mais forte ("all in" do Raicher).
3. Filtro de entrada no 343m (x.com/raicher/status/1991918872958824757): fechamento acima da MA7
   e RSI acima da sua média. (Suporte inferior do RSI por linha de tendência fica para o futuro.)
Médias sem histórico suficiente são ignoradas (regra pulada e registrada no log).

A saída é o mesmo comando de 8 caracteres do Solaria Ruby, interpretado por parse_command,
então trader.py executa exatamente como antes.
"""
import json
import logging
import math
import os
import time

from services.analysis_service import CODE_OF, HOLD_CMD, SATS, parse_command
from services.indicators import last, rsi, sma, stoch_rsi

log = logging.getLogger(__name__)

THREE_CHARTS = (("1d", 343), ("1w", 49), ("1M", 77))
BBB_RSI = 26.21
BBB_STOCH = 20.44
MAX_S_VALUE = 9999


# ---------------- regras puras (testáveis) ----------------
def three_chart_signals(frames, near_band=0.03):
    """frames: {tf: DataFrame}. Retorna lista de dicts por gráfico."""
    out = []
    for tf, length in THREE_CHARTS:
        df = frames.get(tf)
        sig = {"tf": tf, "ma": length, "close": None, "ma_value": None, "ma7": None,
               "buy": None, "above_ma7": None, "dist_pct": None}
        if df is None or df.empty:
            sig["skip"] = "sem velas"
            out.append(sig)
            continue
        close = df["close"]
        c = float(close.iloc[-1])
        ma, ma7 = last(sma(close, length)), last(sma(close, 7))
        sig.update(close=c, ma_value=ma, ma7=ma7)
        if ma is None:
            sig["skip"] = f"MA{length} precisa de {length} velas (há {len(df)})"
        else:
            sig["buy"] = c <= ma * (1 + near_band)
            sig["dist_pct"] = (c / ma - 1) * 100
        if ma7 is not None:
            sig["above_ma7"] = c > ma7
        out.append(sig)
    return out


def bbb_signal(df2d):
    """Retorna (True/False/None, detalhes). None = histórico insuficiente."""
    if df2d is None or len(df2d) < 200:
        return None, {"skip": f"BBB precisa de 200 velas 2D (há {0 if df2d is None else len(df2d)})"}
    close = df2d["close"]
    c, ma200, r = float(close.iloc[-1]), last(sma(close, 200)), last(rsi(close, 14))
    k, _ = stoch_rsi(close, 14, 14, 3, 3)
    k = last(k)
    if None in (ma200, r, k):
        return None, {"skip": "indicadores 2D incompletos"}
    det = {"close": c, "ma200": ma200, "rsi": r, "stoch_k": k}
    return (c < ma200 and r < BBB_RSI and k < BBB_STOCH), det


def entry_filter_343(df343, rsi_ma_len=14):
    """Fechamento > MA7 e RSI > média do RSI. Retorna (True/False/None, detalhes)."""
    if df343 is None or df343.empty:
        return None, {"skip": "sem velas 343m"}
    close = df343["close"]
    r = rsi(close, 14)
    c, ma7, rv, rma = float(close.iloc[-1]), last(sma(close, 7)), last(r), last(sma(r, rsi_ma_len))
    if None in (ma7, rv, rma):
        return None, {"skip": f"343m com histórico curto ({len(df343)} velas)"}
    det = {"close": c, "ma7": ma7, "rsi": rv, "rsi_ma": rma}
    return (c > ma7 and rv > rma), det


def build_command(action, pair, quote_amount=None, all_in=False):
    """Gera o comando de 8 caracteres: comprar|vender|manter."""
    base, quote = pair.upper().split("/")
    b, q = CODE_OF.get(base), CODE_OF.get(quote)
    if action == "manter" or b is None or q is None:
        return HOLD_CMD
    if action == "vender":
        # venda S é em satoshis com 4 dígitos (máx. 9999 sats < mínimo de 0,0001 BTC da OKX),
        # por isso a venda é sempre total (T).
        return f"N{b}{q}T0000"
    if all_in:
        return f"N{q}{b}T0000"
    v = int(min(MAX_S_VALUE, max(0, math.floor(quote_amount or 0))))
    return f"N{q}{b}S{v:04d}" if v > 0 else HOLD_CMD


class LocalStrategy:
    """Mesma interface do AnalysisService (decide), mas 100% local."""

    def __init__(self, market_data, cfg, review=None, state_path=os.path.join("data", "strategy_state.json"),
                 clock=time.time):
        self.md = market_data
        self.cfg = cfg  # Settings
        self.review = review  # WeeklyReview (opcional) -> bias()
        self.state_path = state_path
        self.clock = clock
        self.last_report = {}

    # --- estado (cooldown e preço médio das compras decididas) ---
    def _state(self):
        try:
            with open(self.state_path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def _save(self, st):
        os.makedirs(os.path.dirname(self.state_path) or ".", exist_ok=True)
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(st, f, indent=1)

    def frames(self, pair, now_ms):
        f = {}
        for tf in ("1d", "1w", "1M", "2D"):
            f[tf], src = self.md.frame_with_reference(pair, tf, now_ms)
            if src != pair:
                log.info("%s %s: histórico curto, usando referência %s (%d velas)", pair, tf, src, len(f[tf]))
        for tf in ("343m", "686m"):
            f[tf] = self.md.frame(pair, tf, now_ms)
        return f

    def evaluate(self, pair, price, base_bal, quote_bal, frames, now_s=None):
        """Combina as regras e devolve (comando, relatório)."""
        c = self.cfg
        now_s = now_s or self.clock()
        bias = self.review.bias() if self.review else {"risk": 1.0, "allow_buy": True, "allow_sell": True}
        st = self._state().get(pair, {})
        charts = three_chart_signals(frames, c.near_band_pct / 100)
        bbb, bbb_d = bbb_signal(frames.get("2D"))
        f343, f343_d = entry_filter_343(frames.get("343m"), c.rsi_ma_length)
        rep = {"pair": pair, "price": price, "charts": charts, "bbb": bbb, "bbb_detail": bbb_d,
               "filter343": f343, "filter343_detail": f343_d, "bias": bias, "why": ""}
        for s in charts:
            if s.get("skip"):
                log.info("%s regra %s/MA%d pulada: %s", pair, s["tf"], s["ma"], s["skip"])
        if bbb is None:
            log.info("%s BBB pulado: %s", pair, bbb_d.get("skip"))
        if f343 is None:
            log.info("%s filtro 343m indisponível: %s", pair, f343_d.get("skip"))

        cooldown_ok = now_s - st.get("last_buy", 0) >= c.buy_cooldown_hours * 3600
        filter_ok = f343 is True or (f343 is None and not c.filter_343_required)
        buys = [s["tf"] for s in charts if s["buy"]]
        cmd, why = HOLD_CMD, "sem sinal"

        # ---- venda: fechamento acima da MA7 em todos os SELL_TIMEFRAMES (com histórico) ----
        sell_tfs = [s for s in charts if s["tf"] in c.sell_timeframes and s["above_ma7"] is not None]
        sell = (c.sell_enabled and base_bal > 0 and sell_tfs and all(s["above_ma7"] for s in sell_tfs)
                and not buys and not bbb)
        if sell and c.sell_require_profit:
            avg = st.get("avg_cost")
            sell = bool(avg) and price >= avg * (1 + c.sell_min_profit_pct / 100)
        if sell and not bias["allow_sell"]:
            why = "venda bloqueada pela revisão semanal"
        elif sell:
            cmd, why = build_command("vender", pair), "fechamento acima da MA7 em " + ",".join(s["tf"] for s in sell_tfs)

        # ---- compra ----
        elif (bbb or (buys and filter_ok)) and not bias["allow_buy"]:
            why = "compra bloqueada pela revisão semanal"
        elif (bbb or (buys and filter_ok)) and not cooldown_ok:
            why = f"compra em cooldown ({c.buy_cooldown_hours}h)"
        elif bbb or (buys and filter_ok):
            usable = quote_bal * (1 - c.safety_margin)
            if bbb:
                frac, why = c.bbb_fraction, "BBB no 2D"
            else:
                frac, why = min(1.0, c.buy_fraction * len(buys)), "perto da média em " + ",".join(buys)
            frac = min(1.0, frac * bias["risk"])
            amount = usable * frac
            min_cost = c.min_order_btc * price * 1.02
            if amount < min_cost <= usable:
                amount = min_cost  # sobe para o mínimo da OKX (0,0001 BTC) se houver saldo
            if amount < min_cost or amount <= 0:
                cmd, why = HOLD_CMD, why + " (saldo abaixo do mínimo)"
            else:
                all_in = frac >= 0.999 or amount > MAX_S_VALUE and amount >= usable * 0.999
                cmd = build_command("comprar", pair, amount, all_in=all_in)
                if cmd != HOLD_CMD:
                    spent = usable if all_in else float(cmd[4:])
                    qty_old = st.get("qty", 0.0)
                    qty_new = spent / price
                    st["avg_cost"] = ((st.get("avg_cost") or 0) * qty_old + spent) / (qty_old + qty_new)
                    st["qty"] = qty_old + qty_new
                    st["last_buy"] = now_s
        elif buys and not filter_ok:
            why = "perto da média em " + ",".join(buys) + ", mas filtro 343m não confirmou"

        if cmd.startswith("N") and cmd[1] == CODE_OF.get(pair.split("/")[0]):  # venda zera o preço médio
            st.update(avg_cost=None, qty=0.0)
        all_st = self._state()
        all_st[pair] = st
        self._save(all_st)
        rep.update(cmd=cmd, why=why)
        self.last_report[pair] = rep
        return cmd, rep

    def decide(self, pair, market, base_balance, quote_balance, tweets=None):
        now = int(self.clock() * 1000)
        try:
            self.md.sync_all(pair, now)
            frames = self.frames(pair, now)
            cmd, rep = self.evaluate(pair, market["last"], base_balance, quote_balance, frames, now / 1000)
        except Exception as e:  # noqa: BLE001 - qualquer falha => manter
            log.exception("Erro na estratégia local de %s", pair)
            return parse_command(HOLD_CMD, pair) | {"motivo": f"erro: {type(e).__name__}"}
        self.last_frames = frames
        d = parse_command(cmd, pair)
        d["motivo"] = rep["why"]
        return d


def summary_lines(rep):
    """Texto curto (legenda do gráfico / log) com os sinais e a decisão."""
    lines = [f"{rep['pair']} {rep['price']:,.2f} → {rep['cmd']} ({rep['why']})"]
    for s in rep["charts"]:
        if s["ma_value"] is None:
            lines.append(f"{s['tf']}: MA{s['ma']} indisponível")
        else:
            lines.append(f"{s['tf']}: {s['dist_pct']:+.1f}% vs MA{s['ma']}{' ✅' if s['buy'] else ''}"
                         f"{' | >MA7' if s['above_ma7'] else ''}")
    b = rep["bbb_detail"]
    lines.append("BBB 2D: " + ("indisponível" if rep["bbb"] is None else
                              f"{'SIM' if rep['bbb'] else 'não'} (RSI {b['rsi']:.1f}, StochK {b['stoch_k']:.1f})"))
    f = rep["filter343_detail"]
    lines.append("343m: " + ("indisponível" if rep["filter343"] is None else
                            f"{'ok' if rep['filter343'] else 'não'} (RSI {f['rsi']:.1f} vs média {f['rsi_ma']:.1f})"))
    bi = rep["bias"]
    lines.append(f"Revisão semanal: risco {bi['risk']:.2f} compra={'sim' if bi['allow_buy'] else 'não'} "
                 f"venda={'sim' if bi['allow_sell'] else 'não'}")
    return lines
