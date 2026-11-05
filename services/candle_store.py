"""Memória local de velas em SQLite (data/candles.db), por símbolo + timeframe.

Cada ciclo acrescenta as velas novas; assim médias longas (MA77 mensal, MA343 diária...)
ficam calculáveis quando o histórico acumulado for suficiente.
"""
import os
import sqlite3

SCHEMA = """CREATE TABLE IF NOT EXISTS candles (
    symbol TEXT NOT NULL, timeframe TEXT NOT NULL, ts INTEGER NOT NULL,
    open REAL, high REAL, low REAL, close REAL, volume REAL,
    PRIMARY KEY (symbol, timeframe, ts))"""


class CandleStore:
    def __init__(self, path=os.path.join("data", "candles.db")):
        if path != ":memory:":
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.execute("PRAGMA journal_mode=WAL" if path != ":memory:" else "PRAGMA foreign_keys=ON")
        self.conn.execute(SCHEMA)
        self.conn.commit()

    def upsert(self, symbol, timeframe, rows):
        """rows: [[ts, o, h, l, c, v], ...] (formato ccxt). Vela repetida é sobrescrita (a última pode ter mudado)."""
        rows = [(symbol, timeframe, int(r[0]), *map(float, r[1:6])) for r in rows if r and r[4] is not None]
        if rows:
            self.conn.executemany("INSERT OR REPLACE INTO candles VALUES (?,?,?,?,?,?,?,?)", rows)
            self.conn.commit()
        return len(rows)

    def load(self, symbol, timeframe, since_ms=None, limit=None):
        q = "SELECT ts, open, high, low, close, volume FROM candles WHERE symbol=? AND timeframe=?"
        args = [symbol, timeframe]
        if since_ms is not None:
            q += " AND ts >= ?"
            args.append(int(since_ms))
        if limit:
            q = f"SELECT * FROM ({q} ORDER BY ts DESC LIMIT ?) ORDER BY ts"
            args.append(int(limit))
        else:
            q += " ORDER BY ts"
        return [list(r) for r in self.conn.execute(q, args)]

    def last_ts(self, symbol, timeframe):
        r = self.conn.execute("SELECT MAX(ts) FROM candles WHERE symbol=? AND timeframe=?",
                              (symbol, timeframe)).fetchone()
        return r[0]

    def first_ts(self, symbol, timeframe):
        r = self.conn.execute("SELECT MIN(ts) FROM candles WHERE symbol=? AND timeframe=?",
                              (symbol, timeframe)).fetchone()
        return r[0]

    def count(self, symbol, timeframe):
        return self.conn.execute("SELECT COUNT(*) FROM candles WHERE symbol=? AND timeframe=?",
                                 (symbol, timeframe)).fetchone()[0]

    def prune(self, symbol, timeframe, older_than_ms):
        cur = self.conn.execute("DELETE FROM candles WHERE symbol=? AND timeframe=? AND ts < ?",
                                (symbol, timeframe, int(older_than_ms)))
        self.conn.commit()
        return cur.rowcount
