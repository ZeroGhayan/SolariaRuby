"""Notificações via Telegram Bot API."""
import logging

import requests

log = logging.getLogger(__name__)


class TelegramService:
    def __init__(self, bot_token, chat_id_main, chat_id_debug=""):
        self.bot_token = bot_token
        self.chat_id_main = chat_id_main
        self.chat_id_debug = chat_id_debug or chat_id_main
        self.enabled = bool(bot_token and chat_id_main)
        if not self.enabled:
            log.warning("Telegram desativado (TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID_MAIN ausentes).")

    def _send(self, chat_id, text):
        if not self.enabled or not text:
            return None
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        try:
            r = requests.post(url, json={"chat_id": chat_id, "text": text[:4000]}, timeout=15)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            # não registra a URL (contém o token)
            log.error("Falha ao enviar mensagem ao Telegram: %s", type(e).__name__)
            return None

    def send_photo(self, png_bytes, caption=""):
        """Envia um PNG (gráfico) ao chat principal via sendPhoto."""
        if not self.enabled or not png_bytes:
            return None
        url = f"https://api.telegram.org/bot{self.bot_token}/sendPhoto"
        try:
            r = requests.post(url, data={"chat_id": self.chat_id_main, "caption": caption[:1024]},
                              files={"photo": ("solaria.png", png_bytes, "image/png")}, timeout=30)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            log.error("Falha ao enviar gráfico ao Telegram: %s", type(e).__name__)
            return None

    def send_message(self, text):
        return self._send(self.chat_id_main, text)

    def send_debug(self, text):
        return self._send(self.chat_id_debug, f"⚠️ {text}")
