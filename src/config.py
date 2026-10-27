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
    rsi_threshold: float = 32.0  # RSI abaixo de 32 = sobrevenda
    rvol_threshold: float = 1.0  # RVOL acima de 1.0 = liquidez confirmada

    # Gestão de saída dinâmica (multiplicadores ATR)
    sl_atr_mult: float = 1.5     # Stop Loss = Entrada - 1.5 * ATR
    tp_atr_mult: float = 2.0     # Take Profit = Entrada + 2.0 * ATR
    be_atr_mult: float = 1.0     # Breakeven ativa quando lucro >= 1.0 * ATR
    be_fee_offset: float = 0.0015  # 0.15% para cobrir taxas no breakeven
    trailing_atr_mult: float = 1.0  # Trailing stop segue com distância de 1.0 * ATR

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
        "adjustForTimeDifference": True,
        "recvWindow": 10000,
    })


@dataclass(frozen=True)
class GeminiConfig:
    """Configurações da integração com Gemini Flash."""
    api_key: str = os.getenv("GEMINI_API_KEY", "")
    model: str = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")


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
gemini = GeminiConfig()
supabase = SupabaseConfig()
telegram = TelegramConfig()
healthcheck = HealthcheckConfig()

def is_live() -> bool:
    """Retorna True se o modo for LIVE (produção real)."""
    return trading.mode == "LIVE"

def is_paper() -> bool:
    """Retorna True se o modo for PAPER (simulação)."""
    return trading.mode == "PAPER"
