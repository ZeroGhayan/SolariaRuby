import time
import requests
import json
from services.bitpreco_service import BitPrecoService
from services.telegram_service import TelegramService
from services.twitter_service import TwitterService
from services.analysis_service import AnalysisService
from configs.api_keys import (
    BITPRECO_API_KEY,
    BITPRECO_SIGNATURE,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    OPENAI_API_KEY
)

# Configuração inicial
bitpreco_service = BitPrecoService(api_key=BITPRECO_API_KEY, signature=BITPRECO_SIGNATURE)
telegram_service = TelegramService(bot_token=TELEGRAM_BOT_TOKEN, chat_id=TELEGRAM_CHAT_ID)
twitter_service = TwitterService()
analysis_service = AnalysisService(api_key=OPENAI_API_KEY)

# Parâmetros de execução
TRADE_USERNAME = "allanraicher"
INTERVAL = 10 * 60 # Executa a cada 30 minutos

def main():
    fetch_twitter_counter = 0  # Contador para chamada de logs do Twitter a cada hora
    while True:
        start_time = time.time()  # Marca o início do ciclo
        try:
            print("Iniciando análise de mercado...")

            # Coleta de saldo
            balance_data = bitpreco_service.get_balance()
            if not balance_data:
                raise ValueError("Erro: Não foi possível obter o saldo. Verifique as credenciais ou a conectividade com a API.")
            
            # Coleta de dados de mercado
            market_data = bitpreco_service.get_market_data()
            if not market_data:
                raise ValueError("Erro: Dados de mercado não disponíveis.")
            
            # Cálculo da variação diária
            daily_change = float(market_data.get('var', 0))
            variation_indicator = "🔺" if daily_change >= 0 else "🔻"

            # Acessando o saldo diretamente
            btc_available = float(balance_data.get('BTC', 0))
            brl_available = float(balance_data.get('BRL', 0))

            # Depurando os valores extraídos
            print("BTC disponível: %.8f" %btc_available)
            print("BRL disponível: %.2f" %brl_available)
            btc_price = float(market_data.get('last', 0))

            #Calculando total em BRL
            total_balance_brl = btc_price * btc_available + brl_available

            # Envia resumo ao Telegram
            message = (
                f"📊 Resumo do Mercado e Saldo:\n"
                f"- Preço BTC/BRL: R${float(market_data.get('last', 0)):.2f}\n"
                f"- Maior Preço (24h): R${float(market_data.get('high', 0)):.2f}\n"
                f"- Menor Preço (24h): R${float(market_data.get('low', 0)):.2f}\n"
                f"- Volume (24h): {float(market_data.get('vol', 0)):.4f} BTC\n"
                f"- Variação Diária: {variation_indicator} {float(market_data.get('var', 0)):.4f}%\n"
                f"\n💰 Saldo:\n"
                f"- BTC: {btc_available:.8f} BTC\n"
                f"- BRL: R${brl_available:.2f}\n"
                f"- Saldo Total: R${total_balance_brl:.2f}"
            )
            print(message)  # Para debug
            telegram_service.send_message(message)

            # Coleta de dados do Twitter a cada meia hora

            if fetch_twitter_counter == 0:
                print("Buscando novos tweets")
                raw_logs = twitter_service.get_logs()
                # Garantir que logs sejam desaninhados (sem listas dentro de listas)
                if isinstance(raw_logs, list) and len(raw_logs) > 0:
                    twitter_logs = [tweet for log in raw_logs for tweet in log]
                else:
                    twitter_logs = []

                #print(f"Logs relevantes do Twitter: {twitter_logs}")
            
            # Verifica formato de twitter_logs antes de usar
            if not isinstance(twitter_logs, list) or not all(isinstance(tweet, dict) for tweet in twitter_logs):
                print("Erro: Formato inválido para twitter_logs. Ajustando para lista vazia.")
                twitter_logs = []

            # Verifica formato de market_data antes de usar
            if not isinstance(market_data, dict):
                print("Erro: Formato inválido para market_data. Ajustando para dicionário vazio.")
                market_data = {
                    "btc_price": 0.0,
                    "btc_balance": 0.0,
                    "brl_balance": 0.0,
                    "daily_change": 0.0,
                }

            #printx(f"Dados enviados ao ChatGPT:\n- Twitter Logs: {twitter_logs}\n- Dados de mercado: {market_data}")

            # Envia dados ao ChatGPT para análise
            decision = analysis_service.analyze_trade_data( #Presente erro em analysis_service.py
                twitter_logs=twitter_logs,
                market_data={
                    "btc_price": btc_price,
                    "btc_balance": btc_available,
                    "brl_balance": brl_available,
                    "daily_change": daily_change
                }
            )
            print(f"Decisão sugerida pelo ChatGPT: {decision}")

            # Avaliação da decisão
            amount = analysis_service.extract_amount(decision, btc_price, brl_available, btc_available)
            if analysis_service.evaluate_decision(decision, market_data={"btc_price": btc_price, "btc_balance": btc_available, "brl_balance": brl_available}):
                if decision.lower() == "comprar":
                    bitpreco_service.place_order(order_type="buy", quantity=amount, price=btc_price)
                elif decision.lower() == "vender":
                    bitpreco_service.place_order(order_type="sell", quantity=amount, price=btc_price)
                
                telegram_service.send_message(
                    f"💼 Decisão Executada:\n"
                    f"- Tipo: {decision.capitalize()}\n"
                    f"- Quantidade: {amount:.8f} BTC\n"
                    f"- Preço Unitário: R${btc_price:.2f}"
                )

            fetch_twitter_counter = (fetch_twitter_counter + 1) % 3  # Aumenta o contador

        except requests.exceptions.ConnectionError:
            error_message = "Erro de conexão com a API. Tentando novamente..."
            print(error_message)
            telegram_service.send_error_notification(error_message)
            
        except Exception as e:
            error_message = f"Erro no ciclo principal: {e}"
            print(error_message)
            telegram_service.send_error_notification(error_message)

        # Calcula o tempo restante no ciclo
        elapsed_time = time.time() - start_time
        remaining_time = max(0, INTERVAL - elapsed_time)
        print(f"Esperando {remaining_time:.2f} segundos até a próxima execução...")
        time.sleep(remaining_time)

if __name__ == "__main__":
    main()