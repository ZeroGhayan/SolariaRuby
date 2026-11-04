"""Decisão de trading via Grok (xAI) usando o SDK OpenAI 1.x."""
import json
import logging

from openai import OpenAI

log = logging.getLogger(__name__)

HOLD = {"acao": "manter", "quantidade": 0.0, "motivo": "fallback"}
ACTIONS = {"comprar", "vender", "manter"}

SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "decisao_trading",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "acao": {"type": "string", "enum": sorted(ACTIONS)},
                "quantidade": {"type": "number"},
                "motivo": {"type": "string"},
            },
            "required": ["acao", "quantidade", "motivo"],
            "additionalProperties": False,
        },
    },
}


def parse_decision(raw):
    """Valida a resposta do modelo. Qualquer problema => manter."""
    try:
        data = json.loads(raw) if isinstance(raw, str) else dict(raw)
        acao = str(data["acao"]).strip().lower()
        qtd = float(data.get("quantidade") or 0)
        motivo = str(data.get("motivo", ""))[:500]
    except (ValueError, TypeError, KeyError) as e:
        log.warning("Resposta da IA inválida (%s); usando manter.", e)
        return dict(HOLD, motivo="resposta inválida")
    if acao not in ACTIONS or qtd < 0 or qtd != qtd:  # NaN
        log.warning("Decisão fora do formato: %r", data)
        return dict(HOLD, motivo="decisão fora do formato")
    if acao == "manter":
        qtd = 0.0
    return {"acao": acao, "quantidade": qtd, "motivo": motivo}


class AnalysisService:
    def __init__(self, api_key, model, base_url="https://api.x.ai/v1", client=None):
        self.model = model
        self.client = client or OpenAI(api_key=api_key, base_url=base_url, timeout=60)

    @staticmethod
    def build_prompt(pair, market, base_balance, quote_balance, tweets):
        base, quote = pair.split("/")
        tweet_lines = "\n".join(f"- {t.get('text', '')}" for t in tweets[:5]) or "- (nenhum)"
        return (
            f"Par: {pair}\n"
            f"Preço atual: {market['last']} {quote}\n"
            f"Máxima 24h: {market['high']} | Mínima 24h: {market['low']}\n"
            f"Variação 24h: {market['change_pct']}%\n"
            f"Saldo livre: {base_balance} {base} | {quote_balance} {quote}\n\n"
            f"Tweets recentes relevantes:\n{tweet_lines}\n\n"
            f"Responda em JSON com acao (comprar|vender|manter), quantidade em {base} "
            "(quantidade da moeda base, nunca maior que o saldo disponível) e motivo curto."
        )

    def decide(self, pair, market, base_balance, quote_balance, tweets):
        prompt = self.build_prompt(pair, market, base_balance, quote_balance, tweets)
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": (
                        "Você é Solaria Ruby, especialista em trading spot de criptomoedas. "
                        "Objetivo: acumular BTC no longo prazo com risco controlado. "
                        "Na dúvida, escolha manter.")},
                    {"role": "user", "content": prompt},
                ],
                response_format=SCHEMA,
            )
            raw = resp.choices[0].message.content
        except Exception as e:  # noqa: BLE001 - qualquer falha da API => manter
            log.error("Erro na API da IA: %s", type(e).__name__)
            return dict(HOLD, motivo="erro na API")
        return parse_decision(raw)
