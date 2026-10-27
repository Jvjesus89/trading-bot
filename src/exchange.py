"""
Abstração da conexão com a Binance via CCXT.
Gerencia ordens, balances, order book e market info com retry exponencial.
"""

import asyncio
import logging
import time
from typing import Optional

import ccxt.async_support as ccxt

from . import config

logger = logging.getLogger(__name__)


class ExchangeError(Exception):
    """Erro genérico da exchange."""
    pass


class ExchangeClient:
    """
    Wrapper assíncrono sobre o CCXT para a Binance Spot.
    Implementa backoff exponencial e validação de lote/nocional.
    """

    def __init__(self):
        self._exchange: Optional[ccxt.binance] = None
        self._market_info: dict = {}
        self._max_retries = 5
        self._base_delay = 2.0  # segundos

    async def connect(self) -> None:
        """Inicializa a conexão com a Binance."""
        cfg = config.exchange
        self._exchange = ccxt.binance({
            "apiKey": cfg.api_key,
            "secret": cfg.api_secret,
            "enableRateLimit": True,
            "options": cfg.options,
        })
        # Carrega informações de mercado para validação de lote
        await self._exchange.load_markets()
        symbol = config.trading.symbol
        if symbol in self._exchange.markets:
            self._market_info = self._exchange.markets[symbol]
            logger.info(
                "Conectado à Binance | Par: %s | Precisão: amount=%s price=%s",
                symbol,
                self._market_info.get("precision", {}).get("amount"),
                self._market_info.get("precision", {}).get("price"),
            )
        else:
            raise ExchangeError(f"Par {symbol} não encontrado na Binance.")

    async def close(self) -> None:
        """Encerra a conexão."""
        if self._exchange:
            await self._exchange.close()
            logger.info("Conexão com a Binance encerrada.")

    async def _retry(self, coro_factory, operation_name: str):
        """
        Executa uma operação com backoff exponencial.
        Trata HTTP 429 (rate limit) e 500 (server error).
        Retries: 2s, 4s, 8s, 16s, 32s
        """
        for attempt in range(self._max_retries):
            try:
                return await coro_factory()
            except (ccxt.RateLimitExceeded, ccxt.ExchangeNotAvailable, ccxt.RequestTimeout) as e:
                delay = self._base_delay * (2 ** attempt)
                logger.warning(
                    "[%s] Tentativa %d/%d falhou: %s | Retry em %.1fs",
                    operation_name, attempt + 1, self._max_retries, type(e).__name__, delay
                )
                await asyncio.sleep(delay)
            except ccxt.ExchangeError as e:
                logger.error("[%s] Erro irrecuperável da exchange: %s", operation_name, e)
                raise ExchangeError(str(e)) from e
        raise ExchangeError(f"[{operation_name}] Falhou após {self._max_retries} tentativas.")

    # ------------------------------------------------------------------
    # Dados de mercado
    # ------------------------------------------------------------------

    async def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 250) -> list:
        """Busca candles OHLCV."""
        return await self._retry(
            lambda: self._exchange.fetch_ohlcv(symbol, timeframe, limit=limit),
            f"fetch_ohlcv({symbol},{timeframe})"
        )

    async def fetch_ticker(self, symbol: str) -> dict:
        """Busca ticker atual."""
        return await self._retry(
            lambda: self._exchange.fetch_ticker(symbol),
            f"fetch_ticker({symbol})"
        )

    async def fetch_order_book(self, symbol: str, limit: int = 20) -> dict:
        """Busca order book."""
        return await self._retry(
            lambda: self._exchange.fetch_order_book(symbol, limit=limit),
            f"fetch_order_book({symbol})"
        )

    async def fetch_balance(self) -> dict:
        """Busca saldo da conta."""
        return await self._retry(
            lambda: self._exchange.fetch_balance(),
            "fetch_balance"
        )

    async def fetch_btc_variation_4h(self) -> float:
        """
        Calcula a variação percentual do BTC nas últimas 4h.
        Usado como input para a IA.
        """
        btc_symbol = "BTC/BRL" if "BRL" in config.trading.symbol else "BTC/USDT"
        candles = await self.fetch_ohlcv(btc_symbol, "1h", limit=5)
        if len(candles) < 5:
            return 0.0
        open_4h_ago = candles[0][1]  # open do candle mais antigo
        close_now = candles[-1][4]   # close do candle mais recente
        if open_4h_ago == 0:
            return 0.0
        return ((close_now - open_4h_ago) / open_4h_ago) * 100.0

    # ------------------------------------------------------------------
    # Execução de ordens
    # ------------------------------------------------------------------

    def amount_to_precision(self, symbol: str, amount: float) -> float:
        """Trunca a quantidade para a precisão aceita pela exchange."""
        return float(self._exchange.amount_to_precision(symbol, amount))

    def price_to_precision(self, symbol: str, price: float) -> float:
        """Trunca o preço para a precisão aceita pela exchange."""
        return float(self._exchange.price_to_precision(symbol, price))

    def validate_min_notional(self, amount: float, price: float) -> bool:
        """
        Verifica se o valor da ordem atinge o nocional mínimo.
        Binance exige mínimo de ~R$10 ou 5 USDT.
        """
        notional = amount * price
        return notional >= config.trading.min_notional

    async def create_market_buy(self, symbol: str, amount: float) -> dict:
        """
        Envia ordem de compra a mercado.
        Retorna a ordem com preço médio e quantidade preenchida.
        """
        amount = self.amount_to_precision(symbol, amount)
        logger.info("[ORDER] Enviando COMPRA a mercado: %s | Qtd: %s", symbol, amount)

        order = await self._retry(
            lambda: self._exchange.create_market_buy_order(symbol, amount),
            f"market_buy({symbol})"
        )

        filled = order.get("filled", amount)
        avg_price = order.get("average", order.get("price", 0))

        logger.info(
            "[ORDER] COMPRA executada | Preenchido: %s | Preço Médio: %s",
            filled, avg_price
        )
        return {
            "id": order.get("id"),
            "filled": filled,
            "average_price": avg_price,
            "cost": order.get("cost", filled * avg_price),
            "raw": order,
        }

    async def create_market_sell(self, symbol: str, amount: float) -> dict:
        """
        Envia ordem de venda a mercado.
        Retorna a ordem com preço médio e quantidade preenchida.
        """
        amount = self.amount_to_precision(symbol, amount)
        logger.info("[ORDER] Enviando VENDA a mercado: %s | Qtd: %s", symbol, amount)

        order = await self._retry(
            lambda: self._exchange.create_market_sell_order(symbol, amount),
            f"market_sell({symbol})"
        )

        filled = order.get("filled", amount)
        avg_price = order.get("average", order.get("price", 0))

        logger.info(
            "[ORDER] VENDA executada | Preenchido: %s | Preço Médio: %s",
            filled, avg_price
        )
        return {
            "id": order.get("id"),
            "filled": filled,
            "average_price": avg_price,
            "cost": order.get("cost", filled * avg_price),
            "raw": order,
        }
