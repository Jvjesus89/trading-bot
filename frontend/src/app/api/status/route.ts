import { NextResponse } from "next/server";
import fs from "fs";
import path from "path";

export async function GET(request: Request) {
  try {
    const logsDir = process.env.LOGS_DIR || "/app/logs";
    let statePath = path.join(logsDir, "bot_state.json");

    if (!fs.existsSync(statePath)) {
      statePath = path.resolve(process.cwd(), "..", "logs", "bot_state.json");
    }

    if (fs.existsSync(statePath)) {
      const data = fs.readFileSync(statePath, "utf-8");
      const parsed = JSON.parse(data);
      return NextResponse.json({
        online: true,
        ...parsed,
      });
    }

    // Fallback se o bot ainda não iniciou ou não gerou o primeiro estado
    return NextResponse.json({
      online: false,
      message: "Aguardando inicialização do bot ou primeiro ciclo de telemetria.",
      timestamp: Date.now() / 1000,
      symbol: "SOL/BRL",
      mode: "PAPER",
      price: 0,
      risk: {
        operacional: true,
        motivo: "Inicializando",
        pnl_diario: 0.0,
        trades_hoje: 0,
        stops_consecutivos: 0,
        banca_atual: 100.0,
      },
      ia: {
        autorizado: false,
        nivel_risco: "ALTO",
        motivo: "Aguardando o primeiro setup técnico para auditar uma entrada.",
        timestamp: Date.now() / 1000,
        fonte: "pending",
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
        ia_authorized: false,
      },
    });
  } catch (error: any) {
    return NextResponse.json(
      { online: false, error: error?.message || "Erro interno" },
      { status: 500 }
    );
  }
}
