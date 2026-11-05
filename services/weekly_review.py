"""Revisão semanal pelo Grok (malha fechada): 1 chamada por semana, resumo numérico compacto.

O Grok devolve 3 números "risco,compra,venda" (ex.: "0.8,1,0"), gravados em
data/weekly_review.json e aplicados à estratégia local até a próxima revisão.
Sem XAI_API_KEY ou se a chamada falhar, vale o viés neutro (1.0, compra e venda liberadas).
"""
import json
import logging
import os
import re
import time
from datetime import datetime, timezone

from services.analysis_service import estimate_cost
from services.indicators import last, pi_cycle, rsi, sma

log = logging.getLogger(__name__)

NEUTRAL = {"risk": 1.0, "allow_buy": True, "allow_sell": True}
HALVINGS = ["2012-11-28", "2016-07-09", "2020-05-11", "2024-04-20"]
NEXT_HALVING_EST = "2028-04-15"  # estimativa

SYSTEM = ("Você revisa semanalmente um bot que acumula BTC (regras locais de Allan Raicher: médias 7/49/77/343, "
          "BBB no 2D). Com base nos ciclos semanal, mensal, anual e de 4 anos, responda SÓ: risco,compra,venda "
          "onde risco é 0.0-2.0 (multiplica o tamanho das compras), compra e venda são 1 (liberada) ou 0 (bloqueada). "
          "Ex.: 1.0,1,1. Na dúvida, 1.0,1,1.")


def parse_bias(text):
    m = re.fullmatch(r"\s*([0-9]*\.?[0-9]+)\s*,\s*([01])\s*,\s*([01])\s*", text or "")
    if not m:
        return None
    return {"risk": max(0.0, min(2.0, float(m.group(1)))), "allow_buy": m.group(2) == "1",
            "allow_sell": m.group(3) == "1"}


def _tf_line(name, df, lengths):
    if df is None or df.empty:
        return f"{name}: sem dados"
    close = df["close"]
    c = float(close.iloc[-1])
    parts = [f"{name} fech={c:.0f}"]
    for n in lengths:
        v = last(sma(close, n))
        if v is not None:
            parts.append(f"MA{n}={(c / v - 1) * 100:+.1f}%")
    r = last(rsi(close, 14))
    if r is not None:
        parts.append(f"RSI={r:.0f}")
    return " ".join(parts)


def halving_position(now=None):
    now = now or datetime.now(timezone.utc)
    last_h = datetime.fromisoformat(HALVINGS[-1]).replace(tzinfo=timezone.utc)
    nxt = datetime.fromisoformat(NEXT_HALVING_EST).replace(tzinfo=timezone.utc)
    days = (now - last_h).days
    return days, days / (nxt - last_h).days


def build_summary(frames, decisions, now=None):
    lines = [
        _tf_line("semanal", frames.get("1w"), (7, 21, 49, 200)),
        _tf_line("mensal", frames.get("1M"), (7, 21, 49, 77)),
    ]
    m = frames.get("1M")
    if m is not None and len(m) >= 13:
        c = m["close"]
        lines.append(f"anual: var12m={(c.iloc[-1] / c.iloc[-13] - 1) * 100:+.0f}%"
                     f" máx12m={(c.iloc[-1] / c.iloc[-12:].max() - 1) * 100:+.0f}%")
    d = frames.get("1d")
    pc = pi_cycle(d["close"]) if d is not None and not d.empty else None
    lines.append(f"PiCycle 111DMA/(2x350DMA)={pc['ratio']:.2f} (>=1 topo)" if pc else "PiCycle: histórico curto")
    days, frac = halving_position(now)
    lines.append(f"halving: {days} dias desde 2024-04-20 ({frac * 100:.0f}% do ciclo de 4 anos)")
    if decisions:
        lines.append("decisões 7d: " + " ".join(decisions[-12:]))
    return "\n".join(lines)


class WeeklyReview:
    def __init__(self, api_key, model, base_url="https://api.x.ai/v1", reasoning_effort="none",
                 enabled=True, weekday=6, hour=21, max_tokens=16, prices=(1.25, 0.20, 2.50),
                 path=os.path.join("data", "weekly_review.json"), client=None, clock=time.time):
        self.enabled = enabled and bool(api_key or client)
        self.model, self.reasoning_effort, self.max_tokens, self.prices = model, reasoning_effort, max_tokens, prices
        self.weekday, self.hour = weekday, hour
        self.path = path
        self.clock = clock
        self.client = client
        if self.enabled and client is None:
            from openai import OpenAI
            self.client = OpenAI(api_key=api_key, base_url=base_url, timeout=90)
        self.decisions = []

    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def bias(self):
        b = self._load().get("bias")
        return {**NEUTRAL, **b} if isinstance(b, dict) else dict(NEUTRAL)

    def record(self, cmd):
        self.decisions = (self.decisions + [cmd])[-42:]  # 7 dias de ciclos de 4 h

    def due(self):
        """True se já passou o horário semanal (dia/hora local) e não houve revisão desde então."""
        now = datetime.fromtimestamp(self.clock())
        days_back = (now.weekday() - self.weekday) % 7
        slot = (now.replace(hour=self.hour, minute=0, second=0, microsecond=0)
                .timestamp() - days_back * 86400)
        if slot > now.timestamp():
            slot -= 7 * 86400
        return self._load().get("ts", 0) < slot

    def run(self, frames):
        """Chama o Grok (se habilitado e no horário). Retorna o viés vigente."""
        if not self.enabled or not self.due():
            return self.bias()
        user = build_summary(frames, self.decisions)
        try:
            kw = {"reasoning_effort": self.reasoning_effort} if self.reasoning_effort else {}
            resp = self.client.chat.completions.create(
                model=self.model, max_tokens=self.max_tokens, temperature=0,
                messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}], **kw)
            text = resp.choices[0].message.content
            cost = estimate_cost(getattr(resp, "usage", None), *self.prices)[0]
        except Exception as e:  # noqa: BLE001
            log.error("Revisão semanal falhou (%s); mantendo viés neutro.", type(e).__name__)
            bias = dict(NEUTRAL)
            self._save(bias, "erro", user)
            return bias
        bias = parse_bias(text)
        if bias is None:
            log.warning("Resposta inválida da revisão semanal: %r; viés neutro.", (text or "")[:40])
            bias = dict(NEUTRAL)
        log.info("Revisão semanal: %s -> %s (custo≈US$%.6f)", (text or "").strip()[:20], bias, cost)
        self._save(bias, (text or "").strip()[:40], user)
        return bias

    def _save(self, bias, raw, summary):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"ts": self.clock(), "bias": bias, "raw": raw, "summary": summary}, f, indent=1)
