import { NextResponse } from "next/server";
import fs from "fs";
import path from "path";

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const limit = searchParams.get("limit") || "100";

    const supabaseUrl = process.env.SUPABASE_URL;
    const supabaseKey = process.env.SUPABASE_KEY;
    const supabaseSchema = process.env.SUPABASE_SCHEMA || "public";

    // 1. Tenta buscar direto do Supabase (REST API)
    if (supabaseUrl && supabaseKey) {
      try {
        const url = `${supabaseUrl.replace(/\/+$/, "")}/rest/v1/bot_trades?select=*&order=timestamp_in.desc&limit=${limit}`;
        const headers: Record<string, string> = {
          apikey: supabaseKey,
          Authorization: `Bearer ${supabaseKey}`,
          "Content-Type": "application/json",
        };
        if (supabaseSchema && supabaseSchema !== "public") {
          headers["Accept-Profile"] = supabaseSchema;
        }

        const res = await fetch(url, {
          method: "GET",
          headers,
          cache: "no-store",
        });

        if (res.ok) {
          const trades = await res.json();
          if (Array.isArray(trades) && trades.length > 0) {
            return NextResponse.json({ trades, source: "supabase" });
          }
        }
      } catch {
        // Fallback para arquivo local
      }
    }

    // 2. Fallback: Lê do arquivo local compartilhado logs/trades.json
    const logsDir = process.env.LOGS_DIR || "/app/logs";
    let tradesPath = path.join(logsDir, "trades.json");
    if (!fs.existsSync(tradesPath)) {
      tradesPath = path.resolve(process.cwd(), "..", "logs", "trades.json");
    }

    if (fs.existsSync(tradesPath)) {
      const data = fs.readFileSync(tradesPath, "utf-8");
      const parsed = JSON.parse(data);
      const trades = Array.isArray(parsed) ? parsed : [];
      if (trades.length > 0) {
        return NextResponse.json({ trades, source: "local_file" });
      }
    }

    // 3. Retorna lista vazia se ainda não houver execuções
    return NextResponse.json({ trades: [], source: "empty" });
  } catch (error: any) {
    return NextResponse.json(
      { error: error?.message || "Erro desconhecido", trades: [] },
      { status: 500 }
    );
  }
}
