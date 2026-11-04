"""Acesso à OKX via ccxt (spot)."""
import logging

import ccxt

log = logging.getLogger(__name__)


class ExchangeService:
    def __init__(self, api_key="", secret="", passphrase="", sandbox=False, dry_run=True, client=None):
        self.dry_run = dry_run
        self.client = client or ccxt.okx({
            "apiKey": api_key,
            "secret": secret,
            "password": passphrase,
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        })
        if sandbox and client is None:
            self.client.set_sandbox_mode(True)
        self._markets = None

    def markets(self):
        if self._markets is None:
            self._markets = self.client.load_markets()
        return self._markets

    def validate_pairs(self, pairs):
        """Retorna apenas os pares spot existentes na OKX."""
        m = self.markets()
        valid = []
        for p in pairs:
            if p in m and m[p].get("spot", True) and m[p].get("active", True) is not False:
                valid.append(p)
            else:
                log.error("Par %s não existe (ou está inativo) no spot da OKX; ignorado.", p)
        return valid

    def get_ticker(self, pair):
        t = self.client.fetch_ticker(pair)
        return {
            "last": float(t.get("last") or 0),
            "high": float(t.get("high") or 0),
            "low": float(t.get("low") or 0),
            "volume": float(t.get("baseVolume") or 0),
            "change_pct": float(t.get("percentage") or 0),
        }

    def get_free_balance(self, pair):
        base, quote = pair.split("/")
        bal = self.client.fetch_balance()
        free = bal.get("free", {}) or {}
        return float(free.get(base) or 0), float(free.get(quote) or 0)

    def limits(self, pair):
        lim = self.markets()[pair].get("limits", {}) or {}
        return (
            float((lim.get("amount") or {}).get("min") or 0),
            float((lim.get("cost") or {}).get("min") or 0),
        )

    def round_amount(self, pair, amount):
        return float(self.client.amount_to_precision(pair, amount))

    def cancel_open_orders(self, pair):
        if self.dry_run:
            return []
        orders = self.client.fetch_open_orders(pair)
        for o in orders:
            self.client.cancel_order(o["id"], pair)
        return orders

    def market_order(self, pair, side, amount, price):
        """Ordem a mercado; amount sempre na moeda base. Em DRY_RUN apenas simula."""
        if self.dry_run:
            log.info("[DRY_RUN] %s %.8f %s @ ~%.2f", side, amount, pair, price)
            return {"id": "dry-run", "status": "simulated", "side": side, "amount": amount, "price": price}
        # na OKX, compra a mercado é por custo (quote); ccxt usa amount*price
        return self.client.create_order(pair, "market", side, amount, price)
