# Solaria Ruby — Bot de trading spot (OKX + estratégia local de Allan Raicher)

Bot leve em Python que roda em loop no Orange Pi 5 (ARM64) ou em qualquer Linux. A cada ciclo (padrão: **4 horas**), para cada par:

1. lê o ticker e o saldo livre na **OKX** (via [ccxt](https://github.com/ccxt/ccxt));
2. cancela ordens abertas do par;
3. atualiza a **memória local de velas** (SQLite) e calcula, **no próprio Orange Pi e sem custo**, os sinais
   da estratégia de Allan Raicher (@raicher) — veja "Estratégia local";
4. transforma a decisão no **comando original de 8 caracteres** (ex.: `NRBS0095`, `M0000000`);
5. valida saldo, margem de segurança e mínimos da OKX e executa (ou simula) a ordem a mercado;
6. manda um **gráfico** no Telegram (1x por dia e sempre que houver ordem).

O **Grok** entra só **1x por semana** como revisão de malha fechada (ciclos semanal, mensal, anual e de 4 anos,
Pi Cycle e halving) e devolve um viés de risco aplicado até a revisão seguinte. O modo antigo (Grok a cada ciclo)
continua disponível com `STRATEGY_MODE=grok`.

> ⚠️ `DRY_RUN=true` é o padrão: nenhuma ordem real é enviada. Só mude para `false` depois de acompanhar as simulações.

## Requisitos
- Python 3.10+
- Conta na OKX com chave de API (permissão **Trade** apenas, **sem Withdraw**, restrita ao IP do Orange Pi)
- Chave da API xAI (opcional: só para a revisão semanal ou `STRATEGY_MODE=grok`)
- Bot do Telegram (opcional, mas recomendado)
- numpy, pandas e matplotlib (instalados pelo `requirements.txt`; têm wheels prontos para ARM64, sem TA-Lib)

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
| `X_SOURCE` | `off` (padrão), `x_api` ou `xai`; só usado com `STRATEGY_MODE=grok` (veja "Posts do X") |
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
| `STRATEGY_MODE` | `local` (padrão, análise técnica no Orange Pi) ou `grok` (modo antigo, IA a cada ciclo) |
| `CANDLES_DB` | Memória de velas SQLite (padrão `data/candles.db`, fora do git) |
| `MINUTE_BACKFILL_DAYS`, `MINUTE_RETENTION_DAYS` | Dias de velas de 1 min baixados na 1ª execução (21) e mantidos (35), para montar 343m/686m |
| `REFERENCE_SYMBOL`, `REFERENCE_RATE_SYMBOL` | Par de referência para histórico curto (padrão `BTC/USDT` convertido por `USDT/BRL`; vazio desliga) |
| `NEAR_BAND_PCT` | "Perto da média": fechamento até X% acima da MA (padrão 3) |
| `BUY_FRACTION` | Fração do saldo livre por gráfico com sinal de compra (padrão 0.10) |
| `BBB_FRACTION` | Fração no BBB do 2D (padrão 1.0 = all in) |
| `BUY_COOLDOWN_HOURS` | Horas mínimas entre compras (padrão 24) |
| `FILTER_343_REQUIRED` | `true` = sem dados de 343m, não compra pelos 3 gráficos (padrão `false`) |
| `RSI_MA_LENGTH` | Média do RSI no filtro de 343m (padrão 14) |
| `SELL_ENABLED`, `SELL_TIMEFRAMES` | Venda total quando todos esses gráficos fecham acima da MA7 (padrão `1w,1M`) |
| `SELL_REQUIRE_PROFIT`, `SELL_MIN_PROFIT_PCT` | Só vende com lucro mínimo sobre o preço médio das compras do bot (padrão `true`, 2%) |
| `MIN_ORDER_BTC` | Mínimo da OKX (0.0001) |
| `TELEGRAM_CHARTS`, `CHART_EVERY_N_CYCLES` | Gráfico no Telegram a cada N ciclos (padrão 6 = 1x/dia) e sempre que houver ordem |
| `WEEKLY_REVIEW`, `WEEKLY_REVIEW_WEEKDAY`, `WEEKLY_REVIEW_HOUR` | Revisão semanal do Grok (padrão domingo, 21h local; 0=segunda ... 6=domingo) |

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

## Estratégia local (Allan Raicher)
Médias móveis **simples** do fechamento, sempre em velas **fechadas**:

| Regra | Fonte | O que o bot faz |
|---|---|---|
| **3 gráficos** | [post de 22/06/2025](https://x.com/raicher/status/1936947812811620862) | Diário: compra perto da **MA343**. Semanal: perto da **MA49**. Mensal: perto da **MA77**. "Perto" = fechamento até `NEAR_BAND_PCT`% acima da média (abaixo também vale). Cada gráfico com sinal soma `BUY_FRACTION` do saldo |
| **BBB no 2D** | [post do BBB](https://x.com/raicher/status/1990938405883289764) | Fechamento < MA200 **e** RSI(14) < 26,21 **e** StochRSI %K (14,14,3,3) < 20,44 ⇒ compra mais forte (`BBB_FRACTION`, padrão all in `NRBT0000`) |
| **Filtro 343m** | [post de entrada no 343](https://x.com/raicher/status/1991918872958824757) | Compras dos 3 gráficos só se, no 343m, fechamento > MA7 **e** RSI > média do RSI. O BBB não depende do filtro |
| **Venda** | "vende acima da MA7" | Venda **total** (`NBRT0000`) quando todos os `SELL_TIMEFRAMES` (padrão semanal e mensal) fecham acima da MA7, sem sinal de compra ativo e com lucro mínimo sobre o preço médio das compras do bot |

Escolhas e limites:
- Usar só o "acima da MA7" no diário venderia quase todo dia, por isso a venda exige semanal **e** mensal acima da MA7 e lucro mínimo — ajuste em `SELL_TIMEFRAMES`/`SELL_REQUIRE_PROFIT`.
- A venda é sempre total porque o formato original só aceita até 9.999 sats em `S`, abaixo do mínimo de 0,0001 BTC da OKX.
- Compras acima de R$ 9.999 viram `S9999` (limite de 4 dígitos), a não ser que sejam "tudo" (`T`).
- Compras abaixo do mínimo (0,0001 BTC) sobem para o mínimo se houver saldo; senão, manter.
- O preço médio usado na venda é o das **compras decididas pelo bot** (`data/strategy_state.json`), uma aproximação.
- O "suporte inferior do RSI" (linha de tendência) ainda não foi implementado — fica para uma próxima versão.
- Médias calculadas: 7, 21, 49, 77, 200, 231, 343, 686, 1372 e 2744. Cores no gráfico (as do indicador "Raicher Strategy 2"):
  MA7 verde-limão, MA21 vermelha, MA49 roxa, MA77 laranja, MA231 cinza, MA343 amarela (MA200 azul-claro, MA686 marrom, MA1372 azul-marinho, MA2744 preta).
- Qualquer média sem histórico suficiente faz a regra ser **pulada** (aparece no log e na legenda do gráfico).

### Timeframes e memória de velas
- 1d, 1w e 1M vêm direto da OKX (UTC). **343m** (= 49×7) e **686m** (= 98×7) são montados a partir de velas de 1 min e o
  **2D** a partir do diário, todos ancorados no epoch Unix (cortes estáveis entre execuções).
- Tudo fica em `data/candles.db` (SQLite) por par e timeframe. A 1ª execução baixa todo o histórico que a OKX tem
  (≈1–2 min no total); depois cada ciclo baixa só as velas novas (~1–3 s).
- Histórico da OKX em BTC/BRL (verificado em 04/11/2026): diário/semanal/mensal desde **fev/2024** (≈1.000 dias, 144 semanas,
  34 meses). A MA343 diária e a MA49 semanal já funcionam; a **MA77 mensal** só teria dados em BRL em ~2030. Por isso,
  com `REFERENCE_SYMBOL=BTC/USDT` (padrão), onde o histórico em BRL é curto o bot usa o BTC/USDT (mensal desde 2018)
  convertido pela cotação USDT/BRL da mesma vela (aproximação), e emenda com os dados reais em BRL. As ordens continuam em BTC/BRL.
  Mesmo assim, a memória continua acumulando BRL até que as médias possam ser calculadas só com ele.
- Quando o par `BTC/USDT` for adicionado em `TRADING_PAIRS`, ele usa o próprio histórico (sem conversão).

### Revisão semanal do Grok (malha fechada)
Uma vez por semana (`WEEKLY_REVIEW_WEEKDAY`/`HOUR`), o bot manda ao Grok um resumo numérico de ~6 linhas: distâncias
às médias e RSI no semanal e mensal, variação anual, **Pi Cycle Top** (SMA111 vs 2×SMA350 do diário), posição no
ciclo do halving e as decisões da semana. A resposta é só `risco,compra,venda` (ex.: `0.8,1,0`): `risco` 0–2
multiplica o tamanho das compras e `compra`/`venda` liberam ou bloqueiam. Fica salvo em `data/weekly_review.json`.
Sem `XAI_API_KEY`, ou se a chamada falhar, vale o viés neutro (`1.0,1,1`). Custo ≈ US$ 0,0005 por semana.

## Custo da IA (modo `STRATEGY_MODE=grok`)
Prompt curto (persona e regras em cerca de 500 caracteres, mais preço, saldo e até 3 posts resumidos), `max_tokens=16`,
`temperature=0` e `reasoning_effort=none`. O log mostra os tokens e o custo estimado de cada chamada, além do total.
Com `grok-4.3` (US$ 1,25/1M de entrada, US$ 2,50/1M de saída), uma chamada sai em torno de US$ 0,0002–0,0004;
são 6 chamadas por dia e por par no ciclo de 4 h. Se a pergunta for idêntica em menos de `XAI_CACHE_SECONDS`
(padrão 600 s), a resposta anterior é reaproveitada (cache em `data/cache/`).

## Posts do X (@raicher e @DollynhoCoin) — só no modo `grok`
Na estratégia local, o padrão é `X_SOURCE=off` (sem custo): as regras do Raicher já estão no código.

O código antigo pedia ao Grok para "analisar em tempo real" os posts no X, mas usava `chat.completions` sem
ferramentas. **Assim o modelo não acessa o X.** A documentação da xAI diz que, sem ferramentas de busca, o Grok não tem dados
em tempo real. A antiga Live Search (`search_parameters`) foi descontinuada e hoje retorna `410 Gone`, e a busca agora só
existe como ferramenta `x_search` na Responses API. Ou seja, as decisões antigas eram tomadas **sem** os posts.

Agora há três fontes (`X_SOURCE`):

| Opção | Como funciona | Custo |
|---|---|---|
| `x_api` | Uma busca `(from:raicher OR from:DollynhoCoin) -is:retweet -is:reply` na API oficial do X (`/2/tweets/search/recent`), no máximo a cada 30 min, com `since_id`: só posts **novos** vêm e são cobrados. Os textos (até 3 mais recentes) entram no prompt | US$ 0,005 por post lido, com deduplicação no mesmo dia UTC. Teto `X_MAX_POSTS_PER_DAY=20`, ou seja, **no máx. US$ 0,10/dia (≈ US$ 3/mês)**. Se as contas postarem ~6 posts/dia, ≈ US$ 0,03/dia |
| `xai` | Ferramenta `x_search` do Grok (Responses API), limitada às contas e a posts desde ontem, com `max_turns=1` | US$ 5 por 1.000 posts lidos **a cada chamada** (sem deduplicação entre chamadas), mais os tokens desses posts. Com ~20 posts por chamada: ≈ US$ 0,10 + tokens, ou **≈ US$ 0,60–0,70/dia** em 6 chamadas |
| `off` (**padrão**) | Não lê o X | US$ 0 |

Se for ligar no modo `grok`, prefira `x_api`: ele paga cada post uma vez só, enquanto a `x_search` relê os mesmos posts a cada ciclo.
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
services/analysis_service.py   comando de 8 caracteres (parser) e modo Grok por ciclo
services/strategy.py           estratégia local (3 gráficos, BBB, filtro 343m) -> comando
services/indicators.py         SMA, RSI, StochRSI, Pi Cycle e reamostragem (343m/686m/2D)
services/market_data.py        velas públicas da OKX + memória + par de referência
services/candle_store.py       memória SQLite (data/candles.db)
services/chart_service.py      gráfico PNG (matplotlib) para o Telegram
services/weekly_review.py      revisão semanal do Grok (malha fechada)
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
