"""Decisão de trading via Grok (xAI) com comando rígido de 8 caracteres.

Formato do comando: A PPP TTTT  (sem espaços), ex.: C025BTC_
  A    = ação: C (comprar), V (vender), M (manter)
  PPP  = percentual do saldo disponível, 000-100 (M exige 000)
  TTTT = ativo base do par, completado com '_' à direita (BTC_, ETH_, USDT)
Qualquer resposta fora desse formato vira "manter".
"""
import logging
import re

from openai import OpenAI

log = logging.getLogger(__name__)

CMD_RE = re.compile(r"^([CVM])(\d{3})([A-Z0-9_]{4})$")
ACTIONS = {"C": "comprar", "V": "vender", "M": "manter"}

SYSTEM = (
    "Você é Solaria Ruby, trader spot focada em acumular BTC com risco baixo. "
    "Responda SOMENTE um comando de 8 caracteres: A+PPP+TTTT. "
    "A=C(comprar)|V(vender)|M(manter); PPP=000-100, % do saldo (comprar: saldo em moeda de cotação; "
    "vender: saldo do ativo); TTTT=ativo com _ à direita. Ex: C025BTC_ V010BTC_ M000BTC_. "
    "Na dúvida, M000."
)


def asset_code(pair):
    base = pair.split("/")[0].upper()
    return base[:4].ljust(4, "_") if len(base) <= 4 else None


def hold(pair, why):
    code = asset_code(pair) or "____"
    return {"acao": "manter", "pct": 0, "cmd": f"M000{code}", "motivo": why}


def parse_command(raw, pair):
    """Valida o comando de 8 caracteres. Qualquer problema => manter."""
    text = (raw or "").strip().strip("`'\"").upper()
    m = CMD_RE.fullmatch(text)
    if not m:
        log.warning("Comando inválido da IA: %r; usando manter.", (raw or "")[:40])
        return hold(pair, "comando inválido")
    letter, pct, code = m.group(1), int(m.group(2)), m.group(3)
    if code != asset_code(pair):
        log.warning("Comando para ativo errado (%s, esperado %s); manter.", code, asset_code(pair))
        return hold(pair, "ativo divergente")
    if pct > 100 or (letter == "M") != (pct == 0):
        log.warning("Percentual inválido no comando %s; manter.", text)
        return hold(pair, "percentual inválido")
    return {"acao": ACTIONS[letter], "pct": pct, "cmd": text, "motivo": "ia"}


def estimate_cost(usage, price_in, price_cached, price_out):
    """Custo em US$ a partir do campo usage (preços por 1M tokens)."""
    if usage is None:
        return 0.0, 0, 0, 0
    prompt = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion = int(getattr(usage, "completion_tokens", 0) or 0)
    details = getattr(usage, "prompt_tokens_details", None)
    cached = int(getattr(details, "cached_tokens", 0) or 0) if details else 0
    cdet = getattr(usage, "completion_tokens_details", None)
    reasoning = int(getattr(cdet, "reasoning_tokens", 0) or 0) if cdet else 0
    # tokens de raciocínio são cobrados como saída; somamos caso não estejam em completion_tokens
    out = completion + (reasoning if reasoning and getattr(usage, "total_tokens", 0) > prompt + completion else 0)
    cost = ((prompt - cached) * price_in + cached * price_cached + out * price_out) / 1_000_000
    return cost, prompt, out, cached


class AnalysisService:
    def __init__(self, api_key, model, base_url="https://api.x.ai/v1", reasoning_effort="none",
                 max_tokens=16, prices=(1.25, 0.20, 2.50), client=None):
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.max_tokens = max_tokens
        self.prices = prices
        self.total_cost = 0.0
        self.client = client or OpenAI(api_key=api_key, base_url=base_url, timeout=60)

    @staticmethod
    def build_prompt(pair, market, base_balance, quote_balance, tweets):
        base, quote = pair.split("/")
        lines = [
            f"{pair} p={market['last']:.2f} h={market['high']:.2f} l={market['low']:.2f} v24h={market['change_pct']:.2f}%",
            f"saldo {base}={base_balance:.8f} {quote}={quote_balance:.2f}",
        ]
        for t in tweets[:3]:
            lines.append("tw: " + " ".join(t.get("text", "").split())[:180])
        lines.append(f"ativo={asset_code(pair)}")
        return "\n".join(lines)

    def decide(self, pair, market, base_balance, quote_balance, tweets):
        if asset_code(pair) is None:
            return hold(pair, "ativo com mais de 4 letras")
        kwargs = {}
        if self.reasoning_effort:
            kwargs["reasoning_effort"] = self.reasoning_effort
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": self.build_prompt(pair, market, base_balance, quote_balance, tweets)},
                ],
                max_tokens=self.max_tokens,
                temperature=0,
                **kwargs,
            )
            raw = resp.choices[0].message.content
        except Exception as e:  # noqa: BLE001 - qualquer falha da API => manter
            log.error("Erro na API da IA: %s", type(e).__name__)
            return hold(pair, "erro na API")
        cost, p, o, c = estimate_cost(getattr(resp, "usage", None), *self.prices)
        self.total_cost += cost
        log.info("Tokens IA %s: entrada=%d (cache=%d) saída=%d custo≈US$%.6f total≈US$%.4f",
                 self.model, p, c, o, cost, self.total_cost)
        return parse_command(raw, pair)
