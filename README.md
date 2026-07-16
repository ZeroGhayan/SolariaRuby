# Solaria Ruby — Bot de Day Trade Automatizado (BitPreço + Grok)

**Solaria Ruby** é um bot de day trade desenvolvido para operar na exchange brasileira **BityPreço**, utilizando a inteligência artificial **Grok** (xAI) para tomar decisões assertivas em 8 horários fixos diários (01:00, 04:00, 07:00, 10:00, 13:00, 16:00, 19:00,  22:00 -3).

O foco principal é maximizar a acumulação de BTC a longo prazo, com risco controlado, margem de segurança e execução eficiente. O bot já suporta múltiplos ativos com par em BRL (BTC, ETH, USDT, SOL, XRP, ADA, DOGE e dezenas de outros).

Projeto hospedado em um Orange Pi 5 e compatível com Raspberry Pi ou similares, totalmente open-source para fins educacionais e de portfólio.

## Tecnologias
- Python 3.10+
- API da BityPreço (trading e ticker)
- API do Grok (xAI) — modelo `grok-4-1-fast-reasoning`
- Telegram Bot (notificações em canais separados: principal e debug)
- Bibliotecas: `requests`, `openai`, `python-dotenv`

## Funcionalidades
- Coleta automática de saldo e preços
- Decisão via Grok baseada em tweets e dados de mercado
- Comando de 8 caracteres rígido para máxima eficiência e segurança
- Suporte nativo a múltiplos ativos (todos com par -BRL)
- Cancelamento automático de ordens pendentes
- Proteções: margem de segurança (5%), mínimos de trade, fallback para "manter"
- Canais Telegram separados (principal = financeiro, debug = técnico)

## Instalação

1. Clone o repositório:
   ```bash
   git clone https://github.com/seu-usuario/solaria-ruby.git
   cd solaria-ruby
   ```

2. Crie e ative um ambiente virtual (recomendado):
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```

## Configuração

1. Renomeie `env.example` para `.env` e preencha com suas chaves:
   ```
   BITPRECO_API_KEY=...
   BITPRECO_SIGNATURE=...
   TELEGRAM_BOT_TOKEN=...
   TELEGRAM_CHAT_ID_MAIN=...
   TELEGRAM_CHAT_ID_DEBUG=...
   XAI_API_KEY=...
   ```

2. Execute em produção:
   ```bash
   python main.py
   ```

Para rodar automaticamente via systemd (recomendado em Raspberry Pi ou similares):
```ini
[Unit]
Description=Solaria Ruby Trading Bot
After=network.target

[Service]
WorkingDirectory=/caminho/para/solariaRuby
ExecStart=/usr/bin/python3 main.py
Restart=always
User=orangepi

[Install]
WantedBy=multi-user.target
```

## Código de Indicação BityPreço
Use meu código de indicação ao criar sua conta na BityPreço e ganhe benefícios:

Link direto: https://bity.com.br/108870

## Apoio ao Desenvolvedor
Se o projeto te ajudou ou você obteve lucro com ele, considere apoiar o desenvolvimento:

- **Pix**: `pjsdunham@tutanota.com`
- **Bitcoin**: `bc1p36aamex4zqn76wyk53gdvmpz5rklc8hdnuam78xnjpk2c8c5s9ystnhj2q`

Qualquer valor é bem-vindo e ajuda a manter e evoluir o bot!

## Aviso Legal
Este é um projeto educacional. Trading envolve risco de perda de capital. Use por sua conta e risco. Não sou responsável por perdas financeiras.

Desenvolvido por 00Zero (@ZeroGhayan no X)

⭐ Se gostou, dê uma estrela no repositório!
