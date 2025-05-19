# configs/api_keys.py

# Este arquivo centraliza as chaves e tokens usados no projeto.

#Arquivo de leitura
with open('api.txt') as api:
    lines = [line.rstrip() for line in api]
api.close()

# Insere as credenciais de cada
BITPRECO_API_KEY = lines[0] #OK
BITPRECO_SIGNATURE = lines[1] #OK

TELEGRAM_BOT_TOKEN = lines[2] #OK
TELEGRAM_CHAT_ID = lines[3] #OK

OPENAI_API_KEY = lines[4]

TWITTER_API_KEY = lines[5] #OK
TWITTER_API_SECRET = lines[6] #OK
TWITTER_BEARER_TOKEN = lines[7] #OK
TWITTER_ACCESS_TOKEN = lines[8] #OK
TWITTER_ACCESS_SECRET = lines[9] #OK

#HUGGINGFACE_API = lines[10]

#Depuração

