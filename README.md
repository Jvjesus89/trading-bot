# Trading Bot - Motor Quantitativo de Alta Performance
# Binance Spot | Reversão à Média + Tendência Primária

## Requisitos
- Python 3.11+
- Docker & Docker Compose (para deploy)

## Setup Rápido

```bash
# 1. Clone e entre no diretório
cd trading-bot

# 2. Crie o ambiente virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 3. Instale as dependências
pip install -r requirements.txt

# 4. Configure as credenciais
cp .env.example .env
# Edite o .env com suas chaves

# 5. Execute em modo Paper Trading
python -m src.main
```

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
│   ├── ai_advisor.py         # Integração Gemini Flash
│   ├── state_manager.py      # Máquina de estados e crash recovery
│   ├── notifier.py           # Telegram + Healthcheck
│   ├── persistence.py        # Supabase/PostgreSQL
│   └── paper_trading.py      # Simulador local
├── tests/
├── logs/
├── .env.example
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── README.md
```

## Modos de Operação
- `TRADING_MODE=PAPER` — Simulação sem ordens reais
- `TRADING_MODE=LIVE` — Execução real na Binance

## Frontend Dashboard (React / Next.js)

O painel institucional permite monitorar em tempo real os gráficos técnicos, posição aberta, auditoria do Gemini Flash e o livro de ordens executadas.

### Como Iniciar o Frontend:

```bash
cd frontend
npm install
npm run dev
```

Acesse no navegador:
👉 **http://localhost:3000**

### Recursos do Dashboard:
- **Gráfico ao Vivo (TradingView Lightweight Charts)**: Candlestick 5m, Bandas de Bollinger (20, 2.0), EMA e sub-gráfico de RSI (14) com faixas de sobrevenda (32) e sobrecompra (70).
- **Radar de 5 Condições**: Checklist em tempo real dos gatilhos simultâneos para compra a mercado.
- **Auditor de IA (Gemini Flash L2)**: Nível de risco, autorização e justificativa técnica de mercado.
- **Livro de Registros**: Histórico de compras e vendas, PnL líquido em R$ e %, badges de saída (Take Profit, Breakeven, Trailing, Stop Loss) e modal com snapshot JSON da auditoria de IA.
- **KPIs em Tempo Real**: Saldo da banca, PnL do dia com barra de limite do Drawdown (-R$ 6,00) e status dos Circuit Breakers.

