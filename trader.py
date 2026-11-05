"""Lógica de um ciclo de trading (testável, sem efeitos colaterais além dos serviços)."""
import logging

log = logging.getLogger(__name__)


def size_order(decision, pair, price, base_free, quote_free, min_amount, min_cost, safety_margin):
    """Converte a decisão (S = valor específico, T = tudo) em quantidade do ativo base.

    Nunca usa mais que (1 - safety_margin) do saldo livre e respeita os mínimos da OKX.
    Retorna (side, amount) ou (None, motivo).
    """
    acao = decision["acao"]
    if acao == "manter":
        return None, "manter"
    if price <= 0:
        return None, "preço inválido"
    usable = 1 - safety_margin
    valor = decision.get("valor")
    if acao == "comprar":
        spend = quote_free * usable
        if decision.get("tipo") == "S":
            spend = min(spend, float(valor))
        amount, side = spend / price, "buy"
    else:
        amount = base_free * usable
        if decision.get("tipo") == "S":
            amount = min(amount, float(valor))
        side = "sell"
    if amount <= 0:
        return None, "saldo insuficiente"
    if amount < min_amount:
        return None, f"abaixo do mínimo de quantidade ({min_amount})"
    if min_cost and amount * price < min_cost:
        return None, f"abaixo do valor mínimo da ordem ({min_cost})"
    return side, amount


def run_pair(pair, exchange, analysis, telegram, tweets, safety_margin):
    base, quote = pair.split("/")
    market = exchange.get_ticker(pair)
    base_free, quote_free = exchange.get_free_balance(pair)
    log.info("%s preço=%.2f saldo=%.8f %s / %.2f %s", pair, market["last"], base_free, base, quote_free, quote)

    exchange.cancel_open_orders(pair)
    decision = analysis.decide(pair, market, base_free, quote_free, tweets)
    log.info("Decisão IA %s: %s -> %s (%s)", pair, decision["cmd"], decision["acao"], decision["motivo"])

    min_amount, min_cost = exchange.limits(pair)
    side, amount = size_order(decision, pair, market["last"], base_free, quote_free,
                              min_amount, min_cost, safety_margin)
    if side is None:
        log.info("Nenhuma ordem para %s: %s", pair, amount)
        return None
    amount = exchange.round_amount(pair, amount)
    if amount < min_amount or amount <= 0:
        log.info("Quantidade arredondada abaixo do mínimo para %s", pair)
        return None

    order = exchange.market_order(pair, side, amount, market["last"])
    if not order:
        return None
    prefix = "🧪 [SIMULAÇÃO] " if order.get("status") == "simulated" else ""
    telegram.send_message(
        f"{prefix}💼 Ordem executada {pair}\n"
        f"- Tipo: {decision['acao']}\n"
        f"- Quantidade: {amount:.8f} {base}\n"
        f"- Preço ref.: {market['last']:.2f} {quote}\n"
        f"- Comando: {decision['cmd']}"
    )
    return order
