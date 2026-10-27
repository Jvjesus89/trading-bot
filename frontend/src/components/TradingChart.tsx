"use client";

import React, { useEffect, useRef } from "react";
import {
  createChart,
  IChartApi,
  ISeriesApi,
  CandlestickSeries,
  LineSeries,
  CandlestickData,
  LineData,
  ColorType,
} from "lightweight-charts";
import { BarChart3 } from "lucide-react";

interface CandleItem {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

interface Indicators {
  bbUpper: { time: number; value: number }[];
  bbMiddle: { time: number; value: number }[];
  bbLower: { time: number; value: number }[];
  rsi: { time: number; value: number }[];
  ema: { time: number; value: number }[];
}

interface TradingChartProps {
  candles: CandleItem[];
  indicators: Indicators | null;
  symbol: string;
  entryPrice?: number;
  stopLoss?: number;
  takeProfit?: number;
}

export const TradingChart: React.FC<TradingChartProps> = ({
  candles,
  indicators,
  symbol,
  entryPrice,
  stopLoss,
  takeProfit,
}) => {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const rsiContainerRef = useRef<HTMLDivElement>(null);

  const mainChartRef = useRef<IChartApi | null>(null);
  const rsiChartRef = useRef<IChartApi | null>(null);

  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const bbUpperSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const bbMiddleSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const bbLowerSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const emaSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const rsiSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);

  // 1. Inicializa os gráficos uma única vez
  useEffect(() => {
    if (!chartContainerRef.current || !rsiContainerRef.current) return;

    const chartOptions = {
      layout: {
        background: { type: ColorType.Solid, color: "#080c14" },
        textColor: "#8492a6",
        fontSize: 12,
        fontFamily: "'JetBrains Mono', monospace",
      },
      grid: {
        vertLines: { color: "rgba(255, 255, 255, 0.04)" },
        horzLines: { color: "rgba(255, 255, 255, 0.04)" },
      },
      crosshair: {
        vertLine: { color: "#00f0ff", width: 1 as const, style: 2 },
        horzLine: { color: "#00f0ff", width: 1 as const, style: 2 },
      },
      timeScale: {
        borderColor: "rgba(255, 255, 255, 0.08)",
        timeVisible: true,
        secondsVisible: false,
      },
      rightPriceScale: {
        borderColor: "rgba(255, 255, 255, 0.08)",
      },
    };

    // Main Chart
    const mainChart = createChart(chartContainerRef.current, {
      ...chartOptions,
      height: 380,
    });
    mainChartRef.current = mainChart;

    const candleSeries = mainChart.addSeries(CandlestickSeries, {
      upColor: "#00e676",
      downColor: "#ff3366",
      borderVisible: false,
      wickUpColor: "#00e676",
      wickDownColor: "#ff3366",
    });
    candleSeriesRef.current = candleSeries;

    const bbUpper = mainChart.addSeries(LineSeries, {
      color: "rgba(59, 130, 246, 0.7)",
      lineWidth: 1,
      lineStyle: 1,
      title: "BB Upper",
    });
    bbUpperSeriesRef.current = bbUpper;

    const bbMid = mainChart.addSeries(LineSeries, {
      color: "rgba(138, 43, 226, 0.6)",
      lineWidth: 1,
      title: "BB Mid",
    });
    bbMiddleSeriesRef.current = bbMid;

    const bbLow = mainChart.addSeries(LineSeries, {
      color: "rgba(0, 240, 255, 0.7)",
      lineWidth: 1,
      lineStyle: 1,
      title: "BB Lower",
    });
    bbLowerSeriesRef.current = bbLow;

    const ema = mainChart.addSeries(LineSeries, {
      color: "rgba(255, 179, 0, 0.8)",
      lineWidth: 2,
      title: "EMA",
    });
    emaSeriesRef.current = ema;

    // RSI Chart
    const rsiChart = createChart(rsiContainerRef.current, {
      ...chartOptions,
      height: 140,
    });
    rsiChartRef.current = rsiChart;

    const rsiSeries = rsiChart.addSeries(LineSeries, {
      color: "#00f0ff",
      lineWidth: 2,
      title: "RSI (14)",
    });
    rsiSeriesRef.current = rsiSeries;

    rsiSeries.createPriceLine({
      price: 32,
      color: "rgba(0, 230, 118, 0.7)",
      lineWidth: 1,
      lineStyle: 2,
      axisLabelVisible: true,
      title: "OVERSOLD (32)",
    });

    rsiSeries.createPriceLine({
      price: 70,
      color: "rgba(255, 51, 102, 0.7)",
      lineWidth: 1,
      lineStyle: 2,
      axisLabelVisible: true,
      title: "OVERBOUGHT (70)",
    });

    // Sincroniza eixos de tempo
    mainChart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
      if (range && rsiChartRef.current) {
        try {
          rsiChartRef.current.timeScale().setVisibleLogicalRange(range);
        } catch (_) {}
      }
    });

    rsiChart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
      if (range && mainChartRef.current) {
        try {
          mainChartRef.current.timeScale().setVisibleLogicalRange(range);
        } catch (_) {}
      }
    });

    // Resize observer
    const handleResize = () => {
      if (chartContainerRef.current && mainChartRef.current) {
        mainChartRef.current.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
      if (rsiContainerRef.current && rsiChartRef.current) {
        rsiChartRef.current.applyOptions({ width: rsiContainerRef.current.clientWidth });
      }
    };

    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      try {
        mainChart.remove();
      } catch (_) {}
      try {
        rsiChart.remove();
      } catch (_) {}
      mainChartRef.current = null;
      rsiChartRef.current = null;
    };
  }, []);

  // 2. Atualiza os dados das séries sempre que candles ou indicadores mudarem
  useEffect(() => {
    if (candleSeriesRef.current && candles && candles.length > 0) {
      try {
        candleSeriesRef.current.setData(candles as unknown as CandlestickData[]);
      } catch (_) {}
    }

    if (indicators) {
      if (bbUpperSeriesRef.current && indicators.bbUpper) {
        try {
          bbUpperSeriesRef.current.setData(indicators.bbUpper as LineData[]);
        } catch (_) {}
      }
      if (bbMiddleSeriesRef.current && indicators.bbMiddle) {
        try {
          bbMiddleSeriesRef.current.setData(indicators.bbMiddle as LineData[]);
        } catch (_) {}
      }
      if (bbLowerSeriesRef.current && indicators.bbLower) {
        try {
          bbLowerSeriesRef.current.setData(indicators.bbLower as LineData[]);
        } catch (_) {}
      }
      if (emaSeriesRef.current && indicators.ema) {
        try {
          emaSeriesRef.current.setData(indicators.ema as LineData[]);
        } catch (_) {}
      }
      if (rsiSeriesRef.current && indicators.rsi) {
        try {
          rsiSeriesRef.current.setData(indicators.rsi as LineData[]);
        } catch (_) {}
      }
    }
  }, [candles, indicators]);

  return (
    <div className="glass-panel" style={{ padding: "20px", marginBottom: "20px" }}>
      
      {/* Header do Gráfico */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px", flexWrap: "wrap", gap: "10px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <div style={{ background: "rgba(0, 240, 255, 0.12)", padding: "8px", borderRadius: "8px" }}>
            <BarChart3 size={20} color="var(--accent-cyan)" />
          </div>
          <div>
            <h3 style={{ fontSize: "1.05rem", fontWeight: 700 }}>
              Terminal Gráfico // {symbol} (5m)
            </h3>
            <p style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
              Candlesticks ao vivo + Bandas de Bollinger (20, 2.0) + EMA + RSI (14)
            </p>
          </div>
        </div>

        {/* Legenda de Indicadores */}
        <div style={{ display: "flex", alignItems: "center", gap: "14px", fontSize: "0.75rem", color: "var(--text-muted)" }}>
          <span style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <span style={{ width: "10px", height: "2px", background: "#00f0ff" }} /> BB Inf
          </span>
          <span style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <span style={{ width: "10px", height: "2px", background: "#3b82f6" }} /> BB Sup
          </span>
          <span style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <span style={{ width: "10px", height: "2px", background: "#ffb300" }} /> EMA
          </span>
          <span style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <span style={{ width: "10px", height: "2px", background: "#00e676" }} /> RSI &lt; 32
          </span>
        </div>
      </div>

      {/* Gráfico de Candlestick */}
      <div
        ref={chartContainerRef}
        style={{
          width: "100%",
          borderRadius: "10px",
          overflow: "hidden",
          border: "1px solid var(--border-subtle)",
          marginBottom: "12px",
        }}
      />

      {/* Sub-gráfico de RSI */}
      <div
        ref={rsiContainerRef}
        style={{
          width: "100%",
          borderRadius: "10px",
          overflow: "hidden",
          border: "1px solid var(--border-subtle)",
        }}
      />
    </div>
  );
};
