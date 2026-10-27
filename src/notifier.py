"""
Sistema de Notificações Assíncronas — Telegram + Healthcheck (Heartbeat).
Silencioso quando tudo corre bem, barulhento apenas em eventos financeiros ou anomalias.
"""

import logging
from typing import Optional

import httpx

from . import config

logger = logging.getLogger(__name__)


class Notifier:
    """
    Envia notificações para Telegram e pings de heartbeat.
    Falhas de notificação nunca devem interromper o bot.
    """

    def __init__(self):
        cfg_tg = config.telegram
        self._telegram_enabled = bool(
            cfg_tg.bot_token
            and cfg_tg.chat_id
            and "your_telegram" not in cfg_tg.bot_token
            and "your_telegram" not in cfg_tg.chat_id
        )
        self._telegram_url = (
            f"https://api.telegram.org/bot{cfg_tg.bot_token}/sendMessage"
            if self._telegram_enabled else ""
        )
        self._chat_id = cfg_tg.chat_id

        cfg_hc = config.healthcheck
        self._healthcheck_enabled = bool(
            cfg_hc.url and "your-uuid" not in cfg_hc.url
        )
        self._healthcheck_url = cfg_hc.url

        if self._telegram_enabled:
            logger.info("[NOTIFY] Telegram configurado.")
        else:
            logger.info("[NOTIFY] Telegram desabilitado (aguardando chaves reais no .env).")

        if self._healthcheck_enabled:
            logger.info("[NOTIFY] Healthcheck configurado: %s", cfg_hc.url)
        else:
            logger.info("[NOTIFY] Healthcheck desabilitado (aguardando URL real no .env).")

    async def _send_telegram(self, message: str) -> None:
        """Envia mensagem para o Telegram (best-effort)."""
        if not self._telegram_enabled:
            return
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(self._telegram_url, json={
                    "chat_id": self._chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                })
        except Exception as e:
            logger.warning("[NOTIFY] Falha ao enviar Telegram: %s", e)

    async def ping_healthcheck(self) -> None:
        """Envia ping de heartbeat para o serviço de monitoramento."""
        if not self._healthcheck_enabled:
            return
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.get(self._healthcheck_url)
        except Exception as e:
            logger.warning("[NOTIFY] Falha no heartbeat: %s", e)

    # ------------------------------------------------------------------
    # Eventos de trade
    # ------------------------------------------------------------------

    async def notify_trade_open(
        self,
        symbol: str,
        quantidade: float,
        preco: float,
        stop_loss: float,
        take_profit: float,
        ia_motivo: str = "",
    ) -> None:
        """🟢 Trade Aberto."""
        msg = (
            f"🟢 <b>[COMPRA] {symbol}</b>\n"
            f"Qtd: <code>{quantidade:.6f}</code>\n"
            f"Preço: <code>R$ {preco:.4f}</code>\n"
            f"SL: <code>R$ {stop_loss:.4f}</code>\n"
            f"TP: <code>R$ {take_profit:.4f}</code>\n"
            f"IA: {ia_motivo or 'N/A'}"
        )
        logger.info("[NOTIFY] %s", msg.replace("<b>", "").replace("</b>", "").replace("<code>", "").replace("</code>", ""))
        await self._send_telegram(msg)

    async def notify_trade_close(
        self,
        symbol: str,
        motivo_saida: str,
        pnl: float,
        pnl_pct: float,
        duracao_min: float,
    ) -> None:
        """🔴/🟢 Trade Fechado."""
        emoji = "🟢" if pnl >= 0 else "🔴"
        sinal = "+" if pnl >= 0 else ""
        msg = (
            f"{emoji} <b>[SAÍDA] {motivo_saida}</b> | {symbol}\n"
            f"PnL: <code>{sinal}R$ {pnl:.2f} ({sinal}{pnl_pct:.1f}%)</code>\n"
            f"Tempo: {duracao_min:.0f} min"
        )
        logger.info("[NOTIFY] %s", msg.replace("<b>", "").replace("</b>", "").replace("<code>", "").replace("</code>", ""))
        await self._send_telegram(msg)

    async def notify_ia_lock(self, motivo: str) -> None:
        """⚠️ IA bloqueou operações."""
        msg = (
            f"⚠️ <b>[IA LOCK]</b> Operações pausadas.\n"
            f"Motivo: {motivo}"
        )
        logger.warning("[NOTIFY] %s", msg.replace("<b>", "").replace("</b>", ""))
        await self._send_telegram(msg)

    async def notify_ia_unlock(self, motivo: str) -> None:
        """✅ IA desbloqueou operações."""
        msg = (
            f"✅ <b>[IA UNLOCK]</b> Operações autorizadas.\n"
            f"Motivo: {motivo}"
        )
        logger.info("[NOTIFY] %s", msg.replace("<b>", "").replace("</b>", ""))
        await self._send_telegram(msg)

    async def notify_circuit_breaker(self, motivo: str, pnl_diario: float) -> None:
        """🚨 Circuit Breaker ativado."""
        msg = (
            f"🚨 <b>[EMERGÊNCIA]</b> Circuit Breaker ativado.\n"
            f"PnL diário: <code>R$ {pnl_diario:.2f}</code>\n"
            f"Motivo: {motivo}\n"
            f"Robô dormindo até amanhã (00:00 UTC)."
        )
        logger.critical("[NOTIFY] %s", msg.replace("<b>", "").replace("</b>", "").replace("<code>", "").replace("</code>", ""))
        await self._send_telegram(msg)

    async def notify_cooldown(self, horas: int) -> None:
        """⏸️ Cooldown pós-stops consecutivos."""
        msg = (
            f"⏸️ <b>[COOLDOWN]</b> 2 stops consecutivos.\n"
            f"Robô em dormência por {horas}h."
        )
        logger.warning("[NOTIFY] %s", msg.replace("<b>", "").replace("</b>", ""))
        await self._send_telegram(msg)

    async def notify_high_slippage(
        self, symbol: str, expected_price: float, executed_price: float, slippage_pct: float
    ) -> None:
        """⚠️ Slippage elevado detectado."""
        msg = (
            f"⚠️ <b>[HIGH SLIPPAGE]</b> {symbol}\n"
            f"Esperado: <code>R$ {expected_price:.4f}</code>\n"
            f"Executado: <code>R$ {executed_price:.4f}</code>\n"
            f"Slippage: <code>{slippage_pct:.2f}%</code>\n"
            f"Liquidez baixa no book de ofertas."
        )
        logger.warning("[NOTIFY] HIGH_SLIPPAGE: %.2f%%", slippage_pct)
        await self._send_telegram(msg)

    async def notify_crash_recovery(self, symbol: str, status: str, details: str) -> None:
        """♻️ Recuperação pós-crash."""
        msg = (
            f"♻️ <b>[CRASH RECOVERY]</b> {symbol}\n"
            f"Status: {status}\n"
            f"Detalhes: {details}"
        )
        logger.info("[NOTIFY] %s", msg.replace("<b>", "").replace("</b>", ""))
        await self._send_telegram(msg)

    async def notify_startup(self, mode: str, symbol: str, banca: float) -> None:
        """🚀 Bot iniciado."""
        msg = (
            f"🚀 <b>[STARTUP]</b> Bot iniciado\n"
            f"Modo: <code>{mode}</code>\n"
            f"Par: <code>{symbol}</code>\n"
            f"Banca: <code>R$ {banca:.2f}</code>"
        )
        logger.info("[NOTIFY] Bot iniciado | Modo: %s | Par: %s | Banca: R$ %.2f", mode, symbol, banca)
        await self._send_telegram(msg)
