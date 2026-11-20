"""
Funding rate de futuros perpétuos — métrica macro isolada.

O par operado é spot (ex.: SOL/BRL), que não tem funding rate. A métrica
relevante para risco sistêmico é a do perpétuo em USDT (ex.: SOL/USDT:USDT).

Este módulo é deliberadamente tolerante a falhas: qualquer erro (rede, DNS,
par indisponível, região bloqueada) resulta em None, nunca em exceção, para
não derrubar o slow loop. O chamador decide o que fazer com a ausência.
"""

import logging
import time
from typing import Optional

import ccxt.async_support as ccxt

logger = logging.getLogger(__name__)

# Reaproveita o valor por 5 min (o slow loop roda a cada 30 min)
_CACHE_TTL = 300.0
_TIMEOUT_MS = 10_000

_exchange = None  # type: Optional[ccxt.binanceusdm]
_markets_loaded: bool = False
_last_fetch: float = 0.0
_last_value: Optional[float] = None


def _perp_symbol(spot_symbol: str) -> str:
    """Mapeia 'SOL/BRL' -> 'SOL/USDT:USDT' (perpétuo linear em USDT)."""
    base = spot_symbol.split("/")[0].strip().upper()
    return f"{base}/USDT:USDT"


def reset_funding_cache() -> None:
    """Limpa o cache (útil em testes ou após troca de par)."""
    global _last_fetch, _last_value
    _last_fetch = 0.0
    _last_value = None


async def fetch_funding_rate(spot_symbol: str) -> Optional[float]:
    """
    Retorna o funding rate atual do perpétuo correspondente, em porcentagem
    (ex.: 0.0100 = 0.01%), ou None se indisponível.
    """
    global _exchange, _markets_loaded, _last_fetch, _last_value

    now = time.time()
    if _last_value is not None and (now - _last_fetch) < _CACHE_TTL:
        return _last_value

    try:
        if _exchange is None:
            _exchange = ccxt.binanceusdm(
                {"enableRateLimit": True, "timeout": _TIMEOUT_MS}
            )
        if not _markets_loaded:
            await _exchange.load_markets()
            _markets_loaded = True

        perp = _perp_symbol(spot_symbol)
        if perp not in _exchange.markets:
            logger.warning(
                "[FUNDING] Perpétuo %s não listado na Binance Futures.", perp
            )
            return None

        data = await _exchange.fetch_funding_rate(perp)
        rate = data.get("fundingRate") if isinstance(data, dict) else None
        if rate is None:
            logger.warning("[FUNDING] Resposta sem fundingRate para %s.", perp)
            return None

        _last_value = float(rate) * 100.0  # decimal -> %
        _last_fetch = now
        return _last_value

    except Exception as e:  # rede, DNS, geo-block, par inexistente...
        logger.warning("[FUNDING] Falha ao obter funding de %s: %s", spot_symbol, e)
        reset_funding_cache()
        return None


async def close_funding_exchange() -> None:
    """Fecha o cliente de futuros no shutdown (evita socket pendurado)."""
    global _exchange, _markets_loaded
    if _exchange is not None:
        try:
            await _exchange.close()
        except Exception as e:  # pragma: no cover - shutdown best-effort
            logger.debug("[FUNDING] Erro ao fechar cliente: %s", e)
        finally:
            _exchange = None
            _markets_loaded = False
