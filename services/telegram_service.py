# services/telegram_service.py

import requests

class TelegramService:
    def __init__(self, bot_token, chat_id):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot7577791459:AAHbop8KdPJuBDvoQ-AU6Esvhgw0coBvgnw"

    def send_message(self, text):
        """
        Envia uma mensagem para o chat especificado.
        :param text: Texto da mensagem a ser enviada.
        :return: Resposta da API ou None em caso de erro.
        """
        if not text:
            print("Erro: Mensagem vazia.")
            return None

        endpoint = f"{self.base_url}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": text}
        try:
            response = requests.post(endpoint, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Erro ao enviar mensagem: {e}")
            return None


    def send_photo(self, photo_url, caption=None):
        """
        Envia uma foto para o chat especificado com uma legenda opcional.
        :param photo_url: URL da foto a ser enviada.
        :param caption: Legenda opcional para a foto.
        :return: Resposta da API ou None em caso de erro.
        """
        endpoint = f"{self.base_url}/sendPhoto"
        payload = {
            "chat_id": self.chat_id,
            "photo": photo_url,
            "caption": caption
        }
        try:
            response = requests.post(endpoint, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Erro ao enviar foto: {e}")
            return None

    def send_document(self, document_url, caption=None):
        """
        Envia um documento para o chat especificado com uma legenda opcional.
        :param document_url: URL do documento a ser enviado.
        :param caption: Legenda opcional para o documento.
        :return: Resposta da API ou None em caso de erro.
        """
        endpoint = f"{self.base_url}/sendDocument"
        payload = {
            "chat_id": self.chat_id,
            "document": document_url,
            "caption": caption
        }
        try:
            response = requests.post(endpoint, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Erro ao enviar documento: {e}")
            return None

    def send_error_notification(self, error_message):
        """
        Envia uma mensagem de erro ao Telegram.
        :param error_message: Mensagem detalhada sobre o erro.
        """
        text = f"⚠️ Alerta: {error_message}"
        return self.send_message(text)