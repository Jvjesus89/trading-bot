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
    atr_1h_mediana: float = 0.0   # Mediana do ATR 1h (últimas 100h) — referência de "normal"


@dataclass
class ExecutionIndicators:
    """Indicadores do gráfico de 5m (referentes ao último candle FECHADO por padrão)."""
    bb_upper: float               # Banda Superior de Bollinger
    bb_middle: float              # Banda Média (SMA 20) — alvo da reversão à média
    bb_lower: float               # Banda Inferior de Bollinger
    rsi: float                    # RSI (14)
    atr: float                    # ATR (14)
    rvol: float                   # Volume Relativo (Volume / SMA Volume 20)
    current_close: float          # Preço de fechamento do candle de referência
    current_volume: float         # Volume do candle de referência
    candle_ts: int = 0            # Timestamp (ms) do candle de referência
    # Sinais (se EXIGIR_REVERSAO=true, BB/RSI/RVOL se referem ao candle de setup,
    # que é o anterior ao candle de reversão)
    price_at_or_below_bb_lower: bool = False
    rsi_oversold: bool = False
    volume_confirmed: bool = False
    reversao_confirmada: bool = True
    alvo_cobre_custo: bool = True
    distancia_alvo_pct: float = 0.0


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


def compute_signal_frame(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula todos os indicadores e sinais do 5m de forma vetorizada.
    Usado tanto pelo bot ao vivo quanto pelo backtest (mesma lógica nos dois).
    """
    cfg = config.trading
    close, open_, volume = df["close"], df["open"], df["volume"]

    bb_upper, bb_middle, bb_lower = compute_bollinger_bands(close, cfg.bb_period, cfg.bb_std)
    rsi = compute_rsi(close, cfg.rsi_period)
    atr = compute_atr(df, cfg.atr_period)
    rvol = compute_rvol(volume, cfg.rvol_period).fillna(0.0)

    touch = close <= bb_lower
    rsi_ok = rsi < cfg.rsi_threshold
    rvol_ok = rvol > cfg.rvol_threshold

    if cfg.exigir_reversao:
        # Setup no candle anterior, confirmação no candle atual
        touch = touch.shift(1).fillna(False).astype(bool)
        rsi_ok = rsi_ok.shift(1).fillna(False).astype(bool)
        rvol_ok = rvol_ok.shift(1).fillna(False).astype(bool)
        reversao = (close > open_) & (close > bb_lower)
    else:
        reversao = pd.Series(True, index=df.index)

    # Distância até o alvo e até o stop, em % do preço
    if cfg.alvo_na_media:
        dist_alvo = (bb_middle - close) / close
    else:
        dist_alvo = cfg.tp_atr_mult * atr / close
    dist_stop = cfg.sl_atr_mult * atr / close
    alvo_ok = (dist_alvo >= cfg.min_alvo_mult_custo * cfg.custo_ida_volta) & (
        dist_alvo >= cfg.min_rr * dist_stop
    )

    return pd.DataFrame({
        "open": open_, "high": df["high"], "low": df["low"], "close": close, "volume": volume,
        "bb_upper": bb_upper, "bb_middle": bb_middle, "bb_lower": bb_lower,
        "rsi": rsi, "atr": atr, "rvol": rvol,
        "bb_touch": touch, "rsi_ok": rsi_ok, "rvol_ok": rvol_ok,
        "reversao": reversao.astype(bool), "alvo_ok": alvo_ok.fillna(False).astype(bool),
        "dist_alvo": dist_alvo,
    }, index=df.index)


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
    atr_mediana = float(atr_series.iloc[-101:-1].median()) if len(atr_series) > 20 else 0.0

    return MacroIndicators(
        ema_200=ema_value,
        price_above_ema=current_close > ema_value,
        current_close=current_close,
        atr_1h=atr_value,
        atr_1h_mediana=atr_mediana,
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

    # O último candle retornado pela Binance ainda está em formação: RSI, banda e
    # volume dele mudam a cada segundo ("repintam"). Por padrão usamos só candles fechados.
    if config.trading.sinal_candle_fechado:
        df = df.iloc[:-1]
        if len(df) < min_required:
            return None

    f = compute_signal_frame(df)
    last = f.iloc[-1]

    def _num(v, default=0.0):
        return default if pd.isna(v) else float(v)

    return ExecutionIndicators(
        bb_upper=_num(last["bb_upper"]),
        bb_middle=_num(last["bb_middle"]),
        bb_lower=_num(last["bb_lower"]),
        rsi=_num(last["rsi"], 50.0),
        atr=_num(last["atr"]),
        rvol=_num(last["rvol"]),
        current_close=float(last["close"]),
        current_volume=float(last["volume"]),
        candle_ts=int(df.index[-1].value // 1_000_000),
        price_at_or_below_bb_lower=bool(last["bb_touch"]),
        rsi_oversold=bool(last["rsi_ok"]),
        volume_confirmed=bool(last["rvol_ok"]),
        reversao_confirmada=bool(last["reversao"]),
        alvo_cobre_custo=bool(last["alvo_ok"]),
        distancia_alvo_pct=_num(last["dist_alvo"]) * 100.0,
    )
