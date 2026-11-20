"""
Lógica da Estratégia — Reversão à Média com Filtro de Exaustão e Gestão Dinâmica.
Coordena os gatilhos de entrada (anti-falling knife) e a gestão de saída protegida contra spread.
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
        # O gatilho de breakeven exige pelo menos 1.0 ATR ou 0.8% de valorização
        breakeven_trigger = max(cfg.be_atr_mult * self.atr_entrada, self.preco_entrada * 0.008)

        if self.stop_state == StopState.INITIAL and lucro_flutuante >= breakeven_trigger:
            # Move stop para Preço de Entrada + offset de taxa (cobrindo taxas completas)
            novo_stop = self.preco_entrada * (1 + cfg.be_fee_offset)
            if novo_stop > self.stop_loss:
                self.stop_loss = novo_stop
                self.stop_state = StopState.BREAKEVEN
                logger.info(
                    "[STRATEGY] 🛡️ Breakeven ativado | Novo SL: R$ %.4f (entrada + 0.2%% taxas)",
                    novo_stop
                )

        # --- CHECK 3: Promoção para Trailing Stop ---
        if current_price >= self.take_profit:
            # Não executa TP imediatamente — ativa trailing stop para capturar extensões
            trailing_distance = max(cfg.trailing_atr_mult * self.atr_entrada, self.preco_entrada * 0.008)
            trailing_stop = self.highest_price - trailing_distance

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
    Motor da estratégia de Reversão à Média Quantitativa.
    Implementa:
    1. Desvio de Exaustão (preço acima da EMA200 OU reversão de fundo com candle verde)
    2. Proteção Anti-Faca Caindo (espera compradores absorverem o despejo)
    3. Gestão de Stops com piso de segurança contra spread de SOL/BRL
    """

    def __init__(self):
        self.position: Optional[Position] = None

    @property
    def is_positioned(self) -> bool:
        return self.position is not None

    def _check_conditions(
        self,
        macro: MacroIndicators,
        execution: ExecutionIndicators,
        ia_authorized: bool,
    ) -> dict:
        """Calcula os 5 gatilhos sem emitir o log final de confirmação."""
        cfg = config.trading

        # --- GATILHO 1: Tendência Primária OU Reversão de Fundo por Exaustão ---
        is_exhaustion_reversal = (
            execution.rsi <= cfg.rsi_reversal_threshold
            and execution.is_green_candle
        )
        trend_or_reversal_ok = (
            macro.price_above_ema
            or (cfg.allow_below_ema_reversal and is_exhaustion_reversal)
            or (config.is_paper() and cfg.paper_ignore_ema200)
        )

        if cfg.allow_below_ema_reversal and not macro.price_above_ema and is_exhaustion_reversal:
            logger.info(
                "[STRATEGY] ⚡ Oportunidade de Reversão no Fundo detectada (RSI: %.1f <= %.0f + Candle Verde) abaixo da EMA200",
                execution.rsi, cfg.rsi_reversal_threshold
            )

        # --- GATILHO 2: Toque na Banda Inferior com Proteção Anti-Faca Caindo ---
        bb_tested = execution.price_tested_bb_lower
        if cfg.require_green_candle:
            # Se a vela ainda for vermelha em queda livre, recusa entrada e espera o repique
            bb_condition = bb_tested and execution.is_green_candle
        else:
            bb_condition = bb_tested

        # --- GATILHOS 3, 4 e 5 ---
        return {
            "EMA200_TREND": trend_or_reversal_ok,
            "BB_LOWER_TOUCH": bb_condition,
            "RSI_OVERSOLD": execution.rsi_oversold,
            "RVOL_CONFIRMED": execution.volume_confirmed,
            "IA_AUTHORIZED": ia_authorized,
        }

    def _log_conditions(
        self,
        conditions: dict,
        label: str,
        execution: ExecutionIndicators,
    ) -> None:
        """Loga o checklist quando há pelo menos 3 condições ativas."""
        active_count = sum(1 for v in conditions.values() if v)
        total = len(conditions)
        if active_count >= 3 or all(conditions.values()):
            status = " | ".join(
                f"{'✅' if v else '❌'} {k}" for k, v in conditions.items()
            )
            # Notifica se o bloqueio foi por candle vermelho derretendo (falling knife)
            extra = (
                " [Aguardando candle verde de reação]"
                if (execution.price_tested_bb_lower and not execution.is_green_candle)
                else ""
            )
            logger.info(
                "[STRATEGY] %s (%d/%d): %s%s",
                label, active_count, total, status, extra,
            )

    def technical_setup(
        self,
        macro: MacroIndicators,
        execution: ExecutionIndicators,
    ) -> bool:
        """
        Avalia apenas os 4 filtros técnicos (sem IA).

        O Fast Loop usa este método para só então chamar o auditor DeepSeek:
        a IA audita a entrada específica, em vez de liberar/bloquear o robô
        inteiro por 30 minutos.
        """
        if self.is_positioned:
            return False

        conditions = self._check_conditions(macro, execution, ia_authorized=True)
        technical = {
            key: value
            for key, value in conditions.items()
            if key != "IA_AUTHORIZED"
        }
        self._log_conditions(technical, "Gatilhos técnicos", execution)

        all_met = all(technical.values())
        if all_met:
            logger.info(
                "[STRATEGY] 🎯 SETUP TÉCNICO CONFIRMADO (4/4) | Preço: R$ %.4f | "
                "RSI: %.1f | RVOL: %.2f | Candle: %s — enviando à auditoria de IA",
                execution.current_close, execution.rsi, execution.rvol,
                "VERDE (Alta)" if execution.is_green_candle else "NEUTRO",
            )
        return all_met

    def evaluate_entry(
        self,
        macro: MacroIndicators,
        execution: ExecutionIndicators,
        ia_authorized: bool,
        ia_snapshot: Optional[dict] = None,
    ) -> bool:
        """
        Avalia os 5 gatilhos simultâneos (usado pelo backtest e por testes).

        No Fast Loop a decisão é feita em duas etapas: `technical_setup()`
        (4 filtros) e depois `AIAdvisor.audit_entry()` (5ª condição).
        """
        if self.is_positioned:
            return False

        conditions = self._check_conditions(macro, execution, ia_authorized)
        all_met = all(conditions.values())
        self._log_conditions(conditions, "Gatilhos", execution)

        if all_met:
            logger.info(
                "[STRATEGY] 🎯 SINAL DE ENTRADA CONFIRMADO | Preço: R$ %.4f | RSI: %.1f | RVOL: %.2f | Candle: %s",
                execution.current_close, execution.rsi, execution.rvol,
                "VERDE (Alta)" if execution.is_green_candle else "NEUTRO"
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
        Abre uma posição calculando stops protegidos contra ruído de spread:
        
        - Stop Loss = Max(2.0 * ATR, 1.5% do Preço de Entrada)
        - Take Profit = Max(2.5 * ATR, 1.5% do Preço de Entrada)
        """
        cfg = config.trading

        # Distância segura de Stop Loss
        atr_sl_dist = cfg.sl_atr_mult * atr
        min_sl_dist = preco_entrada * cfg.sl_min_pct
        sl_distance = max(atr_sl_dist, min_sl_dist)
        stop_loss = preco_entrada - sl_distance

        # Distância segura de Take Profit
        atr_tp_dist = cfg.tp_atr_mult * atr
        min_tp_dist = preco_entrada * cfg.tp_min_pct
        tp_distance = max(atr_tp_dist, min_tp_dist)
        take_profit = preco_entrada + tp_distance

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

        sl_pct = (sl_distance / preco_entrada) * 100.0
        tp_pct = (tp_distance / preco_entrada) * 100.0

        logger.info(
            "[STRATEGY] 🟢 POSIÇÃO ABERTA | %s | Entrada: R$ %.4f | "
            "SL: R$ %.4f (-%.2f%%) | TP: R$ %.4f (+%.2f%%) | Qtd: %.6f",
            symbol, preco_entrada, stop_loss, sl_pct,
            take_profit, tp_pct, quantidade
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
