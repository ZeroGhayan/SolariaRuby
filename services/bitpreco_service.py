import requests

class BitPrecoService:
    def __init__(self, api_key, signature):
        self.api_key = api_key
        self.signature = signature
        self.base_url = 'https://api.bitpreco.com'

    def _generate_auth_token(self):
        """
        Gera o token de autenticação concatenando a assinatura e a chave da API.
        """
        return f'{self.signature}{self.api_key}'

    def _generate_signature(self, payload):
        """
        Gera a assinatura HMAC-SHA256 para autenticação na API.
        """
        payload_json = json.dumps(payload, separators=(',', ':'))
        signature = hmac.new(
            self.api_key.encode('utf-8'),
            payload_json.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature

    def _post_request(self, endpoint, payload):
        """
        Realiza uma solicitação POST autenticada à API da BitPreço.
        """
        url = f'{self.base_url}/{endpoint}'
        headers = {'Content-Type': 'application/json'}
        payload['auth_token'] = self.auth_token
        try:
            print(f"DEBUG: Enviando solicitação para {url} com payload: {payload}")  # Log para depuração
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            print(f"DEBUG: Resposta recebida: {data}")  # Log para depuração
            if data.get("success", False):
                return data
            else:
                error_message = data.get('message_cod', 'Erro desconhecido')
                print(f"Erro na resposta da API: {error_message}")
                return None
        except requests.exceptions.RequestException as e:
            print(f"Erro na solicitação POST para {endpoint}: {e}")
            return None

    def get_balance(self):
        """
        Obtém o saldo da conta.
        """
        url = f'{self.base_url}/v1/trading/'
        auth_token = self._generate_auth_token()
        headers = {'Content-Type': 'application/json'}
        payload={}
        payload['cmd']='balance'
        payload['auth_token']=auth_token
        try:
            #print(f"DEBUG: Enviando solicitação para {url} com payload: {payload}")  # Log para depuração
            response = requests.post(url, headers=headers, json=payload)
            #print(response.text)
            response.raise_for_status()
            #print(f"DEBUG: Resposta recebida: {response}")  # Log para depuração
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Erro ao obter saldo: {e}")
            return None

    def get_open_orders(self, market="BTC-BRL"):
        """
        Obtém as ordens abertas.
        """
        payload = {'market': market}
        return self._post_request('trading/open_orders', payload)

    def place_order(self, order_type, quantity, price, pair="btc-brl"):
        """
        Envia uma ordem de compra ou venda.
        :param order_type: Tipo da ordem ("buy" ou "sell").
        :param quantity: Quantidade de BTC.
        :param price: Preço por unidade de BTC.
        :param pair: Par de moedas (padrão: "btc-brl").
        :return: Resposta da API ou None em caso de erro.
        """
        url = f"{self.base_url}/v1/trading/orders"
        headers = self._get_auth_headers()
        payload = {
            "type": order_type,
            "quantity": quantity,
            "price": price,
            "pair": pair,
            "auth_token": self.auth_token
        }
        try:
            response = requests.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            if data.get("success", False):
                print(f"Ordem de {order_type} executada com sucesso: {data}")
                return data
            else:
                print(f"Erro na ordem de {order_type}: {data.get('message_cod', 'Erro desconhecido')}")
                return None
        except requests.exceptions.RequestException as e:
            print(f"Erro na solicitação de ordem ({order_type}): {e}")
            return None


    def cancel_order(self, order_id):
        """
        Cancela uma ordem específica.
        """
        payload = {'order_id': order_id}
        return self._post_request('trading/order_cancel', payload)

    def cancel_all_orders(self):
        """
        Cancela todas as ordens abertas.
        """
        return self._post_request('trading/all_orders_cancel', {})

    def get_market_data(self, pair='btc-brl'):
        """
        Obtém os dados de mercado para o par especificado.
        """
        url = f'{self.base_url}/{pair}/ticker'
        try:
            response = requests.get(url)
            response.raise_for_status()
            #print(response.text)
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Erro ao obter dados de mercado: {e}")
            return None
'''
    def calculate_daily_change(self, market_data):
        """
        Calcula a variação percentual diária com base nos dados de mercado.
        """
        last_price = float(market_data.get('last', 0))
        high_price = float(market_data.get('high', 0))
        low_price = float(market_data.get('low', 0))
        if high_price == low_price:
            return 0.0
        daily_change = ((last_price - low_price) / (high_price - low_price)) * 100
        return daily_change
'''