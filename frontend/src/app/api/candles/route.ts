import { NextResponse } from "next/server";


interface CandleItem {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const symbolParam = (searchParams.get("symbol") || "SOL/BRL").replace("/", "").toUpperCase();
    const interval = searchParams.get("interval") || "5m";
    const limit = searchParams.get("limit") || "120";

    // Consulta à API pública da Binance (sem autenticação necessária para klines)
    const url = `https://api.binance.com/api/v3/klines?symbol=${symbolParam}&interval=${interval}&limit=${limit}`;
    const res = await fetch(url, { next: { revalidate: 0 } });

    if (!res.ok) {
      throw new Error(`Binance API error: ${res.statusText}`);
    }

    const rawData = await res.json();

    // Formata candles para a biblioteca de gráficos
    const candles: CandleItem[] = rawData.map((item: any) => ({
      time: Math.floor(item[0] / 1000), // timestamp em segundos (UTC)
      open: parseFloat(item[1]),
      high: parseFloat(item[2]),
      low: parseFloat(item[3]),
      close: parseFloat(item[4]),
      volume: parseFloat(item[5]),
    }));

    // Calcula Bollinger Bands (20, 2.0)
    const bbPeriod = 20;
    const bbStd = 2.0;
    const bbUpper: { time: number; value: number }[] = [];
    const bbMiddle: { time: number; value: number }[] = [];
    const bbLower: { time: number; value: number }[] = [];

    for (let i = bbPeriod - 1; i < candles.length; i++) {
      const slice = candles.slice(i - bbPeriod + 1, i + 1).map((c) => c.close);
      const mean = slice.reduce((a, b) => a + b, 0) / bbPeriod;
      const variance = slice.reduce((a, b) => a + Math.pow(b - mean, 2), 0) / bbPeriod;
      const std = Math.sqrt(variance);

      bbMiddle.push({ time: candles[i].time, value: parseFloat(mean.toFixed(4)) });
      bbUpper.push({ time: candles[i].time, value: parseFloat((mean + std * bbStd).toFixed(4)) });
      bbLower.push({ time: candles[i].time, value: parseFloat((mean - std * bbStd).toFixed(4)) });
    }

    // Calcula RSI (14)
    const rsiPeriod = 14;
    const rsiData: { time: number; value: number }[] = [];

    let gains: number[] = [];
    let losses: number[] = [];

    for (let i = 1; i < candles.length; i++) {
      const diff = candles[i].close - candles[i - 1].close;
      gains.push(diff > 0 ? diff : 0);
      losses.push(diff < 0 ? Math.abs(diff) : 0);

      if (i >= rsiPeriod) {
        const avgGain = gains.slice(-rsiPeriod).reduce((a, b) => a + b, 0) / rsiPeriod;
        const avgLoss = losses.slice(-rsiPeriod).reduce((a, b) => a + b, 0) / rsiPeriod;

        if (avgLoss === 0) {
          rsiData.push({ time: candles[i].time, value: 100 });
        } else {
          const rs = avgGain / avgLoss;
          const rsi = 100 - 100 / (1 + rs);
          rsiData.push({ time: candles[i].time, value: parseFloat(rsi.toFixed(2)) });
        }
      }
    }

    // Calcula EMA 200 aproximada se houver histórico suficiente ou EMA curta de referência
    const emaPeriod = 20;
    const emaData: { time: number; value: number }[] = [];
    if (candles.length >= emaPeriod) {
      const k = 2 / (emaPeriod + 1);
      let ema = candles.slice(0, emaPeriod).reduce((a, b) => a + b.close, 0) / emaPeriod;
      emaData.push({ time: candles[emaPeriod - 1].time, value: parseFloat(ema.toFixed(4)) });

      for (let i = emaPeriod; i < candles.length; i++) {
        ema = candles[i].close * k + ema * (1 - k);
        emaData.push({ time: candles[i].time, value: parseFloat(ema.toFixed(4)) });
      }
    }

    return NextResponse.json({
      candles,
      indicators: {
        bbUpper,
        bbMiddle,
        bbLower,
        rsi: rsiData,
        ema: emaData,
      },
    });
  } catch (error: any) {
    return NextResponse.json(
      { error: error.message, candles: [], indicators: null },
      { status: 500 }
    );
  }
}
