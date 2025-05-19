import openai
import json
import os
import re

class AnalysisService:
    def __init__(self, api_key):
        openai.api_key = api_key
        self.twitter_log_path = os.path.join("logs", "twitter_logs.json")

    def _load_twitter_logs(self):
        """
        Carrega o arquivo de logs do Twitter.
        Retorna uma lista de logs ou uma lista vazia se o arquivo não existir ou estiver com formato inválido.
        """
        if os.path.exists(self.twitter_log_path):
            with open(self.twitter_log_path, "r", encoding="utf-8") as file:
                try:
                    return json.load(file)
                except json.JSONDecodeError:
                    print("Erro ao carregar os logs do Twitter: JSON inválido.")
        return []

    def extract_amount(self, text):
        """
        Extrai o primeiro valor numérico encontrado em uma string.
        
        Parâmetros:
          text (str): A string da qual extrair o valor.
        
        Retorna:
          float: O primeiro número encontrado na string, ou None se não houver número.
        """
        pattern = r'-?\d+\.?\d*'
        matches = re.findall(pattern, text)
        if matches:
            return float(matches[0])
        else:
            return None

    def analyze_trade_data(self, twitter_logs, market_data):
        """
        Envia um prompt ao ChatGPT para gerar uma análise e decisão de trading.
        
        Parâmetros:
          twitter_logs (list): Lista de tweets relevantes (já lidos do log JSON).
          market_data (dict): Informações de mercado (preço, variação, saldos, etc.).
        
        Retorna:
          str: Decisão sugerida pelo modelo (ex.: "comprar", "vender", ou "manter", possivelmente com a quantidade).
        """
        # Garantir que os dados estão no formato esperado
        if not isinstance(twitter_logs, list) or not all(isinstance(tweet, dict) for tweet in twitter_logs):
            print("Erro: Formato inválido para twitter_logs. Usando lista vazia.")
            twitter_logs = []
        if not isinstance(market_data, dict):
            print("Erro: Formato inválido para market_data. Usando valores padrão.")
            market_data = {
                "btc_price": 0.0,
                "btc_balance": 0.0,
                "brl_balance": 0.0,
                "daily_change": 0.0,
            }

        # Limitar os tweets a, no máximo, os 5 mais recentes
        twitter_data_texts = [f"- {tweet['text']}" for tweet in twitter_logs][:5]

        prompt = (
            "Você é Solaria Ruby, uma assistente financeira especializada em trading de Bitcoin. "
            "Baseando-se nos dados fornecidos, gere uma análise breve e indique a decisão mais recomendada "
            "('comprar', 'vender' ou 'manter') e a quantidade a ser utilizada, considerando o saldo disponível.\n\n"
            "Dados de mercado:\n"
            f"- Preço atual do BTC: {market_data['btc_price']} BRL\n"
            f"- Variação diária: {market_data['daily_change']}%\n"
            f"- Saldo em BTC: {market_data['btc_balance']} BTC\n"
            f"- Saldo em BRL: {market_data['brl_balance']} BRL\n\n"
            "Últimos tweets relevantes:\n" + "\n".join(twitter_data_texts) + "\n\n"
            "Forneça uma análise clara e indique a decisão (comprar, vender ou manter) junto com a quantidade recomendada."
        )

        try:
            print("Prompt enviado ao ChatGPT:")
            print(prompt)
            response = openai.ChatCompletion.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "Você é uma especialista em trading de Bitcoin."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=300,
                temperature=0.7
            )
            print("Resposta da API OpenAI:")
            print(response)
            return response['choices'][0]['message']['content']
        except Exception as e:
            # Se o erro indicar cota insuficiente (429 ou mensagem de insuficiência), retorna decisão padrão "manter"
            if "429" in str(e) or "insufficient_quota" in str(e):
                print("Quota excedida, utilizando decisão padrão: manter")
                return "manter"
            print(f"Erro inesperado: {e}")
            return f"Erro: {e}"

    def evaluate_decision(self, decision, market_data):
        """
        Avalia se a decisão de trading pode ser executada com base nos saldos disponíveis.
        
        Parâmetros:
          decision (str): Decisão sugerida (por exemplo, "comprar", "vender" ou "manter").
          market_data (dict): Informações de mercado.
        
        Retorna:
          bool: True se a decisão for viável, False caso contrário.
        """
        decision = decision.lower().strip() if decision else ""
        if decision == "comprar":
            return float(market_data['brl_balance']) >= 50.0
        elif decision == "vender":
            return float(market_data['btc_balance']) > 0.0
        return True  # "manter" é sempre viável
