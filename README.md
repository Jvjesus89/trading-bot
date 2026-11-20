# Trading Bot - Motor Quantitativo de Alta Performance
# Binance Spot | Reversão à Média + Tendência Primária

## Requisitos
- Python 3.11+
- Node.js 20+ (para rodar frontend localmente)
- Docker & Docker Compose (para deploy completo)

## Setup com Docker (Bot + Frontend em Paralelo)

Para rodar todo o ecossistema (robô quantitativo + painel web) com um único comando:

```bash
# 1. Subir ambos os serviços em segundo plano com rebuild
docker-compose up --build -d

# 2. Acompanhar os logs
docker-compose logs -f

# Ou logs específicos:
docker-compose logs -f trading-bot
docker-compose logs -f frontend
```

O dashboard estará disponível em: 👉 **http://localhost:3000**

---

## Setup Rápido Local (Sem Docker)

```bash
# 1. Clone e entre no diretório
cd trading-bot

# 2. Crie o ambiente virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 3. Instale as dependências do bot
pip install -r requirements.txt

# 4. Configure as credenciais
cp .env.example .env
# Edite o .env com suas chaves

# 5. Execute em modo Paper Trading
python -m src.main
```

## Frontend Dashboard (React / Next.js) Local

```bash
cd frontend
npm install
npm run dev
```

Acesse no navegador:
👉 **http://localhost:3000**

---

## Estrutura do Projeto
```
trading-bot/
├── src/
│   ├── main.py              # Entry point e orquestrador
│   ├── config.py             # Carregamento de configurações
│   ├── exchange.py           # Abstração Binance (CCXT)
│   ├── indicators.py         # Cálculos técnicos (RSI, BB, ATR, RVOL)
│   ├── strategy.py           # Lógica de entrada/saída
│   ├── risk_manager.py       # Circuit breakers e gestão de risco
│   ├── ai_advisor.py         # Auditoria de entrada DeepSeek
│   ├── state_manager.py      # Máquina de estados e crash recovery
│   ├── notifier.py           # Telegram + Healthcheck
│   ├── persistence.py        # Supabase/PostgreSQL
│   └── paper_trading.py      # Simulador local
├── frontend/
│   ├── src/                 # Next.js App Router & componentes
│   ├── Dockerfile           # Multi-stage build standalone
│   ├── .dockerignore        # Exclusão de node_modules e cache
│   └── next.config.ts       # Configuração standalone ativada
├── logs/                    # Volume compartilhado (telemetria e trades)
├── docker-compose.yml       # Orquestração (trading-bot + frontend)
├── Dockerfile               # Imagem Python do bot
└── README.md
```

## Modos de Operação
- `TRADING_MODE=PAPER` — Simulação sem ordens reais
- `TRADING_MODE=LIVE` — Execução real na Binance

## Auditoria de IA por Entrada (DeepSeek)

Cada compra aprovada pelos 4 filtros técnicos é enviada ao DeepSeek antes da
ordem, com preço, RSI (5m), RVOL e variação do BTC (4h). A ordem só executa se
o veredito autorizar; o motivo e as métricas ficam gravados em `ia_snapshot` e
aparecem no botão **Auditar** do painel.

```env
AI_VALIDATION_ENABLED=true
DEEPSEEK_API_KEY=sua_chave_aqui
DEEPSEEK_MODEL=deepseek-chat
```

Comportamento em falha (fail-closed):
- Erro/timeout/HTTP inválido do DeepSeek: a entrada é **bloqueada**.
- `AI_VALIDATION_ENABLED=false` ou chave ausente: no PAPER a entrada é liberada
  sem auditoria (o painel marca "IA desativada" / "chave ausente"); no LIVE a
  entrada é **bloqueada** — dinheiro real nunca opera sem auditor.

## DNS no Docker

O `docker-compose.yml` fixa `8.8.8.8`, `8.8.4.4` e `1.1.1.1` nos dois serviços.
Sem isso, o resolver interno do Docker pode falhar (VPN/firewall do host) e
derrubar `api.binance.com` com `Temporary failure in name resolution`. O cliente
CCXT também reprocessa `ccxt.NetworkError` (que inclui falhas de DNS) com backoff.

## Recursos do Dashboard
- **Gráfico ao Vivo (TradingView Lightweight Charts)**: Candlestick 5m, Bandas de Bollinger (20, 2.0), EMA e sub-gráfico de RSI (14) com faixas de sobrevenda (32) e sobrecompra (70).
- **Radar de 5 Condições**: Checklist em tempo real dos gatilhos simultâneos para compra a mercado.
- **Auditor de IA (DeepSeek) por entrada**: Antes de cada compra, envia preço, RSI (5m), RVOL e variação do BTC (4h) ao modelo; a ordem só executa se o veredito autorizar. O motivo e as métricas ficam gravados no trade e visíveis no botão "Auditar".
- **Livro de Registros**: Histórico de compras e vendas, PnL líquido em R$ e %, badges de saída (Take Profit, Breakeven, Trailing, Stop Loss) e modal com snapshot JSON da auditoria de IA.
- **KPIs em Tempo Real**: Saldo da banca, PnL do dia com barra de limite do Drawdown (-R$ 6,00) e status dos Circuit Breakers.

## Backtest (original vs V2 vs configuração atual)

Antes de mudar qualquer parâmetro, valide em dados históricos reais:

```bash
python -m src.backtest                 # 90 dias de SOL/BRL
python -m src.backtest --dias 180 --spread 0.12
```

Compara três perfis com as mesmas regras do bot ao vivo (taxas e spread incluídos):
`ORIGINAL` (commit 8a8a4c9), `V2` (setup + candle de reversão, alvo na média) e
`ATUAL` (o que o seu `.env` configura). Os trades ficam em `logs/backtest/`.
Para pesquisa mais ampla (experimentos, momentum), veja `research/README.md`.
