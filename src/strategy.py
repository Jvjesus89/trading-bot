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
        # Só move o stop quando o lucro já paga com folga o custo de ida e volta.
        lucro_flutuante = current_price - self.preco_entrada
        breakeven_trigger = max(
            cfg.be_atr_mult * self.atr_entrada,
            cfg.be_min_mult_custo * cfg.custo_ida_volta * self.preco_entrada,
        )
        stop_be = self.preco_entrada * (1 + cfg.be_fee_offset)

        if self.stop_state == StopState.INITIAL and lucro_flutuante >= breakeven_trigger:
            # Move stop para Preço de Entrada + custo (taxas + spread)
            self.stop_loss = max(self.stop_loss, stop_be)
            self.stop_state = StopState.BREAKEVEN
            logger.info(
                "[STRATEGY] 🛡️ Breakeven ativado | Novo SL: R$ %.4f (entrada + custos)",
                self.stop_loss
            )

        # --- CHECK 3: Alvo atingido → trailing curto (nunca abaixo do breakeven) ---
        if current_price >= self.take_profit:
            trailing_stop = max(
                self.highest_price - (cfg.trailing_atr_mult * self.atr_entrada),
                stop_be,
            )

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
        Avalia se todas as condições de entrada são verdadeiras.

        Condições:
        1. Filtro de Tendência (1h): Preço acima da EMA 200
        2. Exaustão de Curto Prazo (5m): Fechamento na/abaixo da Banda Inferior
        3. Sobrevenda (5m): RSI < 32
        4. Confirmação de Liquidez: RVOL > 1.0
        5. Candle de reversão (se EXIGIR_REVERSAO): candle seguinte fechou verde
        6. Alvo cobre custo: distância até a média >= N x custos e >= MIN_RR x stop
        7. Aval Macro: filtro de regras (ou Gemini, se USAR_IA=true)
        
        Returns:
            True se todas as condições são atendidas.
        """
        if self.is_positioned:
            return False

        cfg = config.trading
        conditions = {
            "EMA200_TREND": macro.price_above_ema,
            "BB_LOWER_TOUCH": execution.price_at_or_below_bb_lower,
            "RSI_OVERSOLD": execution.rsi_oversold,
            "RVOL_CONFIRMED": execution.volume_confirmed,
        }
        if cfg.exigir_reversao:
            conditions["REVERSAL_CANDLE"] = execution.reversao_confirmada
        conditions["TARGET_COVERS_COST"] = execution.alvo_cobre_custo
        conditions["MACRO_AUTHORIZED"] = ia_authorized

        all_met = all(conditions.values())

        # Log detalhado apenas quando há pelo menos 3 condições ativas
        active_count = sum(1 for v in conditions.values() if v)
        if active_count >= len(conditions) - 2 or all_met:
            status = " | ".join(
                f"{'✅' if v else '❌'} {k}" for k, v in conditions.items()
            )
            logger.info("[STRATEGY] Gatilhos (%d/%d): %s", active_count, len(conditions), status)

        if all_met:
            logger.info(
                "[STRATEGY] 🎯 SINAL DE ENTRADA CONFIRMADO | Preço: R$ %.4f | RSI: %.1f | "
                "RVOL: %.2f | Distância até o alvo: %.2f%%",
                execution.current_close, execution.rsi, execution.rvol, execution.distancia_alvo_pct
            )

        return all_met

    def open_position(
        self,
        symbol: str,
        preco_entrada: float,
        quantidade: float,
        atr: float,
        ia_snapshot: Optional[dict] = None,
        alvo: Optional[float] = None,
    ) -> Position:
        """
        Abre uma posição e calcula os stops dinâmicos iniciais.
        
        Stop Loss = Entrada - 1.5 * ATR
        Take Profit = Entrada + 2.0 * ATR
        """
        cfg = config.trading

        stop_loss = preco_entrada - (cfg.sl_atr_mult * atr)
        take_profit = preco_entrada + (cfg.tp_atr_mult * atr)
        # Alvo na banda média (reversão à média), se ainda estiver acima da entrada + custos
        if cfg.alvo_na_media and alvo and alvo > preco_entrada * (1 + cfg.custo_ida_volta):
            take_profit = alvo

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
            "SL: R$ %.4f (-%s ATR) | TP: R$ %.4f | Qtd: %.6f",
            symbol, preco_entrada, stop_loss, cfg.sl_atr_mult,
            take_profit, quantidade
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
