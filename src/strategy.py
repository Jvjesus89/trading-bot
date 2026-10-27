"""
Lógica da Estratégia — Reversão à Média a Favor da Tendência Primária.
Coordena os gatilhos de entrada e a gestão de saída dinâmica (ATR-based).
"""

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from . import config
from .indicators import MacroIndicators, ExecutionIndicators

logger = logging.getLogger(__name__)


class ExitReason(str, Enum):
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"
    BREAKEVEN = "BREAKEVEN"
    TRAILING = "TRAILING"


class StopState(str, Enum):
    """Estado do stop dinâmico."""
    INITIAL = "INITIAL"          # Stop Loss fixo inicial
    BREAKEVEN = "BREAKEVEN"      # Stop movido para breakeven
    TRAILING = "TRAILING"        # Trailing stop ativo


@dataclass
class Position:
    """Representa uma posição aberta."""
    symbol: str
    preco_entrada: float
    quantidade: float
    atr_entrada: float           # ATR no momento da entrada
    timestamp_in: float
    stop_loss: float             # Stop Loss dinâmico
    take_profit: float           # Take Profit (alvo)
    stop_state: StopState = StopState.INITIAL
    highest_price: float = 0.0   # Maior preço atingido (para trailing)
    ia_snapshot: Optional[dict] = None

    @property
    def custo_total(self) -> float:
        return self.preco_entrada * self.quantidade

    def update_dynamic_stops(self, current_price: float) -> Optional[ExitReason]:
        """
        Atualiza os stops dinâmicos com base no preço atual.
        Retorna o ExitReason se uma saída deve ser executada, ou None.
        """
        cfg = config.trading

        # Atualiza o preço máximo atingido
        if current_price > self.highest_price:
            self.highest_price = current_price

        # --- CHECK 1: Stop Loss atingido ---
        if current_price <= self.stop_loss:
            if self.stop_state == StopState.BREAKEVEN:
                return ExitReason.BREAKEVEN
            elif self.stop_state == StopState.TRAILING:
                return ExitReason.TRAILING
            else:
                return ExitReason.STOP_LOSS

        # --- CHECK 2: Promoção para Breakeven ---
        lucro_flutuante = current_price - self.preco_entrada
        breakeven_trigger = cfg.be_atr_mult * self.atr_entrada

        if self.stop_state == StopState.INITIAL and lucro_flutuante >= breakeven_trigger:
            # Move stop para Preço de Entrada + 0.15% (cobrindo taxas)
            novo_stop = self.preco_entrada * (1 + cfg.be_fee_offset)
            self.stop_loss = novo_stop
            self.stop_state = StopState.BREAKEVEN
            logger.info(
                "[STRATEGY] 🛡️ Breakeven ativado | Novo SL: R$ %.4f (entrada + taxas)",
                novo_stop
            )

        # --- CHECK 3: Promoção para Trailing Stop ---
        if current_price >= self.take_profit:
            # Não executa TP imediatamente — ativa trailing
            trailing_stop = self.highest_price - (cfg.trailing_atr_mult * self.atr_entrada)

            if trailing_stop > self.stop_loss:
                self.stop_loss = trailing_stop
                self.stop_state = StopState.TRAILING
                logger.info(
                    "[STRATEGY] 📈 Trailing Stop atualizado | SL: R$ %.4f | High: R$ %.4f",
                    trailing_stop, self.highest_price
                )

        return None


class Strategy:
    """
    Motor da estratégia de Reversão à Média.
    Avalia gatilhos de entrada e gerencia posição aberta.
    """

    def __init__(self):
        self.position: Optional[Position] = None

    @property
    def is_positioned(self) -> bool:
        return self.position is not None

    def evaluate_entry(
        self,
        macro: MacroIndicators,
        execution: ExecutionIndicators,
        ia_authorized: bool,
        ia_snapshot: Optional[dict] = None,
    ) -> bool:
        """
        Avalia se todas as 5 condições de entrada são verdadeiras.
        
        Condições:
        1. Filtro de Tendência (1h): Preço acima da EMA 200
        2. Exaustão de Curto Prazo (5m): Preço na Banda Inferior de Bollinger
        3. Sobrevenda (5m): RSI < 32
        4. Confirmação de Liquidez: RVOL > 1.0
        5. Aval Macro (IA): Autorizado = True
        
        Returns:
            True se todas as condições são atendidas.
        """
        if self.is_positioned:
            return False

        conditions = {
            "EMA200_TREND": macro.price_above_ema,
            "BB_LOWER_TOUCH": execution.price_at_or_below_bb_lower,
            "RSI_OVERSOLD": execution.rsi_oversold,
            "RVOL_CONFIRMED": execution.volume_confirmed,
            "IA_AUTHORIZED": ia_authorized,
        }

        all_met = all(conditions.values())

        # Log detalhado apenas quando há pelo menos 3 condições ativas
        active_count = sum(1 for v in conditions.values() if v)
        if active_count >= 3 or all_met:
            status = " | ".join(
                f"{'✅' if v else '❌'} {k}" for k, v in conditions.items()
            )
            logger.info("[STRATEGY] Gatilhos (%d/5): %s", active_count, status)

        if all_met:
            logger.info(
                "[STRATEGY] 🎯 SINAL DE ENTRADA CONFIRMADO | Preço: R$ %.4f | RSI: %.1f | RVOL: %.2f",
                execution.current_close, execution.rsi, execution.rvol
            )

        return all_met

    def open_position(
        self,
        symbol: str,
        preco_entrada: float,
        quantidade: float,
        atr: float,
        ia_snapshot: Optional[dict] = None,
    ) -> Position:
        """
        Abre uma posição e calcula os stops dinâmicos iniciais.
        
        Stop Loss = Entrada - 1.5 * ATR
        Take Profit = Entrada + 2.0 * ATR
        """
        cfg = config.trading

        stop_loss = preco_entrada - (cfg.sl_atr_mult * atr)
        take_profit = preco_entrada + (cfg.tp_atr_mult * atr)

        self.position = Position(
            symbol=symbol,
            preco_entrada=preco_entrada,
            quantidade=quantidade,
            atr_entrada=atr,
            timestamp_in=time.time(),
            stop_loss=stop_loss,
            take_profit=take_profit,
            highest_price=preco_entrada,
            ia_snapshot=ia_snapshot,
        )

        logger.info(
            "[STRATEGY] 🟢 POSIÇÃO ABERTA | %s | Entrada: R$ %.4f | "
            "SL: R$ %.4f (-%s ATR) | TP: R$ %.4f (+%s ATR) | Qtd: %.6f",
            symbol, preco_entrada, stop_loss, cfg.sl_atr_mult,
            take_profit, cfg.tp_atr_mult, quantidade
        )

        return self.position

    def check_exit(self, current_price: float) -> Optional[ExitReason]:
        """
        Verifica se a posição deve ser fechada com base no preço atual.
        Delega para o mecanismo de stops dinâmicos da Position.
        """
        if not self.is_positioned:
            return None
        return self.position.update_dynamic_stops(current_price)

    def close_position(self) -> Optional[Position]:
        """Fecha a posição e retorna seus dados para registro."""
        pos = self.position
        self.position = None
        return pos

    def restore_position(self, position: Position) -> None:
        """Restaura uma posição a partir do crash recovery."""
        self.position = position
        logger.info(
            "[STRATEGY] ♻️ Posição restaurada | %s | Entrada: R$ %.4f | SL: R$ %.4f | Qtd: %.6f",
            position.symbol, position.preco_entrada, position.stop_loss, position.quantidade
        )
