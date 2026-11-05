# Solaria Ruby — Bot de trading spot (OKX + Grok)

Bot leve em Python que roda em loop no Orange Pi 5 (ARM64) ou em qualquer Linux. A cada ciclo, para cada par configurado:

1. lê o ticker e o saldo livre na **OKX** (via [ccxt](https://github.com/ccxt/ccxt));
2. cancela ordens abertas do par;
3. pede uma decisão ao **Grok (xAI)** (`grok-4.3`, raciocínio `none`) usando o SDK `openai`, que responde
   só com o **comando original de 8 caracteres** (veja abaixo);
4. valida saldo, margem de segurança e mínimos da OKX;
5. executa uma ordem a mercado e avisa no Telegram **apenas se a ordem foi executada** (ou simulada).

Erros da IA ou qualquer resposta fora do formato resultam em **manter**. Por padrão o ciclo roda **a cada 4 horas**. Erros técnicos vão para o canal de debug do Telegram.

> ⚠️ `DRY_RUN=true` é o padrão: nenhuma ordem real é enviada. Só mude para `false` depois de acompanhar as simulações.

## Requisitos
- Python 3.10+
- Conta na OKX com chave de API (permissão **Trade** apenas, **sem Withdraw**, restrita ao IP do Orange Pi)
- Chave da API xAI
- Bot do Telegram (opcional, mas recomendado)
- Bearer token da API do X (pay-per-use, com créditos comprados em console.x.com) para ler os posts de @raicher e @DollynhoCoin. Sem ele, o bot usa só o histórico em `logs/twitter_logs.json`.

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
| `XAI_CACHE_SECONDS` | Reaproveita a resposta de uma pergunta idêntica (padrão 600; 0 desliga) |
| `XAI_X_SEARCH_MAX_TURNS` | Só para `X_SOURCE=xai`: rodadas máximas de busca por chamada (padrão 1) |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID_MAIN`, `TELEGRAM_CHAT_ID_DEBUG` | Notificações (principal = ordens; debug = erros) |
| `X_SOURCE` | `x_api` (padrão), `xai` ou `off`; veja "Posts do X" |
| `TWITTER_BEARER_TOKEN` | Bearer token da API do X (para `x_api`) |
| `X_HANDLES` | Contas lidas (padrão `raicher,DollynhoCoin`) |
| `X_QUERY_FILTER` | Filtro extra opcional na busca, ex.: `#nostreidamos` (menos posts = mais barato) |
| `X_MAX_POSTS_PER_DAY` | Teto de posts lidos por dia UTC (padrão 20 = no máx. US$ 0,10/dia) |
| `TRADING_PAIRS` | Pares separados por vírgula, ex.: `BTC/BRL` ou `BTC/BRL,BTC/USDT` |
| `DRY_RUN` | `true` (padrão) simula as ordens |
| `INTERVAL_SECONDS` | Intervalo entre ciclos (padrão 14400 = 4 h) |
| `SCHEDULE_TIMES` | Opcional: horários fixos locais, ex. `01:00,04:00,07:00,10:00,13:00,16:00,19:00,22:00`. Tem prioridade sobre o intervalo |
| `SAFETY_MARGIN` | Fração do saldo que nunca é usada (padrão 0.05) |
| `LOG_LEVEL` | `INFO`, `DEBUG`... |

Pares inexistentes no spot da OKX são ignorados na inicialização, com erro no log.

## Comando de 8 caracteres (formato original do Solaria Ruby)
Formato `[Op][Entrada][Saída][Tipo][Valor]`, interpretado por um `match`/`case` caractere a caractere
(mesma lógica do `analysis_service.py` original):

| Posição | Valores |
|---|---|
| 1 – Op | `N` negociar, `M` manter (`M???????` = manter, o resto é ignorado) |
| 2 – Entrada | moeda que sai (vendida) |
| 3 – Saída | moeda que entra (comprada) |
| 4 – Tipo | `S` valor específico, `T` total (all-in, valor `0000`) |
| 5-8 – Valor | 4 dígitos. Compra: valor inteiro na moeda de cotação (BRL/USDT). Venda: satoshis (1 BTC = 100.000.000 sats) |

Códigos (`ASSET_MAP`): `R`=BRL, `B`=BTC, `E`=ETH, `D`=USDT, `S`=SOL, `X`=XRP, `A`=ADA, `G`=DOGE.
Exatamente um lado tem que ser a moeda de cotação do par (`R` para `/BRL`; `D` para `/USDT`) e o outro, o ativo do par.

Exemplos: `NRBS0200` (gastar R$ 200 em BTC), `NBRT0000` (vender todo o BTC), `NRBT0000` (usar todo o BRL), `M0000000` (manter).
Em pares `BTC/USDT`: `NDBS0150`, `NBDT0000`.

Camadas de segurança depois do comando: margem de 5% (`SAFETY_MARGIN`; o "tudo" usa 95% do saldo), mínimos da OKX
e `DRY_RUN`. Qualquer resposta inválida, ativo diferente do par ou erro da API vira **manter**.
Observação: no formato original, uma venda `S` vai até 9.999 sats (~0,0001 BTC); para vender mais, a IA usa `T`.

## Custo da IA
Prompt curto (persona e regras em cerca de 500 caracteres, mais preço, saldo e até 3 posts resumidos), `max_tokens=16`,
`temperature=0` e `reasoning_effort=none`. O log mostra os tokens e o custo estimado de cada chamada, além do total.
Com `grok-4.3` (US$ 1,25/1M de entrada, US$ 2,50/1M de saída), uma chamada sai em torno de US$ 0,0002–0,0004;
são 6 chamadas por dia e por par no ciclo de 4 h. Se a pergunta for idêntica em menos de `XAI_CACHE_SECONDS`
(padrão 600 s), a resposta anterior é reaproveitada (cache em `data/cache/`).

## Posts do X (@raicher e @DollynhoCoin)
O código antigo pedia ao Grok para "analisar em tempo real" os posts no X, mas usava `chat.completions` sem
ferramentas. **Assim o modelo não acessa o X.** A documentação da xAI diz que, sem ferramentas de busca, o Grok não tem dados
em tempo real. A antiga Live Search (`search_parameters`) foi descontinuada e hoje retorna `410 Gone`, e a busca agora só
existe como ferramenta `x_search` na Responses API. Ou seja, as decisões antigas eram tomadas **sem** os posts.

Agora há três fontes (`X_SOURCE`):

| Opção | Como funciona | Custo |
|---|---|---|
| `x_api` (**padrão**) | Uma busca `(from:raicher OR from:DollynhoCoin) -is:retweet -is:reply` na API oficial do X (`/2/tweets/search/recent`), no máximo a cada 30 min, com `since_id`: só posts **novos** vêm e são cobrados. Os textos (até 3 mais recentes) entram no prompt | US$ 0,005 por post lido, com deduplicação no mesmo dia UTC. Teto `X_MAX_POSTS_PER_DAY=20`, ou seja, **no máx. US$ 0,10/dia (≈ US$ 3/mês)**. Se as contas postarem ~6 posts/dia, ≈ US$ 0,03/dia |
| `xai` | Ferramenta `x_search` do Grok (Responses API), limitada às contas e a posts desde ontem, com `max_turns=1` | US$ 5 por 1.000 posts lidos **a cada chamada** (sem deduplicação entre chamadas), mais os tokens desses posts. Com ~20 posts por chamada: ≈ US$ 0,10 + tokens, ou **≈ US$ 0,60–0,70/dia** em 6 chamadas |
| `off` | Só o histórico local | US$ 0 |

Por isso o padrão é `x_api`: ele paga cada post uma vez só, enquanto a `x_search` relê os mesmos posts a cada ciclo.
Atenção: os créditos da API do X são **separados** dos créditos da xAI e se compram em console.x.com.
Fontes: docs.x.com (pricing pay-per-use), docs.x.ai/developers/tools/x-search, docs.x.ai/developers/pricing.

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
services/analysis_service.py   Grok via SDK openai (comando original de 8 caracteres)
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
