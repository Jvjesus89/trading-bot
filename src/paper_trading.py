"""
Paper Trading — Simulador local para testes sem risco real.
Emula a interface do ExchangeClient com dados reais da Binance (somente leitura)
e execuções fictícias locais.
"""

import logging
import time
from typing import Optional

import ccxt.async_support as ccxt

from . import config

logger = logging.getLogger(__name__)


class PaperTradingClient:
    """
    Simula a execução de ordens usando dados reais de mercado.
    - Dados de mercado (OHLCV, ticker, order book): lidos da Binance real
    - Ordens: executadas localmente com preço de mercado simulado
    - Saldo: rastreado internamente
    """

    def __init__(self):
        self._exchange: Optional[ccxt.binance] = None
        self._market_info: dict = {}
        self._balance: dict = {
            config.trading.quote_currency: config.trading.banca_inicial,
            config.trading.base_currency: 0.0,
        }
        self._trades: list[dict] = []

    async def connect(self) -> None:
        """Conecta à Binance em modo somente leitura (sem API keys)."""
        self._exchange = ccxt.binance({
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        })
        await self._exchange.load_markets()
        symbol = config.trading.symbol
        if symbol in self._exchange.markets:
            self._market_info = self._exchange.markets[symbol]
            logger.info(
                "[PAPER] Conectado à Binance (somente leitura) | Par: %s", symbol
            )
        else:
            raise RuntimeError(f"[PAPER] Par {symbol} não encontrado.")

    async def close(self) -> None:
        if self._exchange:
            await self._exchange.close()

    # ------------------------------------------------------------------
    # Dados de mercado (passthrough para Binance real)
    # ------------------------------------------------------------------

    async def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 250) -> list:
        return await self._exchange.fetch_ohlcv(symbol, timeframe, limit=limit)

    async def fetch_ticker(self, symbol: str) -> dict:
        return await self._exchange.fetch_ticker(symbol)

    async def fetch_order_book(self, symbol: str, limit: int = 20) -> dict:
        return await self._exchange.fetch_order_book(symbol, limit=limit)

    async def fetch_balance(self) -> dict:
        """Retorna o saldo simulado."""
        return {
            "free": dict(self._balance),
            "total": dict(self._balance),
            config.trading.quote_currency: {
                "free": self._balance[config.trading.quote_currency],
                "total": self._balance[config.trading.quote_currency],
            },
            config.trading.base_currency: {
                "free": self._balance[config.trading.base_currency],
                "total": self._balance[config.trading.base_currency],
            },
        }

    async def fetch_btc_variation_4h(self) -> float:
        btc_symbol = "BTC/BRL" if "BRL" in config.trading.symbol else "BTC/USDT"
        candles = await self.fetch_ohlcv(btc_symbol, "1h", limit=5)
        if len(candles) < 5:
            return 0.0
        open_4h = candles[0][1]
        close_now = candles[-1][4]
        return ((close_now - open_4h) / open_4h) * 100.0 if open_4h else 0.0

    # ------------------------------------------------------------------
    # Execução simulada
    # ------------------------------------------------------------------

    def amount_to_precision(self, symbol: str, amount: float) -> float:
        return float(self._exchange.amount_to_precision(symbol, amount))

    def price_to_precision(self, symbol: str, price: float) -> float:
        return float(self._exchange.price_to_precision(symbol, price))

    def validate_min_notional(self, amount: float, price: float) -> bool:
        return (amount * price) >= config.trading.min_notional

    async def create_market_buy(self, symbol: str, amount: float) -> dict:
        """Simula uma compra a mercado usando o preço bid do order book."""
        amount = self.amount_to_precision(symbol, amount)
        ticker = await self._exchange.fetch_ticker(symbol)
        price = ticker.get("ask", ticker.get("last", 0))

        cost = amount * price
        quote = config.trading.quote_currency
        base = config.trading.base_currency

        if self._balance[quote] < cost:
            logger.error("[PAPER] Saldo insuficiente: R$ %.2f < R$ %.2f", self._balance[quote], cost)
            raise RuntimeError("Saldo insuficiente para compra simulada")

        self._balance[quote] -= cost
        self._balance[base] += amount

        trade = {
            "id": f"paper_{int(time.time())}",
            "side": "buy",
            "filled": amount,
            "average_price": price,
            "cost": cost,
            "timestamp": time.time(),
        }
        self._trades.append(trade)

        logger.info(
            "[PAPER] 🟢 COMPRA simulada | %s | Qtd: %.6f | Preço: R$ %.4f | Custo: R$ %.2f | Saldo: R$ %.2f",
            symbol, amount, price, cost, self._balance[quote]
        )

        return {
            "id": trade["id"],
            "filled": amount,
            "average_price": price,
            "cost": cost,
            "raw": trade,
        }

    async def create_market_sell(self, symbol: str, amount: float) -> dict:
        """Simula uma venda a mercado usando o preço bid do order book."""
        amount = self.amount_to_precision(symbol, amount)
        ticker = await self._exchange.fetch_ticker(symbol)
        price = ticker.get("bid", ticker.get("last", 0))

        revenue = amount * price
        quote = config.trading.quote_currency
        base = config.trading.base_currency

        if self._balance[base] < amount:
            logger.error("[PAPER] Saldo insuficiente: %.6f < %.6f %s", self._balance[base], amount, base)
            raise RuntimeError("Saldo insuficiente para venda simulada")

        self._balance[base] -= amount
        self._balance[quote] += revenue

        trade = {
            "id": f"paper_{int(time.time())}",
            "side": "sell",
            "filled": amount,
            "average_price": price,
            "cost": revenue,
            "timestamp": time.time(),
        }
        self._trades.append(trade)

        logger.info(
            "[PAPER] 🔴 VENDA simulada | %s | Qtd: %.6f | Preço: R$ %.4f | Receita: R$ %.2f | Saldo: R$ %.2f",
            symbol, amount, price, revenue, self._balance[quote]
        )

        return {
            "id": trade["id"],
            "filled": amount,
            "average_price": price,
            "cost": revenue,
            "raw": trade,
        }

    def get_balance_summary(self) -> dict:
        """Retorna resumo do saldo simulado."""
        return {
            "quote": round(self._balance[config.trading.quote_currency], 2),
            "base": round(self._balance[config.trading.base_currency], 6),
            "trades_count": len(self._trades),
        }
