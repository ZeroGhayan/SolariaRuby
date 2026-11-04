# Solaria Ruby — Bot de trading spot (OKX + Grok)

Bot leve em Python que roda em loop no Orange Pi 5 (ARM64) ou em qualquer Linux. A cada ciclo, para cada par configurado:

1. lê o ticker e o saldo livre na **OKX** (via [ccxt](https://github.com/ccxt/ccxt));
2. cancela ordens abertas do par;
3. pede uma decisão ao **Grok (xAI)** usando o SDK `openai`, com saída JSON validada
   `{"acao": "comprar|vender|manter", "quantidade": <moeda base>, "motivo": "..."}`;
4. valida saldo, margem de segurança e mínimos da OKX;
5. executa uma ordem a mercado e avisa no Telegram **apenas se a ordem foi executada** (ou simulada).

Erros da IA ou respostas inválidas resultam em **manter**. Erros técnicos vão para o canal de debug do Telegram.

> ⚠️ `DRY_RUN=true` é o padrão: nenhuma ordem real é enviada. Só mude para `false` depois de acompanhar as simulações.

## Requisitos
- Python 3.10+
- Conta na OKX com chave de API (permissão **Trade** apenas, **sem Withdraw**, restrita ao IP do Orange Pi)
- Chave da API xAI
- Bot do Telegram (opcional, mas recomendado)
- Token da API do X/Twitter (opcional; exige plano pago). Sem ele, o bot usa só o histórico em `logs/twitter_logs.json`.

## Instalação
```bash
git clone https://github.com/ZeroGhayan/SolariaRuby.git
cd SolariaRuby
./scripts/setup.sh        # cria venv, instala requirements e gera .env
nano .env                 # preencha as chaves
./venv/bin/python main.py
```

## Configuração (`.env`)
| Variável | Descrição |
|---|---|
| `OKX_API_KEY`, `OKX_API_SECRET`, `OKX_API_PASSPHRASE` | Credenciais da OKX |
| `OKX_SANDBOX` | `true` para usar o ambiente demo da OKX |
| `XAI_API_KEY`, `XAI_MODEL` | Chave e modelo do Grok (padrão `grok-4-1-fast-reasoning`) |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID_MAIN`, `TELEGRAM_CHAT_ID_DEBUG` | Notificações (principal = ordens; debug = erros) |
| `TWITTER_BEARER_TOKEN`, `TWITTER_USERNAME`, `TWITTER_HASHTAG` | Fonte opcional de tweets |
| `TRADING_PAIRS` | Pares separados por vírgula, ex.: `BTC/BRL` ou `BTC/BRL,BTC/USDT` |
| `DRY_RUN` | `true` (padrão) simula as ordens |
| `INTERVAL_SECONDS` | Intervalo entre ciclos (padrão 600) |
| `SAFETY_MARGIN` | Fração do saldo que nunca é usada (padrão 0.05) |
| `LOG_LEVEL` | `INFO`, `DEBUG`... |

Pares inexistentes no spot da OKX são ignorados na inicialização, com erro no log.

## Rodar como serviço
Veja `deploy/solaria-ruby.service` (systemd). Os logs ficam no `journalctl -u solaria-ruby`.

## Estrutura
```
main.py                     loop principal
trader.py                   lógica de um ciclo (dimensionamento e validação da ordem)
configs/settings.py         leitura do .env
services/exchange_service.py   OKX via ccxt
services/analysis_service.py   Grok via SDK openai (JSON estruturado)
services/telegram_service.py   notificações
services/twitter_service.py    tweets (opcional)
tests/                      pytest com exchange e IA simulados
```

## Testes
```bash
./venv/bin/pip install -r requirements-dev.txt
./venv/bin/python -m pytest -q
```

## Aviso
Projeto educacional. Trading automatizado envolve risco de perda total. Use por sua conta e risco.
