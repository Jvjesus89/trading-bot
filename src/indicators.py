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
    atr_1h_mediana: float = 0.0   # Mediana do ATR 1h (últimas 100h) — volatilidade "normal"


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
    current_open: float           # Preço de abertura do último candle 5m
    current_high: float           # Máxima do último candle 5m
    current_low: float            # Mínima do último candle 5m
    current_volume: float         # Volume do último candle 5m
    candle_ts: int = 0            # Timestamp (ms) do candle de referência
    # Com EXIGIR_REVERSAO=true, os sinais de banda/RSI/RVOL vêm do candle ANTERIOR
    # (setup) e o candle atual precisa ser o de reversão. None = usa o próprio candle.
    setup_bb: Optional[bool] = None
    setup_rsi: Optional[bool] = None
    setup_rvol: Optional[bool] = None
    distancia_alvo_pct: float = 0.0   # Distância até o alvo, em % do preço
    alvo_cobre_custo: bool = True     # Alvo paga custos (MIN_ALVO_MULT_CUSTO) e risco (MIN_RR)

    @property
    def is_green_candle(self) -> bool:
        """Indica se o candle atual é de alta (compradores dominando o candle)."""
        return self.current_close > self.current_open

    @property
    def price_at_or_below_bb_lower(self) -> bool:
        """Preço de fechamento tocou ou rompeu a Banda Inferior."""
        return self.current_close <= self.bb_lower

    @property
    def price_tested_bb_lower(self) -> bool:
        """Toque na Banda Inferior (pela mínima ou pelo fechamento, conforme TOQUE_PELA_MINIMA)."""
        if self.setup_bb is not None:
            return self.setup_bb
        return toque_banda(self.current_low, self.current_close, self.bb_lower)

    @property
    def rsi_oversold(self) -> bool:
        """RSI abaixo do limiar de sobrevenda (configurável, default 32)."""
        if self.setup_rsi is not None:
            return self.setup_rsi
        return self.rsi < config.trading.rsi_threshold

    @property
    def volume_confirmed(self) -> bool:
        """Volume relativo acima do limiar (configurável, default 1.0)."""
        if self.setup_rvol is not None:
            return self.setup_rvol
        return self.rvol > config.trading.rvol_threshold

    @property
    def reversao_confirmada(self) -> bool:
        """Candle de reversão: fechou verde e de volta acima da banda inferior."""
        return self.is_green_candle and self.current_close > self.bb_lower


def toque_banda(low: float, close: float, bb_lower: float) -> bool:
    """Regra de toque na Banda Inferior (compartilhada pelo bot e pelo backtest)."""
    if config.trading.toque_pela_minima:
        return low <= bb_lower or close <= bb_lower * 1.002
    return close <= bb_lower


def avaliar_alvo(close: float, atr: float, bb_middle: float) -> tuple[float, bool]:
    """
    Distância até o alvo (fração do preço) e se ela compensa custos e risco.
    Mesmas regras que Strategy.open_position usa para montar SL/TP.
    """
    cfg = config.trading
    if close <= 0 or not np.isfinite(atr):
        return 0.0, False
    dist_stop = max(cfg.sl_atr_mult * atr / close, cfg.sl_min_pct)
    if cfg.alvo_na_media:
        dist_alvo = (bb_middle - close) / close if np.isfinite(bb_middle) else 0.0
    else:
        dist_alvo = max(cfg.tp_atr_mult * atr / close, cfg.tp_min_pct)
    ok = dist_alvo >= cfg.min_alvo_mult_custo * cfg.custo_ida_volta and dist_alvo >= cfg.min_rr * dist_stop
    return dist_alvo, bool(ok)


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

    # O último candle da Binance ainda está em formação e "repinta".
    if config.trading.sinal_candle_fechado:
        df = df.iloc[:-1]
        if len(df) < min_required:
            return None

    series = compute_series_5m(df)
    return build_execution(series, len(df) - 1)


def compute_series_5m(df: pd.DataFrame) -> dict:
    """Calcula todas as séries do 5m de uma vez (usado pelo bot e pelo backtest)."""
    cfg = config.trading
    close = df["close"]
    bb_upper, bb_middle, bb_lower = compute_bollinger_bands(close, cfg.bb_period, cfg.bb_std)
    return {
        "ts": (df.index.asi8 // 1_000_000).astype(np.int64),
        "open": df["open"].to_numpy(float),
        "high": df["high"].to_numpy(float),
        "low": df["low"].to_numpy(float),
        "close": close.to_numpy(float),
        "volume": df["volume"].to_numpy(float),
        "bb_upper": bb_upper.to_numpy(float),
        "bb_middle": bb_middle.to_numpy(float),
        "bb_lower": bb_lower.to_numpy(float),
        "rsi": compute_rsi(close, cfg.rsi_period).fillna(50.0).to_numpy(float),
        "atr": compute_atr(df, cfg.atr_period).to_numpy(float),
        "rvol": compute_rvol(df["volume"], cfg.rvol_period).fillna(0.0).to_numpy(float),
    }


def build_execution(s: dict, i: int) -> ExecutionIndicators:
    """Monta os indicadores de execução do candle i (mesma regra ao vivo e no backtest)."""
    cfg = config.trading
    setup_bb = setup_rsi = setup_rvol = None
    if cfg.exigir_reversao and i >= 1:
        j = i - 1
        setup_bb = toque_banda(s["low"][j], s["close"][j], s["bb_lower"][j])
        setup_rsi = bool(s["rsi"][j] < cfg.rsi_threshold)
        setup_rvol = bool(s["rvol"][j] > cfg.rvol_threshold)

    dist_alvo, alvo_ok = avaliar_alvo(s["close"][i], s["atr"][i], s["bb_middle"][i])

    return ExecutionIndicators(
        bb_upper=float(s["bb_upper"][i]),
        bb_middle=float(s["bb_middle"][i]),
        bb_lower=float(s["bb_lower"][i]),
        rsi=float(s["rsi"][i]),
        atr=float(s["atr"][i]),
        rvol=float(s["rvol"][i]),
        current_close=float(s["close"][i]),
        current_open=float(s["open"][i]),
        current_high=float(s["high"][i]),
        current_low=float(s["low"][i]),
        current_volume=float(s["volume"][i]),
        candle_ts=int(s["ts"][i]),
        setup_bb=setup_bb,
        setup_rsi=setup_rsi,
        setup_rvol=setup_rvol,
        distancia_alvo_pct=dist_alvo * 100.0,
        alvo_cobre_custo=alvo_ok,
    )
