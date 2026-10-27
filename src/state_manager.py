"""
State Manager — Máquina de estados e crash recovery (bootstrap_state).
Reconcilia posições entre o banco de dados e a exchange após reinícios.
"""

import logging
import time
from typing import Optional

from . import config
from .strategy import Position, StopState

logger = logging.getLogger(__name__)


class StateManager:
    """
    Gerencia a reconciliação de estado após crash/reinício.
    
    Fluxo de Bootstrap:
    1. Consulta Supabase: busca último trade com timestamp_out IS NULL
    2. Consulta Exchange: verifica saldo da moeda-alvo
    3. Reconcilia: restaura posição ou marca como ORPHAN_RECOVERY
    """

    def __init__(self, exchange_client, persistence, strategy):
        self._exchange = exchange_client
        self._persistence = persistence
        self._strategy = strategy

    async def bootstrap_state(self) -> Optional[str]:
        """
        Executa a rotina de reconciliação de estado ao iniciar.
        
        Returns:
            - "RESTORED": Posição restaurada com sucesso
            - "ORPHAN_RECOVERED": Posição órfã detectada e fechada
            - "CLEAN": Nenhuma posição pendente, estado limpo
            - None: Erro no bootstrap
        """
        symbol = config.trading.symbol
        base = config.trading.base_currency
        logger.info("[BOOTSTRAP] Iniciando reconciliação de estado para %s...", symbol)

        # 1. Busca trade aberto no banco
        open_trade = await self._persistence.get_open_trade(symbol)

        if open_trade is None:
            logger.info("[BOOTSTRAP] Nenhum trade aberto encontrado. Estado limpo.")
            return "CLEAN"

        logger.info(
            "[BOOTSTRAP] Trade aberto encontrado | Entrada: R$ %s | Qtd: %s",
            open_trade.get("preco_entrada"), open_trade.get("quantidade")
        )

        # 2. Verifica saldo real na exchange
        try:
            balance = await self._exchange.fetch_balance()
            saldo_base = float(balance.get(base, {}).get("free", 0) or 0)
        except Exception as e:
            logger.error("[BOOTSTRAP] Erro ao consultar saldo: %s", e)
            return None

        quantidade_db = float(open_trade.get("quantidade", 0))
        preco_entrada = float(open_trade.get("preco_entrada", 0))
        trade_id = open_trade.get("id", "")

        # 3. Reconciliação
        # Tolerância de 5% para diferenças de arredondamento
        tolerancia = quantidade_db * 0.05

        if abs(saldo_base - quantidade_db) <= tolerancia and saldo_base > 0:
            # Dados batem — restaura posição
            logger.info(
                "[BOOTSTRAP] ✅ Saldo confere (DB: %.6f | Exchange: %.6f). Restaurando posição.",
                quantidade_db, saldo_base
            )

            # Busca ATR atual para recalcular stops
            try:
                ohlcv_5m = await self._exchange.fetch_ohlcv(symbol, "5m", limit=50)
                from .indicators import calculate_execution_indicators
                exec_indicators = calculate_execution_indicators(ohlcv_5m)
                atr = exec_indicators.atr if exec_indicators else preco_entrada * 0.01
            except Exception:
                # Fallback: estima ATR como 1% do preço
                atr = preco_entrada * 0.01

            position = Position(
                symbol=symbol,
                preco_entrada=preco_entrada,
                quantidade=saldo_base,  # Usa saldo real da exchange
                atr_entrada=atr,
                timestamp_in=time.time(),
                stop_loss=preco_entrada - (config.trading.sl_atr_mult * atr),
                take_profit=preco_entrada + (config.trading.tp_atr_mult * atr),
                ia_snapshot=open_trade.get("ia_snapshot"),
            )

            self._strategy.restore_position(position)
            # Armazena trade_id para posterior atualização
            self._current_trade_id = trade_id
            return "RESTORED"

        else:
            # Divergência — posição órfã
            logger.warning(
                "[BOOTSTRAP] ⚠️ DIVERGÊNCIA | DB: %.6f | Exchange: %.6f | "
                "Registrando como ORPHAN_RECOVERY",
                quantidade_db, saldo_base
            )

            # Tenta obter preço atual para calcular PnL aproximado
            try:
                ticker = await self._exchange.fetch_ticker(symbol)
                preco_atual = ticker.get("last", preco_entrada)
            except Exception:
                preco_atual = preco_entrada

            # Fecha o trade no banco como órfão
            await self._persistence.record_exit(
                trade_id=trade_id,
                preco_saida=preco_atual,
                quantidade=quantidade_db,
                motivo_saida="ORPHAN_RECOVERY",
            )

            return "ORPHAN_RECOVERED"

    @property
    def current_trade_id(self) -> Optional[str]:
        """Retorna o ID do trade restaurado, se houver."""
        return getattr(self, "_current_trade_id", None)

    @current_trade_id.setter
    def current_trade_id(self, value: str) -> None:
        self._current_trade_id = value
