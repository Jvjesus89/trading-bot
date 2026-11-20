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
    # Breakeven: stop vai para entrada + custo de ida e volta (antes era 0.15%,
    # que NÃO cobria 0.2% de taxas + spread — todo "breakeven" fechava no prejuízo)
    be_fee_offset: float = float(os.getenv("BE_OFFSET_PCT", "0.30")) / 100.0
    # O breakeven só ativa depois que o lucro flutuante passar de N x custo
    be_min_mult_custo: float = float(os.getenv("BE_MIN_MULT_CUSTO", "2.0"))
    # Trailing após atingir o alvo (média de Bollinger): distância de 0.5 * ATR
    trailing_atr_mult: float = float(os.getenv("TRAILING_ATR_MULT", "0.5"))

    # --- Custos reais de execução ---
    taxa_por_lado: float = float(os.getenv("TAXA_POR_LADO_PCT", "0.10")) / 100.0
    # Custo total estimado ida+volta: taxas (2 x 0.10%) + spread médio do SOL/BRL
    custo_ida_volta: float = float(os.getenv("CUSTO_IDA_VOLTA_PCT", "0.30")) / 100.0

    # --- Filtros de qualidade do sinal (v2) ---
    # Sinais só em candles 5m FECHADOS (antes: candle em formação, que "repinta")
    sinal_candle_fechado: bool = os.getenv("SINAL_CANDLE_FECHADO", "true").lower() == "true"
    # Exige candle de reversão: candle anterior fez o setup e o último fechou verde
    # e de volta acima da banda inferior (evita "pegar faca caindo")
    exigir_reversao: bool = os.getenv("EXIGIR_REVERSAO", "true").lower() == "true"
    # Alvo = banda média de Bollinger (o "retorno à média" da estratégia)
    alvo_na_media: bool = os.getenv("ALVO_NA_MEDIA", "true").lower() == "true"
    # Só entra se a distância até o alvo for >= N x custo de ida e volta
    min_alvo_mult_custo: float = float(os.getenv("MIN_ALVO_MULT_CUSTO", "2.0"))
    # Só entra se (distância até o alvo) >= MIN_RR x (distância até o stop)
    min_rr: float = float(os.getenv("MIN_RR", "0.8"))

    # --- Filtro macro (substitui a chamada ao Gemini por regras determinísticas) ---
    usar_ia: bool = os.getenv("USAR_IA", "false").lower() == "true"
    btc_queda_max_4h: float = float(os.getenv("BTC_QUEDA_MAX_4H_PCT", "-3.0"))
    atr_choque_mult: float = float(os.getenv("ATR_CHOQUE_MULT", "3.0"))

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
    model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


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
