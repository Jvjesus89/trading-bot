-- ============================================
-- Schema: trading_bot (Supabase / PostgreSQL)
-- Execute este script no Supabase SQL Editor
-- ============================================

-- 1. Cria o schema trading_bot se não existir
CREATE SCHEMA IF NOT EXISTS trading_bot;

-- 2. Tabela principal em trading_bot
CREATE TABLE IF NOT EXISTS trading_bot.bot_trades (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp_in    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    timestamp_out   TIMESTAMPTZ,
    symbol          VARCHAR(20) NOT NULL,
    preco_entrada   NUMERIC(18, 4) NOT NULL,
    preco_saida     NUMERIC(18, 4),
    quantidade      NUMERIC(18, 8) NOT NULL,
    pnl_liquido     NUMERIC(10, 4),
    motivo_saida    VARCHAR(30),
    ia_snapshot     JSONB
);

-- 3. Índices de alta performance
CREATE INDEX IF NOT EXISTS idx_trades_symbol_open
    ON trading_bot.bot_trades (symbol, timestamp_in)
    WHERE timestamp_out IS NULL;

CREATE INDEX IF NOT EXISTS idx_trades_timestamp_out
    ON trading_bot.bot_trades (timestamp_out)
    WHERE timestamp_out IS NOT NULL;

-- 4. Permissões para o PostgREST / Supabase API
GRANT USAGE ON SCHEMA trading_bot TO anon, authenticated, service_role;
GRANT ALL ON ALL TABLES IN SCHEMA trading_bot TO anon, authenticated, service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA trading_bot TO anon, authenticated, service_role;

-- 5. View espelho no schema public (garante resolução imediata do PostgREST)
CREATE OR REPLACE VIEW public.bot_trades AS 
SELECT * FROM trading_bot.bot_trades;

GRANT ALL ON public.bot_trades TO anon, authenticated, service_role;
