"""
Cálculo de indicadores técnicos para os gráficos de 1h (macro) e 5m (execução).
Utiliza pandas para performance e ta (Technical Analysis library) quando conveniente.
"""

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from . import config

logger = logging.getLogger(__name__)


@dataclass
class MacroIndicators:
    """Indicadores do gráfico de 1h."""
    ema_200: float                # EMA 200 do timeframe 1h
    price_above_ema: bool         # Preço de fechamento > EMA 200
    current_close: float          # Preço de fechamento do último candle 1h
    atr_1h: float                 # ATR 14 do 1h (para payload da IA)


@dataclass
class ExecutionIndicators:
    """Indicadores do gráfico de 5m."""
    bb_upper: float               # Banda Superior de Bollinger
    bb_middle: float              # Banda Média (SMA 20)
    bb_lower: float               # Banda Inferior de Bollinger
    rsi: float                    # RSI (14)
    atr: float                    # ATR (14)
    rvol: float                   # Volume Relativo (Volume / SMA Volume 20)
    current_close: float          # Preço de fechamento do último candle 5m
    current_volume: float         # Volume do último candle 5m

    @property
    def price_at_or_below_bb_lower(self) -> bool:
        """Preço tocou ou rompeu a Banda Inferior."""
        return self.current_close <= self.bb_lower

    @property
    def rsi_oversold(self) -> bool:
        """RSI abaixo do limiar de sobrevenda (32)."""
        return self.rsi < config.trading.rsi_threshold

    @property
    def volume_confirmed(self) -> bool:
        """Volume relativo acima do limiar (1.0)."""
        return self.rvol > config.trading.rvol_threshold


def _to_dataframe(ohlcv: list) -> pd.DataFrame:
    """Converte lista OHLCV do CCXT para DataFrame."""
    df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df.set_index("timestamp", inplace=True)
    return df


def compute_ema(series: pd.Series, period: int) -> pd.Series:
    """Calcula a Média Móvel Exponencial."""
    return series.ewm(span=period, adjust=False).mean()


def compute_bollinger_bands(series: pd.Series, period: int, std_dev: float):
    """
    Calcula as Bandas de Bollinger.
    Retorna (upper, middle, lower) como tupla de floats do último valor.
    """
    sma = series.rolling(window=period).mean()
    rolling_std = series.rolling(window=period).std()
    upper = sma + (rolling_std * std_dev)
    lower = sma - (rolling_std * std_dev)
    return upper, sma, lower


def compute_rsi(series: pd.Series, period: int) -> pd.Series:
    """
    Calcula o RSI (Relative Strength Index).
    Usa média móvel exponencial dos ganhos e perdas.
    """
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)

    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi


def compute_atr(df: pd.DataFrame, period: int) -> pd.Series:
    """
    Calcula o ATR (Average True Range).
    Mede a volatilidade real do ativo em unidades de preço.
    """
    high = df["high"]
    low = df["low"]
    close = df["close"]

    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = true_range.ewm(span=period, adjust=False).mean()
    return atr


def compute_rvol(volume: pd.Series, period: int) -> pd.Series:
    """
    Calcula o Volume Relativo.
    RVOL = Volume atual / Média de Volume dos últimos N períodos.
    """
    vol_sma = volume.rolling(window=period).mean()
    return volume / vol_sma.replace(0, np.nan)


def calculate_macro_indicators(ohlcv_1h: list) -> Optional[MacroIndicators]:
    """
    Calcula indicadores do gráfico de 1h.
    Requer pelo menos 201 candles para a EMA 200.
    """
    if len(ohlcv_1h) < config.trading.ema_period + 1:
        logger.warning(
            "Dados insuficientes para EMA %d (recebidos: %d candles 1h)",
            config.trading.ema_period, len(ohlcv_1h)
        )
        return None

    df = _to_dataframe(ohlcv_1h)
    ema_series = compute_ema(df["close"], config.trading.ema_period)
    atr_series = compute_atr(df, config.trading.atr_period)

    current_close = float(df["close"].iloc[-1])
    ema_value = float(ema_series.iloc[-1])
    atr_value = float(atr_series.iloc[-1])

    return MacroIndicators(
        ema_200=ema_value,
        price_above_ema=current_close > ema_value,
        current_close=current_close,
        atr_1h=atr_value,
    )


def calculate_execution_indicators(ohlcv_5m: list) -> Optional[ExecutionIndicators]:
    """
    Calcula indicadores do gráfico de 5m.
    Requer pelo menos 21 candles para Bollinger Bands.
    """
    min_required = max(config.trading.bb_period, config.trading.rsi_period, config.trading.atr_period) + 1
    if len(ohlcv_5m) < min_required:
        logger.warning(
            "Dados insuficientes para indicadores 5m (recebidos: %d candles, mínimo: %d)",
            len(ohlcv_5m), min_required
        )
        return None

    df = _to_dataframe(ohlcv_5m)
    close = df["close"]
    volume = df["volume"]

    # Bollinger Bands
    bb_upper, bb_middle, bb_lower = compute_bollinger_bands(
        close, config.trading.bb_period, config.trading.bb_std
    )

    # RSI
    rsi_series = compute_rsi(close, config.trading.rsi_period)

    # ATR
    atr_series = compute_atr(df, config.trading.atr_period)

    # RVOL
    rvol_series = compute_rvol(volume, config.trading.rvol_period)

    return ExecutionIndicators(
        bb_upper=float(bb_upper.iloc[-1]),
        bb_middle=float(bb_middle.iloc[-1]),
        bb_lower=float(bb_lower.iloc[-1]),
        rsi=float(rsi_series.iloc[-1]),
        atr=float(atr_series.iloc[-1]),
        rvol=float(rvol_series.iloc[-1]) if not pd.isna(rvol_series.iloc[-1]) else 0.0,
        current_close=float(close.iloc[-1]),
        current_volume=float(volume.iloc[-1]),
    )
