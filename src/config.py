"""
Carregamento centralizado de configurações a partir do .env.
Todas as constantes operacionais do bot são definidas aqui.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv

# Carrega .env do diretório raiz do projeto
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class TradingConfig:
    """Configurações de trading e risco."""
    mode: str = os.getenv("TRADING_MODE", "PAPER").upper()
    symbol: str = os.getenv("SYMBOL", "SOL/BRL")
    base_currency: str = os.getenv("BASE_CURRENCY", "SOL")
    quote_currency: str = os.getenv("QUOTE_CURRENCY", "BRL")

    banca_inicial: float = float(os.getenv("BANCA_INICIAL", "100.0"))
    ordem_percentual: float = float(os.getenv("ORDEM_PERCENTUAL", "25")) / 100.0  # 0.25
    drawdown_diario_max: float = float(os.getenv("DRAWDOWN_DIARIO_MAX", "6.0")) / 100.0  # 0.06
    cooldown_stops_consecutivos: int = int(os.getenv("COOLDOWN_STOPS_CONSECUTIVOS", "2"))
    cooldown_horas: int = int(os.getenv("COOLDOWN_HORAS", "2"))

    # Parâmetros da estratégia
    ema_period: int = 200        # EMA macro (1h)
    bb_period: int = 20          # Bollinger Bands (5m)
    bb_std: float = 2.0          # Desvio padrão das Bandas
    rsi_period: int = 14         # RSI (5m)
    atr_period: int = 14         # ATR (5m)
    rvol_period: int = 20        # Volume Relativo (5m)
    rsi_threshold: float = float(os.getenv("RSI_THRESHOLD", "32.0"))  # Sobrevenda normal (<32)
    rsi_reversal_threshold: float = float(os.getenv("RSI_REVERSAL_THRESHOLD", "30.0"))  # Exaustão (<30)
    rvol_threshold: float = float(os.getenv("RVOL_THRESHOLD", "1.0"))  # Liquidez confirmada

    # Anti-faca caindo: exige que o candle de 5m seja verde (close > open) para confirmar reação compradora
    require_green_candle: bool = os.getenv("REQUIRE_GREEN_CANDLE", "true").lower() in ("true", "1", "yes")

    # Flexibilização opcional de teste para PAPER trading
    paper_ignore_ema200: bool = os.getenv("PAPER_IGNORE_EMA200", "false").lower() in ("true", "1", "yes")

    # Permite entrada por "reversão de fundo" (RSI de exaustão + candle verde)
    # MESMO com preço abaixo da EMA200. Com "false" o bot só compra dip em
    # tendência de alta — filtro de regime testado no backtest.
    # Default true = comportamento histórico (não muda produção).
    allow_below_ema_reversal: bool = os.getenv("ALLOW_BELOW_EMA_REVERSAL", "true").lower() in ("true", "1", "yes")

    # Validação de IA (Auditor DeepSeek) por entrada. Com "true" cada compra
    # aprovada pelos 4 filtros técnicos passa por uma auditoria antes da ordem.
    # Sem a chave configurada o PAPER segue sem auditoria (fail-open explícito),
    # mas o LIVE bloqueia — nunca opera dinheiro real sem auditor.
    ai_validation_enabled: bool = os.getenv("AI_VALIDATION_ENABLED", "false").lower() in ("true", "1", "yes")

    # Gestão de saída dinâmica (multiplicadores ATR com piso percentual para evitar ruído de spread)
    sl_atr_mult: float = float(os.getenv("SL_ATR_MULT", "2.0"))     # Stop Loss = Entrada - 2.0 * ATR
    sl_min_pct: float = float(os.getenv("SL_MIN_PCT", "1.5")) / 100.0  # Stop Loss Mínimo = 1.5% (protege contra spread)
    tp_atr_mult: float = float(os.getenv("TP_ATR_MULT", "2.5"))     # Take Profit = Entrada + 2.5 * ATR
    tp_min_pct: float = float(os.getenv("TP_MIN_PCT", "2.5")) / 100.0  # Take Profit Mínimo = 2.5% (assimetria TP>SL)
    be_atr_mult: float = float(os.getenv("BE_ATR_MULT", "1.0"))     # Breakeven ativa quando lucro >= 1.0 * ATR
    be_fee_offset: float = 0.0020  # 0.20% para cobrir taxas completas de compra e venda
    trailing_atr_mult: float = float(os.getenv("TRAILING_ATR_MULT", "1.2"))  # Trailing stop segue com distância de 1.2 * ATR

    # Slippage
    slippage_max: float = 0.003  # 0.3% — alerta de HIGH_SLIPPAGE
    min_notional: float = 10.0   # Valor financeiro mínimo para ordem (BRL)

    # Intervalos dos loops
    fast_loop_interval: int = 10       # segundos
    slow_loop_interval: int = 1800     # 30 minutos em segundos
    heartbeat_interval: int = 300      # 5 minutos em segundos


@dataclass(frozen=True)
class ExchangeConfig:
    """Configurações da conexão com a Binance."""
    api_key: str = os.getenv("BINANCE_API_KEY", "")
    api_secret: str = os.getenv("BINANCE_API_SECRET", "")
    options: dict = field(default_factory=lambda: {
        "defaultType": "spot",
        "fetchMarkets": ["spot"],
        "adjustForTimeDifference": True,
        "recvWindow": 10000,
    })


@dataclass(frozen=True)
class DeepSeekConfig:
    """Configurações do auditor de entrada DeepSeek."""
    api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    model: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    api_url: str = os.getenv(
        "DEEPSEEK_API_URL", "https://api.deepseek.com/chat/completions"
    )
    timeout: float = float(os.getenv("DEEPSEEK_TIMEOUT", "15"))


@dataclass(frozen=True)
class SupabaseConfig:
    """Configurações do Supabase."""
    url: str = os.getenv("SUPABASE_URL", "")
    key: str = os.getenv("SUPABASE_KEY", "")
    schema: str = os.getenv("SUPABASE_SCHEMA", "trading_bot")


@dataclass(frozen=True)
class TelegramConfig:
    """Configurações do Telegram."""
    bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")


@dataclass(frozen=True)
class HealthcheckConfig:
    """Configurações do Healthcheck."""
    url: str = os.getenv("HEALTHCHECK_URL", "")


# Instâncias globais de configuração
trading = TradingConfig()
exchange = ExchangeConfig()
deepseek = DeepSeekConfig()
supabase = SupabaseConfig()
telegram = TelegramConfig()
healthcheck = HealthcheckConfig()

def is_live() -> bool:
    """Retorna True se o modo for LIVE (produção real)."""
    return trading.mode == "LIVE"

def is_paper() -> bool:
    """Retorna True se o modo for PAPER (simulação)."""
    return trading.mode == "PAPER"
