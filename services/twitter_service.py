"""Posts recentes do X via API v2 oficial (pay-per-use), com limite diário de gasto.

Busca numa única requisição (/2/tweets/search/recent):
    (from:raicher OR from:DollynhoCoin) -is:retweet -is:reply [filtro opcional]
usando since_id, então só posts NOVOS são retornados (e cobrados: US$ 0,005 por post lido).
"""
import json
import logging
import os
import time
from datetime import datetime, timezone

import requests

log = logging.getLogger(__name__)
SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"
PRICE_PER_POST = 0.005  # US$ (docs.x.com, pay-per-use)


class TwitterService:
    def __init__(self, bearer_token, handles=("raicher", "DollynhoCoin"), query_filter="",
                 max_posts_per_day=20, log_path=os.path.join("logs", "twitter_logs.json"),
                 state_path=os.path.join("data", "x_state.json"), keep=200):
        self.enabled = bool(bearer_token)
        self.headers = {"Authorization": f"Bearer {bearer_token}"}
        self.handles = [h.strip().lstrip("@") for h in handles if h and h.strip()]
        self.query_filter = (query_filter or "").strip()
        self.max_posts_per_day = int(max_posts_per_day)
        self.log_path = log_path
        self.state_path = state_path
        self.keep = keep
        self._last_fetch = 0.0
        if not self.enabled:
            log.info("API do X desativada (TWITTER_BEARER_TOKEN ausente); usando só o histórico local.")

    # --- estado (since_id e posts lidos no dia UTC) ---
    def _state(self):
        try:
            with open(self.state_path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def _save_json(self, path, data):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)

    def build_query(self):
        q = "(" + " OR ".join(f"from:{h}" for h in self.handles) + ") -is:retweet -is:reply"
        return f"{q} {self.query_filter}" if self.query_filter else q

    # --- histórico local ---
    def load_logs(self):
        """Lê o histórico e achata listas aninhadas (formato antigo)."""
        if not os.path.exists(self.log_path):
            return []
        try:
            with open(self.log_path, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            log.warning("Histórico de posts ilegível; ignorando.")
            return []
        flat, stack = [], list(data) if isinstance(data, list) else []
        while stack:
            item = stack.pop(0)
            if isinstance(item, list):
                stack[0:0] = item
            elif isinstance(item, dict) and "text" in item:
                flat.append(item)
        return flat

    def recent(self, n=5):
        logs = self.load_logs()
        logs.sort(key=lambda t: t.get("created_at") or "", reverse=True)
        return logs[:n]

    # --- busca ---
    def fetch_new(self):
        """Busca posts novos respeitando o limite diário. Retorna os posts adicionados."""
        if not self.enabled or not self.handles:
            return []
        state = self._state()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if state.get("day") != today:
            state.update(day=today, posts_today=0)
        remaining = self.max_posts_per_day - state.get("posts_today", 0)
        if remaining < 10:  # a busca recente exige max_results >= 10
            log.info("Limite diário de posts do X atingido (%d); usando o histórico.", self.max_posts_per_day)
            return []
        params = {
            "query": self.build_query(),
            "max_results": min(100, remaining),
            "tweet.fields": "created_at,author_id",
            "expansions": "author_id",
            "user.fields": "username",
        }
        if state.get("since_id"):
            params["since_id"] = state["since_id"]
        try:
            r = requests.get(SEARCH_URL, headers=self.headers, params=params, timeout=20)
            if r.status_code == 429:
                log.warning("Limite de requisições da API do X; tentando no próximo ciclo.")
                return []
            r.raise_for_status()
            body = r.json()
        except (requests.RequestException, ValueError) as e:
            log.error("Erro ao buscar posts no X: %s", type(e).__name__)
            return []

        users = {u["id"]: u.get("username") for u in body.get("includes", {}).get("users", [])}
        posts = [
            {"id": t["id"], "created_at": t.get("created_at"), "author": users.get(t.get("author_id"), ""),
             "text": t.get("text", "")}
            for t in body.get("data", []) or []
        ]
        meta = body.get("meta", {})
        if meta.get("newest_id"):
            state["since_id"] = meta["newest_id"]
        state["posts_today"] = state.get("posts_today", 0) + len(posts)
        self._save_json(self.state_path, state)
        log.info("X: %d posts novos (≈US$%.3f); hoje %d/%d posts.", len(posts), len(posts) * PRICE_PER_POST,
                 state["posts_today"], self.max_posts_per_day)

        existing = self.load_logs()
        ids = {t.get("id") for t in existing}
        added = [p for p in posts if p["id"] not in ids]
        if added:
            merged = sorted(existing + added, key=lambda t: t.get("created_at") or "")[-self.keep:]
            self._save_json(self.log_path, merged)
        return added

    def fetch_and_get_recent(self, n=5, min_interval=1800):
        now = time.time()
        if self.enabled and now - self._last_fetch >= min_interval:
            self._last_fetch = now
            self.fetch_new()
        return self.recent(n)
