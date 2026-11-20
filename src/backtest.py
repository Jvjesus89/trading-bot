"""
Backtest — compara a estratégia ORIGINAL com a v2 em dados históricos reais da Binance.

Usa a MESMA lógica do bot ao vivo (compute_signal_frame + Position.update_dynamic_stops),
com taxas e spread incluídos.

Uso (na pasta do projeto, com o venv ativo):
    python -m src.backtest                       # 90 dias de SOL/BRL
    python -m src.backtest --dias 180 --spread 0.12
    python -m src.backtest --symbol SOL/USDT --dias 120

Limitações (leia antes de confiar nos números):
- Simula em candles de 5m: dentro de um candle, assume que a mínima vem ANTES da
  máxima (conservador para stops). O bot real olha o preço a cada 10s.
- A versão ORIGINAL decidia no candle ainda em formação; aqui ela é avaliada no
  fechamento, o que tende a deixá-la MELHOR do que foi na prática.
- Resultado passado não garante resultado futuro. Poucos trades = pouca confiança.
"""

import argparse
import logging
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from . import config
from .indicators import compute_signal_frame, compute_ema, compute_atr
from .strategy import Position

logging.basicConfig(level=logging.WARNING)
CACHE_DIR = Path(__file__).resolve().parent.parent / "logs" / "backtest"


# ----------------------------------------------------------------------
# Dados
# ----------------------------------------------------------------------

def baixar_ohlcv(symbol: str, timeframe: str, desde_ms: int) -> pd.DataFrame:
    """Baixa candles paginando a API pública da Binance (com cache em CSV)."""
    import ccxt

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    nome = f"{symbol.replace('/', '')}_{timeframe}_{desde_ms}.csv"
    cache = CACHE_DIR / nome
    if cache.exists() and (time.time() - cache.stat().st_mtime) < 6 * 3600:
        df = pd.read_csv(cache, index_col=0, parse_dates=True)
        return df

    ex = ccxt.binance({"enableRateLimit": True, "options": {"defaultType": "spot"}})
    tf_ms = ex.parse_timeframe(timeframe) * 1000
    linhas, since = [], desde_ms
    while True:
        lote = ex.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
        if not lote:
            break
        linhas.extend(lote)
        since = lote[-1][0] + tf_ms
        if len(lote) < 1000 or since >= ex.milliseconds():
            break
    df = pd.DataFrame(linhas, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df = df.drop_duplicates("timestamp")
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df.set_index("timestamp").astype(float)
    # Descarta o último candle (em formação)
    df = df.iloc[:-1]
    df.to_csv(cache)
    return df


# ----------------------------------------------------------------------
# Simulação
# ----------------------------------------------------------------------

def _alinhar_1h(serie_1h: pd.Series, idx_5m: pd.DatetimeIndex) -> np.ndarray:
    """
    Alinha uma série de 1h aos candles de 5m sem olhar o futuro:
    o valor de um candle 1h só fica disponível quando ele FECHA.
    """
    disponivel = serie_1h.copy()
    disponivel.index = disponivel.index + pd.Timedelta(hours=1)
    fechamento_5m = idx_5m + pd.Timedelta(minutes=5)
    alinhado = disponivel.reindex(disponivel.index.union(fechamento_5m)).ffill()
    return alinhado.reindex(fechamento_5m).to_numpy()


def simular(df5: pd.DataFrame, df1h: pd.DataFrame, btc1h, cfg, spread_pct: float) -> pd.DataFrame:
    config.trading = cfg  # strategy/indicators leem config.trading em tempo de execução
    f = compute_signal_frame(df5)

    # Filtros de 1h (tendência + macro)
    ema = compute_ema(df1h["close"], cfg.ema_period)
    tendencia = _alinhar_1h((df1h["close"] > ema).astype(float), df5.index)
    atr1 = compute_atr(df1h, cfg.atr_period)
    mediana = atr1.rolling(100).median().shift(1)
    choque = _alinhar_1h((atr1 >= cfg.atr_choque_mult * mediana).astype(float), df5.index)
    if btc1h is not None and len(btc1h) > 5:
        var4h = (btc1h["close"] - btc1h["open"].shift(4)) / btc1h["open"].shift(4) * 100
        btc_ok = _alinhar_1h((var4h > cfg.btc_queda_max_4h).astype(float), df5.index)
    else:
        btc_ok = np.ones(len(df5))

    sinal = (
        f["bb_touch"].to_numpy() & f["rsi_ok"].to_numpy() & f["rvol_ok"].to_numpy()
        & f["reversao"].to_numpy() & f["alvo_ok"].to_numpy()
        & (np.nan_to_num(tendencia) == 1) & (np.nan_to_num(choque) == 0)
        & (np.nan_to_num(btc_ok, nan=1) == 1)
    )

    o, h, l, c = (f[k].to_numpy() for k in ("open", "high", "low", "close"))
    atr, mid = f["atr"].to_numpy(), f["bb_middle"].to_numpy()
    idx = df5.index
    hs = spread_pct / 100 / 2          # meio spread: compra no ask, vende no bid
    fee = cfg.taxa_por_lado

    banca = cfg.banca_inicial
    trades, pos, entrada_i = [], None, 0
    cooldown_ate = idx[0]
    stops_seguidos, dia, pnl_dia, dia_bloqueado = 0, None, 0.0, False
    aquecimento = max(cfg.bb_period, cfg.rsi_period * 3, cfg.rvol_period) + 2

    def fechar(i, preco_saida, motivo):
        nonlocal banca, pos, stops_seguidos, cooldown_ate, pnl_dia, dia_bloqueado
        q = pos.quantidade
        pnl = q * (preco_saida - pos.preco_entrada) - fee * q * (pos.preco_entrada + preco_saida)
        banca += pnl
        pnl_dia += pnl
        trades.append({
            "entrada": idx[entrada_i], "saida": idx[i], "preco_entrada": pos.preco_entrada,
            "preco_saida": preco_saida, "motivo": motivo, "pnl_brl": pnl,
            "pnl_pct": pnl / pos.custo_total * 100, "duracao_min": (i - entrada_i) * 5,
            "banca": banca,
        })
        if motivo == "STOP_LOSS":
            stops_seguidos += 1
            if stops_seguidos >= cfg.cooldown_stops_consecutivos:
                cooldown_ate = idx[i] + pd.Timedelta(hours=cfg.cooldown_horas)
                stops_seguidos = 0
        else:
            stops_seguidos = 0
        if pnl_dia <= -banca * cfg.drawdown_diario_max:
            dia_bloqueado = True
        pos = None

    for i in range(aquecimento, len(f) - 1):
        d = idx[i].date()
        if d != dia:
            dia, pnl_dia, dia_bloqueado = d, 0.0, False

        if pos is not None:
            bid_o, bid_l, bid_h, bid_c = o[i] - o[i] * hs, l[i] - l[i] * hs, h[i] - h[i] * hs, c[i] - c[i] * hs
            stop_antes = pos.stop_loss
            if bid_o <= stop_antes:                      # gap abaixo do stop
                fechar(i, bid_o, pos.update_dynamic_stops(bid_o).value)
                continue
            motivo = pos.update_dynamic_stops(bid_l)     # mínima primeiro (conservador)
            if motivo:
                fechar(i, stop_antes, motivo.value)
                continue
            pos.update_dynamic_stops(bid_h)              # depois a máxima (promove stops)
            if bid_c <= pos.stop_loss:                   # devolveu no mesmo candle
                motivo = pos.update_dynamic_stops(bid_c)
                fechar(i, pos.stop_loss, motivo.value if motivo else "STOP_LOSS")
            continue

        if sinal[i] and not dia_bloqueado and idx[i] >= cooldown_ate and atr[i] > 0:
            preco = o[i + 1] * (1 + hs)                  # entra na abertura seguinte, no ask
            valor = banca * cfg.ordem_percentual
            if valor < cfg.min_notional:
                continue
            pos = Position(
                symbol=cfg.symbol, preco_entrada=preco, quantidade=valor / preco,
                atr_entrada=atr[i], timestamp_in=0, stop_loss=preco - cfg.sl_atr_mult * atr[i],
                take_profit=preco + cfg.tp_atr_mult * atr[i], highest_price=preco,
            )
            if cfg.alvo_na_media and mid[i] > preco * (1 + cfg.custo_ida_volta):
                pos.take_profit = mid[i]
            entrada_i = i + 1

    return pd.DataFrame(trades)


# ----------------------------------------------------------------------
# Relatório
# ----------------------------------------------------------------------

def resumo(nome: str, t: pd.DataFrame, banca0: float, dias: int) -> dict:
    if t.empty:
        return {"versão": nome, "trades": 0}
    ganhos, perdas = t[t.pnl_brl > 0], t[t.pnl_brl <= 0]
    curva = pd.concat([pd.Series([banca0]), t["banca"]]).reset_index(drop=True)
    dd = ((curva - curva.cummax()) / curva.cummax()).min() * 100
    pf = ganhos.pnl_brl.sum() / abs(perdas.pnl_brl.sum()) if len(perdas) and perdas.pnl_brl.sum() else float("inf")
    return {
        "versão": nome,
        "trades": len(t),
        "trades/dia": round(len(t) / dias, 2),
        "acerto %": round(len(ganhos) / len(t) * 100, 1),
        "ganho médio %": round(ganhos.pnl_pct.mean(), 3) if len(ganhos) else 0,
        "perda média %": round(perdas.pnl_pct.mean(), 3) if len(perdas) else 0,
        "profit factor": round(pf, 2),
        "resultado R$": round(t.pnl_brl.sum(), 2),
        "resultado % banca": round(t.pnl_brl.sum() / banca0 * 100, 2),
        "max drawdown %": round(dd, 2),
    }


def main():
    ap = argparse.ArgumentParser(description="Backtest: estratégia original vs v2")
    ap.add_argument("--symbol", default=config.trading.symbol)
    ap.add_argument("--dias", type=int, default=90)
    ap.add_argument("--spread", type=float, default=0.10, help="spread médio em %% (ex.: 0.10)")
    args = ap.parse_args()

    base = replace(config.trading, symbol=args.symbol)
    original = replace(
        base, exigir_reversao=False, alvo_na_media=False, min_alvo_mult_custo=0.0,
        min_rr=0.0, be_fee_offset=0.0015, be_min_mult_custo=0.0, trailing_atr_mult=1.0,
    )
    v2 = base

    agora = int(time.time() * 1000)
    desde5 = agora - args.dias * 86_400_000
    desde1h = desde5 - 260 * 3_600_000   # aquecimento da EMA 200
    print(f"Baixando {args.symbol} ({args.dias} dias)...")
    df5 = baixar_ohlcv(args.symbol, "5m", desde5)
    df1h = baixar_ohlcv(args.symbol, "1h", desde1h)
    quote = args.symbol.split("/")[1]
    try:
        btc1h = baixar_ohlcv(f"BTC/{quote}", "1h", desde1h)
    except Exception as e:
        print(f"Aviso: sem dados de BTC/{quote} ({e}); filtro de BTC desligado.")
        btc1h = None
    print(f"{len(df5)} candles de 5m | {df5.index[0]} → {df5.index[-1]}")

    linhas = []
    for nome, cfg in (("ORIGINAL", original), ("V2", v2)):
        t = simular(df5, df1h, btc1h, cfg, args.spread)
        linhas.append(resumo(nome, t, cfg.banca_inicial, args.dias))
        if not t.empty:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            t.to_csv(CACHE_DIR / f"trades_{nome.lower()}.csv", index=False)
            print(f"\n{nome} — resultado por tipo de saída:")
            print(t.groupby("motivo").agg(qtd=("pnl_brl", "size"), pnl_brl=("pnl_brl", "sum"),
                                          pnl_medio_pct=("pnl_pct", "mean")).round(3).to_string())

    bh = (df5["close"].iloc[-1] / df5["close"].iloc[0] - 1) * 100
    print("\n" + "=" * 70)
    print(pd.DataFrame(linhas).set_index("versão").T.to_string())
    print("=" * 70)
    print(f"Referência — só segurar {args.symbol} no período: {bh:+.2f}% "
          f"(o bot usa {base.ordem_percentual:.0%} da banca por trade)")
    print(f"Trades salvos em: {CACHE_DIR}")


if __name__ == "__main__":
    main()
