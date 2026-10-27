import { NextResponse } from "next/server";
import fs from "fs";
import path from "path";


export async function GET() {
  try {
    const tradesPath = path.resolve(process.cwd(), "..", "logs", "trades.json");

    if (fs.existsSync(tradesPath)) {
      const data = fs.readFileSync(tradesPath, "utf-8");
      const trades = JSON.parse(data);
      return NextResponse.json({ trades });
    }

    // Se ainda não houver trades registrados, retorna lista vazia
    return NextResponse.json({ trades: [] });
  } catch (error: any) {
    return NextResponse.json(
      { error: error.message, trades: [] },
      { status: 500 }
    );
  }
}
