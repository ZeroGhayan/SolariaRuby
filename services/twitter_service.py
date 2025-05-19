# services/twitter_service.py

import requests
import logging
import os
import time
import json
from datetime import datetime
from configs.api_keys import TWITTER_BEARER_TOKEN

class TwitterService:
    def __init__(self):
        self.base_url = "https://api.twitter.com/2"
        self.headers = {
            "Authorization": f"Bearer {TWITTER_BEARER_TOKEN}"
        }

        # Configuração de logs na pasta "logs"
        os.makedirs("logs", exist_ok=True)
        self.log_path = os.path.join("logs", "twitter_logs.json")
        self.logger = logging.getLogger("TwitterService")
        self.logger.setLevel(logging.INFO)
        handler = logging.FileHandler(self.log_path, mode="a", encoding="utf-8")
        formatter = logging.Formatter('%(asctime)s - %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

    def _load_existing_logs(self):
        """Carrega os logs existentes do arquivo."""
        if os.path.exists(self.log_path):
            with open(self.log_path, "r", encoding="utf-8") as file:
                try:
                    return json.load(file)
                except json.JSONDecodeError:
                    print("Erro ao decodificar o JSON existente no log. Ignorando conteúdo.")
        return []

    def _is_duplicate(self, latest_tweet):
        """Verifica se o último tweet já está presente nos logs."""
        existing_logs = self._load_existing_logs()
        return any(log.get("id") == latest_tweet.get("id") for log in existing_logs)

    def _append_to_log(self, new_tweet):
        """Adiciona um novo tweet ao log, caso não seja duplicado."""
        existing_logs = self._load_existing_logs()
        existing_logs.append(new_tweet)
        with open(self.log_path, "w", encoding="utf-8") as file:
            json.dump(existing_logs, file, ensure_ascii=False, indent=4)

    def _get_conversation_tweets(self, conversation_id):
        """Recupera tweets relacionados a uma conversa específica."""
        endpoint = f"{self.base_url}/tweets/search/recent"
        params = {
            "query": f"conversation_id:{conversation_id}",
            "tweet.fields": "created_at,text",
        }
        try:
            response = requests.get(endpoint, headers=self.headers, params=params)
            response.raise_for_status()
            data = response.json().get("data", [])
            return [
                {"created_at": tweet["created_at"], "text": tweet["text"], "id": tweet["id"]}
                for tweet in data
            ]
        except requests.exceptions.RequestException as e:
            print(f"Erro ao buscar tweets da conversa {conversation_id}: {e}")
            return []

    def get_user_id(self, username):
        """
        Recupera o ID de um usuário com base no nome de usuário.
        :param username: Nome de usuário no Twitter (e.g., "allanraicher").
        :return: ID do usuário ou None em caso de erro.
        """
        user_endpoint = f"{self.base_url}/users/by/username/{username}"
        try:
            response = requests.get(user_endpoint, headers=self.headers)
            response.raise_for_status()
            return response.json().get("data", {}).get("id")
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Erro ao buscar ID do usuário {username}: {e}")
            return None

    def get_user_tweets(self, username, count=10):
        """
        Recupera os tweets mais recentes de um usuário, filtrando pela hashtag relevante.
        :param username: Nome de usuário no Twitter (e.g., "allanraicher").
        :param count: Número máximo de tweets a recuperar.
        :return: Lista de tweets relevantes ou None em caso de erro.
        """
        user_id = self.get_user_id(username)
        if not user_id:
            print(f"Usuário {username} não encontrado.")
            return None

        # Endpoint para buscar tweets do usuário
        tweets_endpoint = f"{self.base_url}/users/{user_id}/tweets"
        params = {
            "max_results": count,
            "tweet.fields": "created_at,conversation_id,text",
        }
        retry_interval = 15  # Tempo inicial de espera em segundos
        while True:
            try:
                response = requests.get(tweets_endpoint, headers=self.headers, params=params)
                if response.status_code == 429:
                    retry_interval = self.handle_too_many_requests("Limite de requisições atingido", retry_interval)
                    continue  # Reenvia a requisição após o tempo de espera escalado

                response.raise_for_status()
                tweets = response.json().get("data", [])
            
                # Filtra tweets com a hashtag e mantém continuidade de logs
                relevant_tweets = []
                for tweet in tweets:
                    if "#nostreidamos" in tweet["text"].lower():
                        relevant_tweets.append({
                            "created_at": tweet["created_at"],
                            "text": tweet["text"],
                            "id": tweet["id"],
                            "conversation_id": tweet.get("conversation_id")
                        })

                '''
                if response.status_code == 429:
                    reset_time = int(response.headers.get("x-rate-limit-reset", time.time() + 60))
                    sleep_time = max(reset_time - time.time(), 0) + 1
                    print(f"Rate limit exceeded. Sleeping for {sleep_time} seconds.")
                    time.sleep(sleep_time)
                    return self.get_user_tweets(username, count)
                response.raise_for_status()
                tweets = response.json().get("data", [])
                '''

                # Verifica threads relacionadas usando get_thread_tweets
                # Inclui tweets da thread apenas do autor original
                if tweet.get("conversation_id"):
                    thread_tweets = self.get_thread_tweets(tweet["conversation_id"], user_id)
                    if thread_tweets:
                        relevant_tweets.extend(thread_tweets)

                # Elimina duplicatas e escreve no arquivo JSON
                self._append_to_log(relevant_tweets)
                return relevant_tweets

            except requests.exceptions.RequestException as e:
                print(f"Erro ao buscar tweets do usuário {username}: {e}")
                return []

    def handle_too_many_requests(self, error, retry_interval):
        """
        Trata o erro 429 escalando o tempo de espera.
        """
        print(f"Erro 429 (Muitas requisições): {error}")
        print(f"Aguardando {retry_interval} segundos antes de tentar novamente...")
        time.sleep(retry_interval)
        return retry_interval * 2  # Escala o tempo de espera se o erro persistir


    def get_thread_tweets(self, conversation_id, user_id):
        """
        Recupera todos os tweets em uma thread específica, filtrando apenas os do usuário especificado.
        :param conversation_id: ID da conversa inicial.
        :param user_id: ID do usuário principal (e.g., Allan Raicher).
        :return: Lista de tweets relacionados ou None em caso de erro.
        """
        search_endpoint = f"{self.base_url}/tweets/search/recent"
        params = {
            "query": f"conversation_id:{conversation_id} from:{user_id}",
            "tweet.fields": "created_at,text,author_id",
        }

        try:
            response = requests.get(search_endpoint, headers=self.headers, params=params)
            response.raise_for_status()
            tweets = response.json().get("data", [])

            # Filtra tweets apenas do usuário especificado
            filtered_tweets = [
                {
                    "created_at": tweet["created_at"],
                    "text": tweet["text"]
                } for tweet in tweets if tweet.get("author_id") == user_id
            ]
            return filtered_tweets
        except requests.exceptions.RequestException as e:
            print(f"Erro ao buscar tweets da thread {conversation_id}: {e}")
            return None

    def get_logs(self):
            """
            Recupera os logs do arquivo JSON de registros do Twitter.
            :return: Lista de tweets relevantes ou lista vazia se o arquivo não existir.
            """
            logs_path = os.path.join("logs", "twitter_logs.json")
            if os.path.exists(logs_path):
                with open(logs_path, "r") as logs_file:
                    try:
                        return json.load(logs_file)
                    except json.JSONDecodeError:
                        print("Erro ao ler o arquivo JSON de logs do Twitter. Retornando lista vazia.")
                        return []
            else:
                print("Arquivo de logs do Twitter não encontrado. Criando arquivo vazio.")
                return []