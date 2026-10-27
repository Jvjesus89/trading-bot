"""
Gerenciamento de Risco — Circuit Breakers e controles operacionais.
Protege a banca contra drawdown excessivo, stops consecutivos e anomalias.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import config

logger = logging.getLogger(__name__)


@dataclass
class RiskState:
    """Estado corrente do gerenciador de risco."""
    pnl_diario: float = 0.0                # PnL acumulado do dia (em BRL)
    stops_consecutivos: int = 0             # Contagem de stops seguidos
    operacional: bool = True                # Flag mestra — False = bot desligado
    cooldown_ate: float = 0.0               # Timestamp até quando está em cooldown
    motivo_bloqueio: str = ""               # Motivo do bloqueio
    trades_hoje: int = 0                    # Contagem de trades no dia
    ultimo_dia_utc: str = ""                # Dia UTC do último reset


class RiskManager:
    """
    Implementa os circuit breakers:
    1. Drawdown Diário Máximo: -6% da banca → desliga até 00:00 UTC
    2. Pausa Pós-Stop: 2 stops consecutivos → cooldown de 2h
    3. Reset automático à meia-noite UTC
    """

    def __init__(self):
        self.state = RiskState()
        self._banca = config.trading.banca_inicial
        self._check_day_reset()

    def _check_day_reset(self) -> None:
        """Reseta contadores se mudou o dia UTC."""
        hoje_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self.state.ultimo_dia_utc != hoje_utc:
            logger.info("[RISCO] Novo dia UTC: %s — resetando contadores.", hoje_utc)
            self.state.pnl_diario = 0.0
            self.state.stops_consecutivos = 0
            self.state.operacional = True
            self.state.motivo_bloqueio = ""
            self.state.trades_hoje = 0
            self.state.ultimo_dia_utc = hoje_utc

    def update_banca(self, nova_banca: float) -> None:
        """Atualiza o valor atual da banca para cálculos dinâmicos."""
        self._banca = nova_banca

    def get_order_size(self) -> float:
        """
        Calcula o tamanho fixo da ordem: 25% da banca.
        Retorna o valor em BRL a ser investido por trade.
        """
        return self._banca * config.trading.ordem_percentual

    def can_trade(self) -> tuple[bool, str]:
        """
        Verifica se o bot está autorizado a operar.
        Retorna (pode_operar, motivo).
        """
        self._check_day_reset()

        # 1. Circuit Breaker: drawdown diário
        if not self.state.operacional:
            return False, f"Circuit breaker ativo: {self.state.motivo_bloqueio}"

        # 2. Cooldown pós-stops consecutivos
        now = time.time()
        if now < self.state.cooldown_ate:
            restante_min = (self.state.cooldown_ate - now) / 60
            return False, f"Cooldown ativo: {restante_min:.0f}min restantes (2 stops consecutivos)"

        return True, "OK"

    def register_trade_result(self, pnl: float, motivo_saida: str) -> None:
        """
        Registra o resultado de um trade e atualiza os circuit breakers.
        
        Args:
            pnl: Lucro/Prejuízo do trade em BRL (positivo = lucro).
            motivo_saida: STOP_LOSS, TAKE_PROFIT, BREAKEVEN, TRAILING.
        """
        self._check_day_reset()

        self.state.pnl_diario += pnl
        self.state.trades_hoje += 1

        logger.info(
            "[RISCO] Trade #%d | PnL: R$ %.2f | PnL diário: R$ %.2f | Saída: %s",
            self.state.trades_hoje, pnl, self.state.pnl_diario, motivo_saida
        )

        # Atualiza contagem de stops consecutivos
        if motivo_saida == "STOP_LOSS":
            self.state.stops_consecutivos += 1
            logger.warning(
                "[RISCO] Stop Loss #%d consecutivo", self.state.stops_consecutivos
            )
        else:
            # Qualquer saída que não seja stop zera o contador
            self.state.stops_consecutivos = 0

        # Circuit Breaker 1: Drawdown Diário
        limite_perda = self._banca * config.trading.drawdown_diario_max
        if self.state.pnl_diario <= -limite_perda:
            self.state.operacional = False
            self.state.motivo_bloqueio = (
                f"Drawdown diário atingido: R$ {self.state.pnl_diario:.2f} "
                f"(limite: -R$ {limite_perda:.2f})"
            )
            logger.critical("[RISCO] 🚨 %s", self.state.motivo_bloqueio)
            return

        # Circuit Breaker 2: Cooldown pós-stops
        if self.state.stops_consecutivos >= config.trading.cooldown_stops_consecutivos:
            cooldown_seconds = config.trading.cooldown_horas * 3600
            self.state.cooldown_ate = time.time() + cooldown_seconds
            self.state.stops_consecutivos = 0  # Reset após ativar cooldown
            logger.warning(
                "[RISCO] ⏸️ Cooldown de %dh ativado após %d stops consecutivos",
                config.trading.cooldown_horas,
                config.trading.cooldown_stops_consecutivos,
            )

    def get_status_summary(self) -> dict:
        """Retorna resumo do estado de risco para logs/notificações."""
        can, reason = self.can_trade()
        return {
            "operacional": can,
            "motivo": reason,
            "pnl_diario": round(self.state.pnl_diario, 2),
            "trades_hoje": self.state.trades_hoje,
            "stops_consecutivos": self.state.stops_consecutivos,
            "banca_atual": round(self._banca, 2),
            "tamanho_ordem": round(self.get_order_size(), 2),
        }
