# Solaria Ruby — Bot de trading spot (OKX + Grok)

Bot leve em Python que roda em loop no Orange Pi 5 (ARM64) ou em qualquer Linux. A cada ciclo, para cada par configurado:

1. lê o ticker e o saldo livre na **OKX** (via [ccxt](https://github.com/ccxt/ccxt));
2. cancela ordens abertas do par;
3. pede uma decisão ao **Grok (xAI)** (`grok-4.3`, raciocínio `none`) usando o SDK `openai`, que responde
   só com um **comando rígido de 8 caracteres** (veja abaixo);
4. valida saldo, margem de segurança e mínimos da OKX;
5. executa uma ordem a mercado e avisa no Telegram **apenas se a ordem foi executada** (ou simulada).

Erros da IA ou qualquer resposta fora do formato resultam em **manter**. Por padrão o ciclo roda **a cada 4 horas**. Erros técnicos vão para o canal de debug do Telegram.

> ⚠️ `DRY_RUN=true` é o padrão: nenhuma ordem real é enviada. Só mude para `false` depois de acompanhar as simulações.

## Requisitos
- Python 3.10+
- Conta na OKX com chave de API (permissão **Trade** apenas, **sem Withdraw**, restrita ao IP do Orange Pi)
- Chave da API xAI
- Bot do Telegram (opcional, mas recomendado)
- Token da API do X/Twitter (opcional; exige plano pago). Sem ele, o bot usa só o histórico em `logs/twitter_logs.json`.

## Instalação
```bash
cd ~/dgsManager
git clone https://github.com/ZeroGhayan/SolariaRuby.git   # ou git pull, se já existir
cd SolariaRuby                 # /home/orangepi/dgsManager/SolariaRuby
./scripts/setup.sh        # cria ./venv, instala requirements e gera .env
nano .env                 # preencha as chaves
./venv/bin/python main.py
```

## Configuração (`.env`)
| Variável | Descrição |
|---|---|
| `OKX_API_KEY`, `OKX_API_SECRET`, `OKX_API_PASSPHRASE` | Credenciais da OKX |
| `OKX_SANDBOX` | `true` para usar o ambiente demo da OKX |
| `XAI_API_KEY`, `XAI_MODEL` | Chave e modelo do Grok (padrão `grok-4.3`; o antigo `grok-4-1-fast-reasoning` foi aposentado em 15/05/2026) |
| `XAI_REASONING_EFFORT` | `none` (padrão, mais barato), `low`, `medium`, `high`. Vazio = padrão da API (`low`) |
| `XAI_MAX_TOKENS` | Limite de tokens da resposta (padrão 16) |
| `XAI_PRICE_INPUT_PER_M`, `XAI_PRICE_CACHED_PER_M`, `XAI_PRICE_OUTPUT_PER_M` | Preços (US$/1M tokens) usados para estimar o custo no log |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID_MAIN`, `TELEGRAM_CHAT_ID_DEBUG` | Notificações (principal = ordens; debug = erros) |
| `TWITTER_BEARER_TOKEN`, `TWITTER_USERNAME`, `TWITTER_HASHTAG` | Fonte opcional de tweets |
| `TRADING_PAIRS` | Pares separados por vírgula, ex.: `BTC/BRL` ou `BTC/BRL,BTC/USDT` |
| `DRY_RUN` | `true` (padrão) simula as ordens |
| `INTERVAL_SECONDS` | Intervalo entre ciclos (padrão 14400 = 4 h) |
| `SCHEDULE_TIMES` | Opcional: horários fixos locais, ex. `01:00,04:00,07:00,10:00,13:00,16:00,19:00,22:00`. Tem prioridade sobre o intervalo |
| `SAFETY_MARGIN` | Fração do saldo que nunca é usada (padrão 0.05) |
| `LOG_LEVEL` | `INFO`, `DEBUG`... |

Pares inexistentes no spot da OKX são ignorados na inicialização, com erro no log.

## Comando de 8 caracteres
Formato `APPPTTTT`, validado pela regex `^([CVM])(\d{3})([A-Z0-9_]{4})$`:

| Parte | Significado |
|---|---|
| `A` | `C` comprar, `V` vender, `M` manter |
| `PPP` | Percentual do saldo disponível (000–100). Na compra, % do saldo da moeda de cotação (ex.: BRL); na venda, % do saldo do ativo. `M` exige `000`, e `C`/`V` exigem pelo menos `001` |
| `TTTT` | Ativo base do par, completado com `_` (ex.: `BTC_`, `ETH_`, `USDT`); tem que bater com o par |

Exemplos: `C025BTC_` (comprar BTC com 25% do saldo em BRL), `V010BTC_` (vender 10% do BTC), `M000BTC_` (manter).
A margem de segurança (`SAFETY_MARGIN`) e os mínimos da OKX são aplicados depois. Qualquer outra resposta vira `manter`.

## Custo da IA
Cada chamada envia um prompt curto (preço, saldo e até 3 tweets resumidos) e recebe ~4–8 tokens.
O log mostra os tokens e o custo estimado de cada chamada, além do total acumulado. Com `grok-4.3`
(US$ 1,25/1M de entrada, US$ 2,50/1M de saída), uma chamada sai em torno de US$ 0,0002–0,0004;
são 6 chamadas por dia e por par no ciclo de 4 h.

## Rodar como serviço (systemd)
No Orange Pi **já existe um serviço funcionando**. Não crie outro: aponte o existente para o novo caminho.
O arquivo `deploy/solaria-ruby.service` serve só de referência.

1. Descubra o nome do serviço e veja a configuração atual:
   ```bash
   systemctl list-units --type=service | grep -i -E 'solaria|ruby|trade'
   systemctl cat <nome>
   ```
2. Edite o serviço (o `--full` abre o arquivo original):
   ```bash
   sudo systemctl edit --full <nome>
   ```
   e deixe a seção `[Service]` assim:
   ```ini
   User=orangepi
   WorkingDirectory=/home/orangepi/dgsManager/SolariaRuby
   EnvironmentFile=/home/orangepi/dgsManager/SolariaRuby/.env
   ExecStart=/home/orangepi/dgsManager/SolariaRuby/venv/bin/python main.py
   Restart=on-failure
   RestartSec=30
   ```
3. Recarregue e reinicie:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl restart <nome>
   systemctl status <nome>
   journalctl -u <nome> -f
   ```

O `.env` também é lido pelo próprio bot (python-dotenv), então o `EnvironmentFile` é uma garantia extra.

## Estrutura
```
main.py                     loop principal
trader.py                   lógica de um ciclo (dimensionamento e validação da ordem)
configs/settings.py         leitura do .env
services/exchange_service.py   OKX via ccxt
services/analysis_service.py   Grok via SDK openai (comando de 8 caracteres)
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
