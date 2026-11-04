"""Lógica de um ciclo de trading (testável, sem efeitos colaterais além dos serviços)."""
import logging

log = logging.getLogger(__name__)


def size_order(decision, pair, price, base_free, quote_free, min_amount, min_cost, safety_margin):
    """Valida a decisão contra saldo e mínimos. Retorna (side, amount) ou (None, motivo)."""
    acao, qtd = decision["acao"], float(decision["quantidade"])
    if acao == "manter":
        return None, "manter"
    if price <= 0 or qtd <= 0:
        return None, "preço ou quantidade inválidos"
    if acao == "comprar":
        max_qtd = quote_free * (1 - safety_margin) / price
        side = "buy"
    else:
        max_qtd = base_free * (1 - safety_margin)
        side = "sell"
    amount = min(qtd, max_qtd)
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
    log.info("Decisão IA %s: %s %.8f (%s)", pair, decision["acao"], decision["quantidade"], decision["motivo"])

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
        f"- Motivo: {decision['motivo']}"
    )
    return order
