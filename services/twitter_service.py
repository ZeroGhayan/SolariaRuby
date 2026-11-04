"""Coleta opcional de tweets via API v2 do X (requer plano pago)."""
import json
import logging
import os
import time

import requests

log = logging.getLogger(__name__)
BASE_URL = "https://api.twitter.com/2"


class TwitterService:
    def __init__(self, bearer_token, username, hashtag="#nostreidamos", log_path=os.path.join("logs", "twitter_logs.json")):
        self.enabled = bool(bearer_token)
        self.headers = {"Authorization": f"Bearer {bearer_token}"}
        self.username = username
        self.hashtag = hashtag.lower()
        self.log_path = log_path
        self._user_id = None
        if not self.enabled:
            log.info("Twitter desativado (TWITTER_BEARER_TOKEN ausente); usando apenas o histórico local.")

    def _get(self, path, params=None):
        r = requests.get(f"{BASE_URL}{path}", headers=self.headers, params=params, timeout=20)
        if r.status_code == 429:
            log.warning("Limite da API do X atingido; tentando no próximo ciclo.")
            return None
        r.raise_for_status()
        return r.json()

    def load_logs(self):
        """Lê o histórico e achata listas aninhadas (formato antigo)."""
        if not os.path.exists(self.log_path):
            return []
        try:
            with open(self.log_path, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            log.warning("Histórico de tweets ilegível; ignorando.")
            return []
        flat = []
        stack = list(data) if isinstance(data, list) else []
        while stack:
            item = stack.pop(0)
            if isinstance(item, list):
                stack[0:0] = item
            elif isinstance(item, dict) and "text" in item:
                flat.append(item)
        return flat

    def _save(self, tweets):
        os.makedirs(os.path.dirname(self.log_path) or ".", exist_ok=True)
        tmp = self.log_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(tweets, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.log_path)

    def get_user_tweets(self, count=10):
        """Busca tweets novos com a hashtag e mescla ao histórico (sem duplicatas)."""
        if not self.enabled:
            return []
        try:
            if not self._user_id:
                data = self._get(f"/users/by/username/{self.username}")
                if not data:
                    return []
                self._user_id = data["data"]["id"]
            data = self._get(f"/users/{self._user_id}/tweets",
                             {"max_results": max(5, min(count, 100)), "tweet.fields": "created_at,conversation_id"})
        except (requests.RequestException, KeyError) as e:
            log.error("Erro ao buscar tweets: %s", type(e).__name__)
            return []
        new = [
            {"id": t["id"], "created_at": t.get("created_at"), "text": t["text"],
             "conversation_id": t.get("conversation_id")}
            for t in (data or {}).get("data", []) if self.hashtag in t.get("text", "").lower()
        ]
        existing = self.load_logs()
        ids = {t.get("id") for t in existing}
        added = [t for t in new if t["id"] not in ids]
        if added:
            self._save(existing + added)
        return added

    def recent(self, n=5):
        logs = self.load_logs()
        logs.sort(key=lambda t: t.get("created_at") or "", reverse=True)
        return logs[:n]

    def fetch_and_get_recent(self, n=5, min_interval=1800):
        now = time.time()
        if self.enabled and now - getattr(self, "_last_fetch", 0) >= min_interval:
            self._last_fetch = now
            self.get_user_tweets()
        return self.recent(n)
