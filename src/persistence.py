"""
Persistência de dados — Integração com Supabase (PostgreSQL).
Registra trades, recupera estado e suporta crash recovery.
"""

import json
import logging
import time
import uuid
import os
from datetime import datetime, timezone
from typing import Optional

from . import config

logger = logging.getLogger(__name__)

# Flag para indicar se supabase está disponível
_SUPABASE_AVAILABLE = False
try:
    from supabase import create_client, Client
    _SUPABASE_AVAILABLE = True
except ImportError:
    logger.warning("[PERSIST] Biblioteca supabase não instalada. Usando fallback local.")


class LocalFallbackStore:
    """
    Fallback local quando Supabase não está configurado ou offline.
    Persiste trades em arquivo JSON (logs/trades.json).
    """

    def __init__(self, filepath: str = "logs/trades.json"):
        self._filepath = filepath
        self._trades: list[dict] = []
        self._load()

    def _load(self) -> None:
        try:
            with open(self._filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._trades = data if isinstance(data, list) else []
        except (FileNotFoundError, json.JSONDecodeError):
            self._trades = []

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self._filepath) or ".", exist_ok=True)
        with open(self._filepath, "w", encoding="utf-8") as f:
            json.dump(self._trades, f, indent=2, default=str)

    def insert_trade(self, trade: dict) -> str:
        trade_id = trade.get("id") or str(uuid.uuid4())
        trade["id"] = trade_id
        # Evita duplicatas se o trade já existir
        self._trades = [t for t in self._trades if t.get("id") != trade_id]
        self._trades.insert(0, trade)
        self._save()
        return trade_id

    def update_trade(self, trade_id: str, updates: dict) -> None:
        for t in self._trades:
            if t.get("id") == trade_id:
                t.update(updates)
                break
        self._save()

    def get_open_trade(self, symbol: str) -> Optional[dict]:
        for t in self._trades:
            if t.get("symbol") == symbol and t.get("timestamp_out") is None:
                return t
        return None

    def get_daily_pnl(self) -> float:
        hoje = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        total = 0.0
        for t in self._trades:
            ts_out = t.get("timestamp_out", "")
            if ts_out and str(ts_out).startswith(hoje):
                total += float(t.get("pnl_liquido", 0) or 0)
        return total


class PersistenceManager:
    """
    Interface unificada de persistência.
    Usa Supabase (schema trading_bot ou public) quando configurado,
    mantendo sempre espelhamento duplo em logs/trades.json para consumo do frontend.
    """

    def __init__(self):
        self._client: Optional[Client] = None
        self._fallback = LocalFallbackStore()
        self._use_supabase = False
        self._use_schema = False
        self._schema_name = config.supabase.schema or "trading_bot"

    def _table(self):
        """Retorna referência à tabela bot_trades com ou sem schema customizado."""
        if self._use_schema and hasattr(self._client, "schema"):
            return self._client.schema(self._schema_name).table("bot_trades")
        return self._client.table("bot_trades")

    async def connect(self) -> None:
        """Inicializa conexão com Supabase testando o schema trading_bot e public."""
        cfg = config.supabase
        if _SUPABASE_AVAILABLE and cfg.url and cfg.key:
            try:
                self._client = create_client(cfg.url, cfg.key)

                # 1. Tenta acessar com schema customizado (ex: trading_bot)
                try:
                    if hasattr(self._client, "schema"):
                        self._client.schema(self._schema_name).table("bot_trades").select("id").limit(1).execute()
                        self._use_schema = True
                        self._use_supabase = True
                        logger.info(
                            "[PERSIST] Conectado ao Supabase no schema '%s.bot_trades': %s",
                            self._schema_name, cfg.url
                        )
                except Exception as s_err:
                    logger.debug("[PERSIST] Schema %s direto não retornou dados: %s", self._schema_name, s_err)

                # 2. Se não conectou no schema, tenta acessar no schema padrão (public)
                if not self._use_supabase:
                    try:
                        self._client.table("bot_trades").select("id").limit(1).execute()
                        self._use_schema = False
                        self._use_supabase = True
                        logger.info("[PERSIST] Conectado ao Supabase em 'public.bot_trades': %s", cfg.url)
                    except Exception as p_err:
                        logger.debug("[PERSIST] public.bot_trades não retornou dados: %s", p_err)

                # 3. Se conectou no Supabase, sincroniza histórico existente para logs/trades.json
                if self._use_supabase:
                    try:
                        res = self._table().select("*").order("timestamp_in", desc=True).limit(100).execute()
                        if res.data:
                            os.makedirs("logs", exist_ok=True)
                            with open("logs/trades.json", "w", encoding="utf-8") as f:
                                json.dump(res.data, f, indent=2, default=str)
                            self._fallback._load()
                            logger.info("[PERSIST] Sincronizados %d trades do Supabase para logs/trades.json", len(res.data))
                    except Exception as sync_err:
                        logger.debug("[PERSIST] Não foi possível sincronizar histórico inicial: %s", sync_err)
                    return

                # Se ambos falharem, ativa fallback amigável
                self._use_supabase = False
                logger.warning(
                    "[PERSIST] Conexão com Supabase estabelecida, mas a tabela '%s.bot_trades' precisa de permissões no Supabase SQL Editor. "
                    "Usando fallback local (logs/trades.json).",
                    self._schema_name
                )
            except Exception as e:
                logger.error("[PERSIST] Falha ao conectar Supabase: %s | Usando fallback local", e)
        else:
            logger.info("[PERSIST] Supabase não configurado. Usando persistência local (logs/trades.json)")

    async def record_entry(
        self,
        symbol: str,
        preco_entrada: float,
        quantidade: float,
        ia_snapshot: Optional[dict] = None,
    ) -> str:
        """
        Registra a abertura de um trade.
        Retorna o trade_id para posterior atualização.
        """
        now = datetime.now(timezone.utc).isoformat()
        trade_data = {
            "timestamp_in": now,
            "timestamp_out": None,
            "symbol": symbol,
            "preco_entrada": preco_entrada,
            "preco_saida": None,
            "quantidade": quantidade,
            "pnl_liquido": None,
            "motivo_saida": None,
            "ia_snapshot": ia_snapshot,
        }

        trade_id = None
        if self._use_supabase:
            try:
                result = self._table().insert(trade_data).execute()
                trade_id = result.data[0]["id"]
                logger.info("[PERSIST] Trade registrado no Supabase | ID: %s", trade_id)
            except Exception as e:
                logger.error("[PERSIST] Erro ao inserir no Supabase: %s | Usando fallback local", e)

        # Dual-write: espelha sempre no fallback local para o frontend ler imediatamente
        if trade_id:
            trade_data["id"] = trade_id
        trade_id = self._fallback.insert_trade(trade_data)
        return trade_id

    async def record_exit(
        self,
        trade_id: str,
        preco_saida: float,
        quantidade: float,
        motivo_saida: str,
        taxa_total: float = 0.002,  # 0.2% (maker+taker)
    ) -> float:
        """
        Registra o fechamento de um trade e calcula o PnL líquido.
        Retorna o PnL líquido em BRL.
        """
        now = datetime.now(timezone.utc).isoformat()

        # Busca preço de entrada
        preco_entrada = 0.0
        if self._use_supabase:
            try:
                result = (
                    self._table()
                    .select("preco_entrada")
                    .eq("id", trade_id)
                    .execute()
                )
                if result.data:
                    preco_entrada = float(result.data[0]["preco_entrada"])
            except Exception:
                pass

        if preco_entrada == 0.0:
            trade = next(
                (t for t in self._fallback._trades if t.get("id") == trade_id),
                None
            )
            preco_entrada = float(trade["preco_entrada"]) if trade else 0.0

        # PnL Líquido = (Saída - Entrada) * Qtd - Taxas
        pnl_bruto = (preco_saida - preco_entrada) * quantidade
        custo_taxas = (preco_entrada * quantidade + preco_saida * quantidade) * (taxa_total / 2)
        pnl_liquido = pnl_bruto - custo_taxas

        updates = {
            "timestamp_out": now,
            "preco_saida": preco_saida,
            "pnl_liquido": round(pnl_liquido, 4),
            "motivo_saida": motivo_saida,
        }

        if self._use_supabase:
            try:
                self._table().update(updates).eq("id", trade_id).execute()
                logger.info("[PERSIST] Trade atualizado no Supabase | ID: %s", trade_id)
            except Exception as e:
                logger.error("[PERSIST] Erro ao atualizar Supabase: %s", e)

        # Dual-write: atualiza também no fallback local
        self._fallback.update_trade(trade_id, updates)

        logger.info(
            "[PERSIST] Trade fechado | PnL bruto: R$ %.4f | Taxas: R$ %.4f | PnL líquido: R$ %.4f",
            pnl_bruto, custo_taxas, pnl_liquido
        )
        return pnl_liquido

    async def get_open_trade(self, symbol: str) -> Optional[dict]:
        """
        Busca trade aberto (sem timestamp_out) para crash recovery.
        """
        if self._use_supabase:
            try:
                result = (
                    self._table()
                    .select("*")
                    .eq("symbol", symbol)
                    .is_("timestamp_out", "null")
                    .order("timestamp_in", desc=True)
                    .limit(1)
                    .execute()
                )
                if result.data:
                    return result.data[0]
            except Exception as e:
                logger.error("[PERSIST] Erro ao buscar trade aberto: %s", e)

        return self._fallback.get_open_trade(symbol)

    async def get_daily_pnl(self) -> float:
        """Retorna o PnL acumulado do dia (UTC)."""
        if self._use_supabase:
            try:
                hoje = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                result = (
                    self._table()
                    .select("pnl_liquido")
                    .gte("timestamp_out", f"{hoje}T00:00:00Z")
                    .not_.is_("pnl_liquido", "null")
                    .execute()
                )
                return sum(float(r["pnl_liquido"]) for r in result.data)
            except Exception as e:
                logger.error("[PERSIST] Erro ao buscar PnL diário: %s", e)

        return self._fallback.get_daily_pnl()
