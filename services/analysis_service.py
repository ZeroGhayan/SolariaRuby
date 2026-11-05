"""Decisão de trading via Grok (xAI) com o comando original de 8 caracteres do Solaria Ruby.

Formato (do analysis_service.py original do Pedro):
  [Op][Entrada][Saída][Tipo][Valor 4 dígitos]
  Op      N = negociar, M = manter (M??????? = manter, o resto é ignorado)
  Entrada moeda que sai (vendida); Saída = moeda que entra (comprada)
          -> exatamente uma das duas é a moeda de cotação do par (R=BRL padrão; D=USDT em pares /USDT)
  Tipo    S = valor específico, T = total da carteira (all-in; valor 0000)
  Valor   S + compra: valor inteiro na moeda de cotação (BRL/USDT)
          S + venda : satoshis (1 BTC = 100000000 sats; mesma escala 1e-8 para outros ativos)
Ex.: NRBS0200 (200 BRL -> BTC), NBRT0000 (todo BTC -> BRL), NRBT0000 (todo BRL -> BTC), M0000000.
Qualquer resposta inválida vira "manter".
"""
import hashlib
import json
import logging
import os
import re
import time

from openai import OpenAI

log = logging.getLogger(__name__)

ASSET_MAP = {
    "R": "BRL",
    "B": "BTC",
    "E": "ETH",
    "D": "USDT",
    "S": "SOL",
    "X": "XRP",
    "A": "ADA",
    "G": "DOGE",
}
CODE_OF = {v: k for k, v in ASSET_MAP.items()}
SATS = 100_000_000
HOLD_CMD = "M0000000"

SYSTEM = (
    "Você é Solaria Ruby, trader de Bitcoin. Objetivo: acumular BTC no longo prazo, "
    "evitar vender em baixa e proteger capital em {quote} quando necessário. "
    "Responda SÓ 8 caracteres, sem mais nada: [N|M][Entrada][Saída][S|T][4 dígitos]. "
    "N=negociar M=manter. Entrada=moeda vendida, Saída=moeda comprada; uma delas tem que ser {q}. "
    "Códigos: {codes}. S=valor específico, T=tudo (0000). "
    "Valor S: compra=inteiro em {quote}; venda=satoshis. "
    "Ex: N{q}{b}S0200 N{b}{q}T0000 M0000000. Na dúvida, M0000000."
)


def hold(cmd, why):
    return {"acao": "manter", "tipo": None, "valor": 0.0, "cmd": cmd, "motivo": why}


def parse_command(raw, pair):
    """Interpreta o comando com o mesmo match-case do original, limitado ao par em operação."""
    response = (raw or "").strip().upper()
    log.debug("Resposta bruta da IA: %r (len=%d)", (raw or "")[:40], len(response))
    if len(response) != 8:
        log.warning("Comprimento inválido: %r. Manter.", response[:40])
        return hold(response[:8], "comprimento inválido")

    base, quote = pair.upper().split("/")
    base_code, quote_code = CODE_OF.get(base), CODE_OF.get(quote)

    match (response[0], response[1], response[2], response[3], response[4:8]):
        case ("M", _, _, _, _):
            return hold(response, "manter")

        case ("N", from_code, to_code, tipo, valor_str) if (
            from_code in ASSET_MAP
            and to_code in ASSET_MAP
            and from_code != to_code
            and quote_code is not None
            and (from_code == quote_code) != (to_code == quote_code)  # exatamente um é a cotação
            and tipo in ("S", "T")
            and re.fullmatch(r"\d{4}", valor_str)
        ):
            valor = int(valor_str)
            if from_code == quote_code:
                acao, asset_code = "comprar", to_code
            else:
                acao, asset_code = "vender", from_code
            if asset_code != base_code:
                log.warning("Comando %s é para %s, mas o par é %s. Manter.", response, ASSET_MAP[asset_code], pair)
                return hold(response, "ativo diferente do par")
            if tipo == "T":
                if valor != 0:
                    log.warning("Tipo T exige 0000: %s. Manter.", response)
                    return hold(response, "T sem 0000")
                quantia = None  # all-in
            else:
                if valor == 0:
                    return hold(response, "valor zero")
                quantia = float(valor) if acao == "comprar" else valor / SATS
            return {"acao": acao, "tipo": tipo, "valor": quantia, "cmd": response, "motivo": "ia"}

        case _:
            log.warning("Formato inválido: %r. Manter.", response)
            return hold(response, "formato inválido")


def estimate_cost(usage, price_in, price_cached, price_out):
    """Custo em US$ a partir do usage (chat.completions ou responses). Preços por 1M tokens."""
    if usage is None:
        return 0.0, 0, 0, 0
    prompt = int(getattr(usage, "prompt_tokens", None) or getattr(usage, "input_tokens", 0) or 0)
    completion = int(getattr(usage, "completion_tokens", None) or getattr(usage, "output_tokens", 0) or 0)
    details = getattr(usage, "prompt_tokens_details", None) or getattr(usage, "input_tokens_details", None)
    cached = int(getattr(details, "cached_tokens", 0) or 0) if details else 0
    cost = ((prompt - cached) * price_in + cached * price_cached + completion * price_out) / 1_000_000
    return cost, prompt, completion, cached


def x_search_cost(usage, price_post=5.0, price_user=10.0):
    """Custo do X Search (US$ por 1k posts/perfis) a partir de usage.server_side_tool_usage_details."""
    d = getattr(usage, "server_side_tool_usage_details", None) if usage is not None else None
    if d is None:
        return 0.0, 0, 0
    get = (lambda k: d.get(k, 0)) if isinstance(d, dict) else (lambda k: getattr(d, k, 0))
    posts, users = int(get("x_posts_fetched") or 0), int(get("x_users_fetched") or 0)
    return (posts * price_post + users * price_user) / 1000, posts, users


class AnalysisService:
    def __init__(self, api_key, model, base_url="https://api.x.ai/v1", reasoning_effort="none",
                 max_tokens=16, prices=(1.25, 0.20, 2.50), cache_seconds=600,
                 cache_path=os.path.join("data", "cache", "api_cache.json"),
                 x_search=False, x_handles=(), x_search_max_turns=1, client=None):
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.max_tokens = max_tokens
        self.prices = prices
        self.cache_seconds = cache_seconds
        self.cache_path = cache_path
        self.x_search = x_search
        self.x_handles = [h.lstrip("@") for h in x_handles if h]
        self.x_search_max_turns = x_search_max_turns
        self.total_cost = 0.0
        self.client = client or OpenAI(api_key=api_key, base_url=base_url, timeout=90)

    # --- cache (ideia do código original: mesma pergunta em < 10 min reaproveita a resposta) ---
    def _cache_get(self, key):
        if self.cache_seconds <= 0 or not os.path.exists(self.cache_path):
            return None
        try:
            with open(self.cache_path, encoding="utf-8") as f:
                entry = json.load(f).get(key)
            if entry and time.time() - entry["timestamp"] < self.cache_seconds:
                return entry["response"]
        except (OSError, ValueError, KeyError, TypeError):
            pass
        return None

    def _cache_put(self, key, response):
        if self.cache_seconds <= 0:
            return
        now = time.time()
        cache = {}
        try:
            with open(self.cache_path, encoding="utf-8") as f:
                cache = json.load(f)
        except (OSError, ValueError):
            pass
        cache = {k: v for k, v in cache.items()
                 if isinstance(v, dict) and now - v.get("timestamp", 0) < self.cache_seconds}
        cache[key] = {"response": response, "timestamp": now}
        try:
            os.makedirs(os.path.dirname(self.cache_path) or ".", exist_ok=True)
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(cache, f)
        except OSError:
            pass

    # --- prompt ---
    @staticmethod
    def system_prompt(pair):
        base, quote = pair.upper().split("/")
        codes = " ".join(f"{k}={v}" for k, v in ASSET_MAP.items())
        return SYSTEM.format(quote=quote, q=CODE_OF.get(quote, "R"), b=CODE_OF.get(base, "B"), codes=codes)

    def build_prompt(self, pair, market, base_balance, quote_balance, tweets):
        base, quote = pair.upper().split("/")
        lines = [
            f"{pair} preço={market['last']:.2f} máx24h={market['high']:.2f} mín24h={market['low']:.2f} var24h={market['change_pct']:.2f}%",
            f"saldo {quote}={quote_balance:.2f} {base}={base_balance:.8f} ({int(base_balance * SATS)} sats)",
        ]
        for t in tweets[:3]:
            lines.append("post: " + " ".join(t.get("text", "").split())[:180])
        if self.x_search and self.x_handles:
            lines.append("Busque posts recentes de " + ", ".join("@" + h for h in self.x_handles)
                         + " no X e use como sinal de alta/baixa.")
        return "\n".join(lines)

    # --- chamadas ---
    def _call_chat(self, system, user):
        kwargs = {"reasoning_effort": self.reasoning_effort} if self.reasoning_effort else {}
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_tokens=self.max_tokens, temperature=0, **kwargs,
        )
        return resp.choices[0].message.content, getattr(resp, "usage", None)

    def _call_responses_x_search(self, system, user):
        """X Search só existe na Responses API (não em chat.completions)."""
        tool = {"type": "x_search"}
        if self.x_handles:
            tool["allowed_x_handles"] = self.x_handles[:20]
        kwargs = {"reasoning": {"effort": self.reasoning_effort}} if self.reasoning_effort else {}
        resp = self.client.responses.create(
            model=self.model,
            instructions=system,
            input=user,
            tools=[tool],
            temperature=0,
            extra_body={"max_turns": self.x_search_max_turns},
            **kwargs,
        )
        return getattr(resp, "output_text", ""), getattr(resp, "usage", None)

    def decide(self, pair, market, base_balance, quote_balance, tweets):
        system = self.system_prompt(pair)
        user = self.build_prompt(pair, market, base_balance, quote_balance, tweets)
        key = hashlib.sha256((self.model + system + user).encode()).hexdigest()

        raw = self._cache_get(key)
        if raw is not None:
            log.info("Resposta da IA obtida do cache (%s).", raw)
            return parse_command(raw, pair)
        try:
            if self.x_search:
                raw, usage = self._call_responses_x_search(system, user)
            else:
                raw, usage = self._call_chat(system, user)
        except Exception as e:  # noqa: BLE001 - qualquer falha da API => manter
            log.error("Erro na API da IA: %s", type(e).__name__)
            return parse_command(HOLD_CMD, pair) | {"motivo": "erro na API"}

        cost, p, o, c = estimate_cost(usage, *self.prices)
        xcost, posts, users = x_search_cost(usage)
        self.total_cost += cost + xcost
        log.info("Tokens IA %s: entrada=%d (cache=%d) saída=%d custo≈US$%.6f%s total≈US$%.4f",
                 self.model, p, c, o, cost,
                 f" + X Search {posts} posts/{users} perfis≈US${xcost:.4f}" if self.x_search else "",
                 self.total_cost)
        raw = (raw or "").strip()
        self._cache_put(key, raw)
        return parse_command(raw, pair)
