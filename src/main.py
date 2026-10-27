"""
Motor Quantitativo de Alta Performance — Entry Point e Orquestrador.

Arquitetura Dual-Speed:
  • Fast Loop (10s): Monitoramento, indicadores, gestão de stops
  • Slow Loop (30min): Consulta Gemini Flash para contexto macro
  • Heartbeat (5min): Ping de saúde para monitoramento externo
"""

import asyncio
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Union

from . import config
from .exchange import ExchangeClient
from .paper_trading import PaperTradingClient
from .indicators import calculate_macro_indicators, calculate_execution_indicators
from .strategy import Strategy, ExitReason
from .risk_manager import RiskManager
from .ai_advisor import AIAdvisor
from .persistence import PersistenceManager
from .state_manager import StateManager
from .notifier import Notifier

# Configura logging
LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / "bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("main")


class TradingEngine:
    """
    Orquestrador principal do robô de day trade.
    Coordena todos os módulos em loops assíncronos independentes.
    """

    def __init__(self):
        # Seleciona cliente: Live ou Paper
        if config.is_live():
            self.client: Union[ExchangeClient, PaperTradingClient] = ExchangeClient()
        else:
            self.client = PaperTradingClient()

        self.strategy = Strategy()
        self.risk_manager = RiskManager()
        self.ai_advisor = AIAdvisor()
        self.persistence = PersistenceManager()
        self.notifier = Notifier()
        self.state_manager = StateManager(self.client, self.persistence, self.strategy)

        self._current_trade_id: str = ""
        self._running = True
        self._last_ia_was_authorized = False  # Para detectar mudanças de estado IA

    async def start(self) -> None:
        """Inicializa conexões e executa o motor."""
        mode = config.trading.mode
        symbol = config.trading.symbol
        banca = config.trading.banca_inicial

        logger.info("=" * 60)
        logger.info("  MOTOR QUANTITATIVO DE ALTA PERFORMANCE")
        logger.info("  Modo: %s | Par: %s | Banca: R$ %.2f", mode, symbol, banca)
        logger.info("=" * 60)

        try:
            # 1. Conecta à exchange
            await self.client.connect()

            # 2. Conecta ao banco
            await self.persistence.connect()

            # 3. Bootstrap: reconcilia estado pós-crash
            bootstrap_result = await self.state_manager.bootstrap_state()
            logger.info("[BOOTSTRAP] Resultado: %s", bootstrap_result)

            if bootstrap_result == "RESTORED":
                self._current_trade_id = self.state_manager.current_trade_id or ""
                await self.notifier.notify_crash_recovery(
                    symbol, "RESTORED", "Posição restaurada com sucesso após reinício."
                )
            elif bootstrap_result == "ORPHAN_RECOVERED":
                await self.notifier.notify_crash_recovery(
                    symbol, "ORPHAN_RECOVERED",
                    "Posição órfã detectada e fechada. Estado limpo."
                )

            # 4. Carrega PnL diário
            daily_pnl = await self.persistence.get_daily_pnl()
            self.risk_manager.state.pnl_diario = daily_pnl
            logger.info("[INIT] PnL diário restaurado: R$ %.2f", daily_pnl)

            # 5. Notificação de startup
            await self.notifier.notify_startup(mode, symbol, banca)

            # 6. Executa loops em paralelo
            await asyncio.gather(
                self._fast_loop(),
                self._slow_loop(),
                self._heartbeat_loop(),
            )

        except KeyboardInterrupt:
            logger.info("Desligamento solicitado pelo usuário.")
        except Exception as e:
            logger.critical("Erro fatal no motor: %s", e, exc_info=True)
        finally:
            await self._shutdown()

    async def _shutdown(self) -> None:
        """Encerramento gracioso."""
        self._running = False
        logger.info("Encerrando conexões...")
        try:
            await self.client.close()
        except Exception as e:
            logger.error("Erro ao fechar exchange: %s", e)
        logger.info("Motor encerrado.")

    # ==================================================================
    # FAST LOOP (a cada 10 segundos)
    # ==================================================================

    async def _fast_loop(self) -> None:
        """
        Camada Executora — roda a cada 10 segundos.
        Responsabilidades:
        - Buscar dados de mercado (OHLCV 1h e 5m)
        - Calcular indicadores técnicos
        - Avaliar gatilhos de entrada
        - Gerenciar stops dinâmicos da posição aberta
        - Executar ordens (compra/venda)
        """
        symbol = config.trading.symbol
        interval = config.trading.fast_loop_interval

        # Espera a primeira consulta da IA (ou timeout de 60s)
        logger.info("[FAST] Aguardando primeira consulta da IA...")
        start_wait = time.time()
        while not self.ai_advisor.last_verdict.timestamp and (time.time() - start_wait) < 60:
            await asyncio.sleep(1)

        logger.info("[FAST] Iniciando Fast Loop (intervalo: %ds)", interval)

        while self._running:
            cycle_start = time.time()
            try:
                await self._fast_cycle(symbol)
            except Exception as e:
                logger.error("[FAST] Erro no ciclo: %s", e, exc_info=True)

            # Mantém cadência de 10 segundos
            elapsed = time.time() - cycle_start
            sleep_time = max(0, interval - elapsed)
            await asyncio.sleep(sleep_time)

    async def _fast_cycle(self, symbol: str) -> None:
        """Um ciclo completo do Fast Loop."""

        # --- Verifica circuit breakers ---
        can_trade, reason = self.risk_manager.can_trade()
        if not can_trade:
            # Se temos posição, ainda precisamos monitorar os stops
            if self.strategy.is_positioned:
                await self._monitor_position(symbol)
            return

        # --- Busca dados de mercado ---
        ohlcv_1h = await self.client.fetch_ohlcv(symbol, "1h", limit=250)
        ohlcv_5m = await self.client.fetch_ohlcv(symbol, "5m", limit=50)

        # --- Calcula indicadores ---
        macro = calculate_macro_indicators(ohlcv_1h)
        execution = calculate_execution_indicators(ohlcv_5m)

        if macro is None or execution is None:
            logger.warning("[FAST] Indicadores incompletos. Pulando ciclo.")
            return

        # --- Exporta estado para o Front-end ---
        await self._export_state(execution, macro)

        # --- Se posicionado: gerencia saída ---
        if self.strategy.is_positioned:
            ticker = await self.client.fetch_ticker(symbol)
            current_price = ticker.get("last", execution.current_close)
            exit_reason = self.strategy.check_exit(current_price)

            if exit_reason:
                await self._execute_exit(symbol, current_price, exit_reason)
            return

        # --- Se não posicionado: avalia entrada ---
        ia_authorized = self.ai_advisor.is_authorized

        if self.strategy.evaluate_entry(macro, execution, ia_authorized):
            await self._execute_entry(symbol, execution)

    async def _monitor_position(self, symbol: str) -> None:
        """Monitora stops mesmo quando circuit breaker está ativo."""
        try:
            ticker = await self.client.fetch_ticker(symbol)
            current_price = ticker.get("last", 0)
            exit_reason = self.strategy.check_exit(current_price)
            if exit_reason:
                await self._execute_exit(symbol, current_price, exit_reason)
        except Exception as e:
            logger.error("[FAST] Erro ao monitorar posição: %s", e)

    async def _export_state(self, execution, macro) -> None:
        """Gera arquivo de telemetria em tempo real para o Front-end."""
        import json
        try:
            pos = self.strategy.position
            pos_dict = None
            if pos:
                lucro_brl = (execution.current_close - pos.preco_entrada) * pos.quantidade
                lucro_pct = ((execution.current_close - pos.preco_entrada) / pos.preco_entrada) * 100
                pos_dict = {
                    "symbol": pos.symbol,
                    "preco_entrada": pos.preco_entrada,
                    "preco_atual": execution.current_close,
                    "quantidade": pos.quantidade,
                    "stop_loss": pos.stop_loss,
                    "take_profit": pos.take_profit,
                    "stop_state": pos.stop_state.value,
                    "highest_price": pos.highest_price,
                    "timestamp_in": pos.timestamp_in,
                    "lucro_flutuante_brl": round(lucro_brl, 4),
                    "lucro_flutuante_pct": round(lucro_pct, 2),
                }

            can_trade, reason = self.risk_manager.can_trade()
            state_data = {
                "timestamp": time.time(),
                "symbol": config.trading.symbol,
                "mode": config.trading.mode,
                "price": execution.current_close,
                "volume": execution.current_volume,
                "risk": {
                    "operacional": can_trade,
                    "motivo": reason,
                    "pnl_diario": round(self.risk_manager.state.pnl_diario, 2),
                    "trades_hoje": self.risk_manager.state.trades_hoje,
                    "stops_consecutivos": self.risk_manager.state.stops_consecutivos,
                    "banca_atual": round(self.risk_manager._banca, 2),
                },
                "ia": self.ai_advisor.last_verdict.to_dict(),
                "position": pos_dict,
                "indicators": {
                    "rsi": round(execution.rsi, 2),
                    "bb_upper": round(execution.bb_upper, 4),
                    "bb_middle": round(execution.bb_middle, 4),
                    "bb_lower": round(execution.bb_lower, 4),
                    "atr": round(execution.atr, 4),
                    "rvol": round(execution.rvol, 2),
                    "ema_200": round(macro.ema_200, 4) if macro else None,
                },
                "signals": {
                    "ema200_trend": macro.price_above_ema if macro else False,
                    "bb_lower_touch": execution.price_at_or_below_bb_lower,
                    "rsi_oversold": execution.rsi_oversold,
                    "rvol_confirmed": execution.volume_confirmed,
                    "ia_authorized": self.ai_advisor.is_authorized,
                }
            }

            state_file = LOG_DIR / "bot_state.json"
            temp_file = LOG_DIR / "bot_state.json.tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(state_data, f, indent=2)
            temp_file.replace(state_file)
        except Exception as e:
            logger.debug("[FAST] Erro ao exportar estado: %s", e)

    # ------------------------------------------------------------------
    # Execução de ordens
    # ------------------------------------------------------------------

    async def _execute_entry(self, symbol: str, execution) -> None:
        """Executa uma entrada (compra a mercado)."""
        cfg = config.trading

        # Calcula tamanho da ordem
        order_value_brl = self.risk_manager.get_order_size()
        price = execution.current_close
        amount = order_value_brl / price

        # Valida nocional mínimo
        if not self.client.validate_min_notional(amount, price):
            logger.warning(
                "[FAST] Ordem abaixo do nocional mínimo: R$ %.2f < R$ %.2f",
                amount * price, cfg.min_notional
            )
            return

        # Executa compra
        try:
            order = await self.client.create_market_buy(symbol, amount)
        except Exception as e:
            logger.error("[FAST] Erro ao executar compra: %s", e)
            return

        filled = order["filled"]
        avg_price = order["average_price"]

        # Verifica slippage
        slippage_pct = abs(avg_price - price) / price
        if slippage_pct > cfg.slippage_max:
            await self.notifier.notify_high_slippage(
                symbol, price, avg_price, slippage_pct * 100
            )

        # Abre posição na estratégia (usa preço médio executado)
        ia_snapshot = self.ai_advisor.last_verdict.to_dict()
        position = self.strategy.open_position(
            symbol=symbol,
            preco_entrada=avg_price,
            quantidade=filled,
            atr=execution.atr,
            ia_snapshot=ia_snapshot,
        )

        # Persiste trade
        self._current_trade_id = await self.persistence.record_entry(
            symbol=symbol,
            preco_entrada=avg_price,
            quantidade=filled,
            ia_snapshot=ia_snapshot,
        )

        # Notifica
        await self.notifier.notify_trade_open(
            symbol=symbol,
            quantidade=filled,
            preco=avg_price,
            stop_loss=position.stop_loss,
            take_profit=position.take_profit,
            ia_motivo=self.ai_advisor.last_verdict.motivo,
        )

    async def _execute_exit(self, symbol: str, current_price: float, reason: ExitReason) -> None:
        """Executa uma saída (venda a mercado)."""
        position = self.strategy.position
        if not position:
            return

        try:
            order = await self.client.create_market_sell(symbol, position.quantidade)
        except Exception as e:
            logger.error("[FAST] Erro ao executar venda: %s", e)
            return

        avg_price = order["average_price"]
        filled = order["filled"]

        # Fecha posição na estratégia
        closed_position = self.strategy.close_position()

        # Calcula PnL
        pnl = await self.persistence.record_exit(
            trade_id=self._current_trade_id,
            preco_saida=avg_price,
            quantidade=filled,
            motivo_saida=reason.value,
        )

        # Registra no risk manager
        self.risk_manager.register_trade_result(pnl, reason.value)

        # Calcula % e duração
        pnl_pct = (pnl / (closed_position.preco_entrada * closed_position.quantidade)) * 100 if closed_position else 0
        duracao_min = (time.time() - closed_position.timestamp_in) / 60 if closed_position else 0

        # Notifica
        await self.notifier.notify_trade_close(
            symbol=symbol,
            motivo_saida=reason.value,
            pnl=pnl,
            pnl_pct=pnl_pct,
            duracao_min=duracao_min,
        )

        # Verifica se circuit breaker foi ativado
        can_trade, cb_reason = self.risk_manager.can_trade()
        if not can_trade:
            if "Drawdown" in cb_reason or "Circuit" in cb_reason:
                await self.notifier.notify_circuit_breaker(
                    cb_reason, self.risk_manager.state.pnl_diario
                )
            elif "Cooldown" in cb_reason:
                await self.notifier.notify_cooldown(config.trading.cooldown_horas)

        # Atualiza banca (em paper trading)
        if config.is_paper():
            balance = await self.client.fetch_balance()
            nova_banca = float(
                balance.get(config.trading.quote_currency, {}).get("free", config.trading.banca_inicial)
            )
            self.risk_manager.update_banca(nova_banca)

        self._current_trade_id = ""

    # ==================================================================
    # SLOW LOOP (a cada 30 minutos)
    # ==================================================================

    async def _slow_loop(self) -> None:
        """
        Camada de Contexto IA — consulta Gemini Flash a cada 30 minutos.
        Processa métricas macro para autorizar/bloquear o Fast Loop.
        """
        interval = config.trading.slow_loop_interval
        logger.info("[SLOW] Iniciando Slow Loop (intervalo: %ds = %dmin)", interval, interval // 60)

        while self._running:
            try:
                await self._slow_cycle()
            except Exception as e:
                logger.error("[SLOW] Erro no ciclo: %s", e, exc_info=True)

            await asyncio.sleep(interval)

    async def _slow_cycle(self) -> None:
        """Um ciclo completo do Slow Loop."""
        # Coleta métricas
        btc_var = await self.client.fetch_btc_variation_4h()

        # Funding rate — se disponível (apenas em futuros, usa 0 como default)
        funding_rate = 0.0  # Binance Spot não tem funding; pode ser estendido

        # ATR de 1h
        symbol = config.trading.symbol
        ohlcv_1h = await self.client.fetch_ohlcv(symbol, "1h", limit=250)
        macro = calculate_macro_indicators(ohlcv_1h)
        atr_1h = macro.atr_1h if macro else 0.0

        logger.info(
            "[SLOW] Métricas IA | BTC 4h: %+.2f%% | Funding: %.4f%% | ATR 1h: %.4f",
            btc_var, funding_rate, atr_1h
        )

        # Consulta IA
        was_authorized = self._last_ia_was_authorized
        verdict = await self.ai_advisor.consult(btc_var, funding_rate, atr_1h)

        # Detecta mudança de estado e notifica
        if was_authorized and not verdict.autorizado:
            await self.notifier.notify_ia_lock(verdict.motivo)
        elif not was_authorized and verdict.autorizado:
            await self.notifier.notify_ia_unlock(verdict.motivo)

        self._last_ia_was_authorized = verdict.autorizado

    # ==================================================================
    # HEARTBEAT (a cada 5 minutos)
    # ==================================================================

    async def _heartbeat_loop(self) -> None:
        """Envia pings de saúde para monitoramento externo."""
        interval = config.trading.heartbeat_interval
        logger.info("[HEARTBEAT] Iniciando (intervalo: %ds = %dmin)", interval, interval // 60)

        while self._running:
            try:
                await self.notifier.ping_healthcheck()
            except Exception as e:
                logger.error("[HEARTBEAT] Erro: %s", e)
            await asyncio.sleep(interval)


def main():
    """Entry point do motor."""
    engine = TradingEngine()
    try:
        asyncio.run(engine.start())
    except KeyboardInterrupt:
        print("\nDesligamento solicitado. Até logo!")


if __name__ == "__main__":
    main()
