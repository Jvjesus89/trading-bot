"use client";

import React, { useState, useEffect, useCallback } from "react";
import { Header } from "../components/Header";
import { MetricCards } from "../components/MetricCards";
import { AIAdvisorCard } from "../components/AIAdvisorCard";
import { SignalRadar } from "../components/SignalRadar";
import { TradingChart } from "../components/TradingChart";
import { TradesTable } from "../components/TradesTable";

export default function Dashboard() {
  const [status, setStatus] = useState<any>({
    online: false,
    symbol: "SOL/BRL",
    mode: "PAPER",
    price: 0,
    risk: {
      operacional: true,
      motivo: "Inicializando motor...",
      pnl_diario: 0.0,
      trades_hoje: 0,
      stops_consecutivos: 0,
      banca_atual: 100.0,
    },
    ia: {
      autorizado: true,
      nivel_risco: "BAIXO",
      motivo: "Aguardando leitura de contexto...",
      timestamp: 0,
    },
    position: null,
    indicators: {
      rsi: 50,
      bb_upper: 0,
      bb_middle: 0,
      bb_lower: 0,
      atr: 0,
      rvol: 1.0,
      ema_200: 0,
    },
    signals: {
      ema200_trend: false,
      bb_lower_touch: false,
      rsi_oversold: false,
      rvol_confirmed: false,
      ia_authorized: true,
    },
  });

  const [trades, setTrades] = useState<any[]>([]);
  const [marketData, setMarketData] = useState<{ candles: any[]; indicators: any }>({
    candles: [],
    indicators: null,
  });
  const [loading, setLoading] = useState(false);

  // Busca status do bot
  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch("/api/status");
      if (res.ok) {
        const data = await res.json();
        setStatus(data);
      }
    } catch (err) {
      console.error("Erro ao buscar status:", err);
    }
  }, []);

  // Busca histórico de trades
  const fetchTrades = useCallback(async () => {
    try {
      const res = await fetch("/api/trades");
      if (res.ok) {
        const data = await res.json();
        setTrades(data.trades || []);
      }
    } catch (err) {
      console.error("Erro ao buscar trades:", err);
    }
  }, []);

  // Busca candles da Binance
  const fetchCandles = useCallback(async () => {
    try {
      const res = await fetch(`/api/candles?symbol=${status.symbol || "SOL/BRL"}&interval=5m&limit=100`);
      if (res.ok) {
        const data = await res.json();
        setMarketData(data);
      }
    } catch (err) {
      console.error("Erro ao buscar candles:", err);
    }
  }, [status.symbol]);

  // Atualização manual via botão
  const handleManualRefresh = async () => {
    setLoading(true);
    await Promise.all([fetchStatus(), fetchTrades(), fetchCandles()]);
    setLoading(false);
  };

  // Efeito de inicialização e polling contínuo em tempo real
  useEffect(() => {
    handleManualRefresh();

    // Polling rápido de status (a cada 3s)
    const statusInterval = setInterval(fetchStatus, 3000);

    // Polling de candles e trades (a cada 8s)
    const marketInterval = setInterval(() => {
      fetchCandles();
      fetchTrades();
    }, 8000);

    return () => {
      clearInterval(statusInterval);
      clearInterval(marketInterval);
    };
  }, [fetchStatus, fetchTrades, fetchCandles]);

  const currentPrice = status.price > 0 ? status.price : marketData.candles.slice(-1)[0]?.close || 0;

  return (
    <main style={{ maxWidth: "1440px", margin: "0 auto", padding: "20px 24px 60px" }}>
      
      {/* 1. Header do Painel */}
      <Header
        symbol={status.symbol || "SOL/BRL"}
        mode={status.mode || "PAPER"}
        price={currentPrice}
        online={status.online}
        onRefresh={handleManualRefresh}
        loading={loading}
      />

      {/* 2. Top Metric Cards (Banca, PnL, Posição, Circuit Breaker) */}
      <MetricCards
        risk={status.risk}
        position={status.position}
        currentPrice={currentPrice}
      />

      {/* 3. Card de Auditoria Macro de IA (Gemini Flash) */}
      <AIAdvisorCard ia={status.ia} />

      {/* 4. Radar dos 5 Gatilhos de Entrada */}
      <SignalRadar
        signals={status.signals}
        indicators={status.indicators}
        currentPrice={currentPrice}
      />

      {/* 5. Terminal Gráfico de Candlesticks + Bollinger + RSI */}
      <TradingChart
        candles={marketData.candles}
        indicators={marketData.indicators}
        symbol={status.symbol || "SOL/BRL"}
        entryPrice={status.position?.preco_entrada}
        stopLoss={status.position?.stop_loss}
        takeProfit={status.position?.take_profit}
      />

      {/* 6. Livro de Registros: Compras e Vendas */}
      <TradesTable trades={trades} />

      {/* Footer com versão e status */}
      <footer style={{
        marginTop: "40px",
        textAlign: "center",
        fontSize: "0.75rem",
        color: "var(--text-dim)",
        borderTop: "1px solid var(--border-subtle)",
        paddingTop: "20px"
      }}>
        AETHER QUANT v2.0 // Binance Spot High Performance Engine // Dual-Speed Asynchronous Loop
      </footer>

    </main>
  );
}
