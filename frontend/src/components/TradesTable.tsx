"use client";

import React, { useState } from "react";
import { History, ArrowUpRight, ArrowDownRight, Eye, ShieldCheck, Clock } from "lucide-react";
import { TradeDetailModal } from "./TradeDetailModal";

export interface Trade {
  id: string;
  timestamp_in: string;
  timestamp_out: string | null;
  symbol: string;
  preco_entrada: number;
  preco_saida: number | null;
  quantidade: number;
  pnl_liquido: number | null;
  motivo_saida: string | null;
  ia_snapshot: any;
}

interface TradesTableProps {
  trades: Trade[];
}

export const TradesTable: React.FC<TradesTableProps> = ({ trades }) => {
  const [selectedTrade, setSelectedTrade] = useState<Trade | null>(null);

  const formatDateTime = (isoString?: string | null) => {
    if (!isoString) return "--";
    const date = new Date(isoString);
    return date.toLocaleDateString("pt-BR", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  };

  const getBadgeStyle = (reason?: string | null) => {
    switch (reason) {
      case "TAKE_PROFIT":
        return "badge-green";
      case "TRAILING":
        return "badge-cyan";
      case "BREAKEVEN":
        return "badge-cyan";
      case "STOP_LOSS":
        return "badge-red";
      case "ORPHAN_RECOVERY":
        return "badge-amber";
      default:
        return "badge-amber";
    }
  };

  return (
    <div className="glass-panel" style={{ padding: "20px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px", flexWrap: "wrap", gap: "10px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <div style={{ background: "rgba(138, 43, 226, 0.15)", padding: "8px", borderRadius: "8px" }}>
            <History size={20} color="var(--accent-purple)" />
          </div>
          <div>
            <h3 style={{ fontSize: "1.05rem", fontWeight: 700 }}>
              Livro de Registros // Compras e Vendas
            </h3>
            <p style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
              Execuções registradas na base de dados com auditoria de slippage e taxas (0.2%)
            </p>
          </div>
        </div>

        <span className="badge badge-cyan">
          {trades.length} TRADES REGISTRADOS
        </span>
      </div>

      {trades.length === 0 ? (
        <div style={{
          textAlign: "center",
          padding: "48px 20px",
          color: "var(--text-muted)",
          background: "var(--bg-card-inner)",
          borderRadius: "10px",
          border: "1px dashed var(--border-subtle)"
        }}>
          <Clock size={36} color="var(--text-dim)" style={{ marginBottom: "12px" }} />
          <div style={{ fontSize: "1rem", fontWeight: 600, color: "var(--text-main)" }}>
            Nenhuma execução fechada até o momento
          </div>
          <p style={{ fontSize: "0.82rem", color: "var(--text-muted)", marginTop: "4px" }}>
            O robô está em vigilância ativa monitorando o order book a cada 10 segundos. Assim que as 5 condições forem confirmadas, o trade aparecerá aqui em tempo real.
          </p>
        </div>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left", fontSize: "0.85rem" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border-subtle)", color: "var(--text-muted)", fontSize: "0.75rem", textTransform: "uppercase" }}>
                <th style={{ padding: "12px 14px" }}>Horário (Entrada / Saída)</th>
                <th style={{ padding: "12px 14px" }}>Par</th>
                <th style={{ padding: "12px 14px" }}>Preço Compra</th>
                <th style={{ padding: "12px 14px" }}>Preço Venda</th>
                <th style={{ padding: "12px 14px" }}>Qtd Executada</th>
                <th style={{ padding: "12px 14px" }}>PnL Líquido</th>
                <th style={{ padding: "12px 14px" }}>Motivo Saída</th>
                <th style={{ padding: "12px 14px", textAlign: "center" }}>Auditoria IA</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((trade) => {
                const isProfit = (trade.pnl_liquido ?? 0) >= 0;
                const pnlPct = trade.preco_entrada && trade.preco_saida
                  ? ((trade.preco_saida - trade.preco_entrada) / trade.preco_entrada) * 100
                  : 0;

                return (
                  <tr
                    key={trade.id}
                    style={{
                      borderBottom: "1px solid rgba(255, 255, 255, 0.04)",
                      transition: "background 0.2s ease"
                    }}
                    onMouseOver={(e) => (e.currentTarget.style.background = "rgba(255, 255, 255, 0.02)")}
                    onMouseOut={(e) => (e.currentTarget.style.background = "transparent")}
                  >
                    <td style={{ padding: "14px" }}>
                      <div style={{ color: "var(--text-main)", fontWeight: 500 }}>
                        {formatDateTime(trade.timestamp_in)}
                      </div>
                      <div style={{ fontSize: "0.72rem", color: "var(--text-dim)" }}>
                        {trade.timestamp_out ? formatDateTime(trade.timestamp_out) : "Posição Ativa"}
                      </div>
                    </td>

                    <td className="mono" style={{ padding: "14px", fontWeight: 700, color: "var(--accent-cyan)" }}>
                      {trade.symbol}
                    </td>

                    <td className="mono" style={{ padding: "14px" }}>
                      R$ {Number(trade.preco_entrada).toFixed(4)}
                    </td>

                    <td className="mono" style={{ padding: "14px" }}>
                      {trade.preco_saida ? `R$ ${Number(trade.preco_saida).toFixed(4)}` : "--"}
                    </td>

                    <td className="mono" style={{ padding: "14px", color: "var(--text-muted)" }}>
                      {Number(trade.quantidade).toFixed(6)}
                    </td>

                    <td className="mono" style={{ padding: "14px" }}>
                      {trade.pnl_liquido != null ? (
                        <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                          {isProfit ? <ArrowUpRight size={16} color="var(--trade-green)" /> : <ArrowDownRight size={16} color="var(--trade-red)" />}
                          <span style={{ fontWeight: 700, color: isProfit ? "var(--trade-green)" : "var(--trade-red)" }}>
                            {isProfit ? "+" : ""}R$ {Number(trade.pnl_liquido).toFixed(2)}
                          </span>
                          <span style={{ fontSize: "0.72rem", color: isProfit ? "var(--trade-green)" : "var(--trade-red)" }}>
                            ({isProfit ? "+" : ""}{pnlPct.toFixed(2)}%)
                          </span>
                        </div>
                      ) : (
                        <span style={{ color: "var(--trade-amber)" }}>Em Aberto</span>
                      )}
                    </td>

                    <td style={{ padding: "14px" }}>
                      <span className={`badge ${getBadgeStyle(trade.motivo_saida)}`}>
                        {trade.motivo_saida || "POSICIONADO"}
                      </span>
                    </td>

                    <td style={{ padding: "14px", textAlign: "center" }}>
                      <button
                        onClick={() => setSelectedTrade(trade)}
                        style={{
                          background: "var(--bg-card-inner)",
                          border: "1px solid var(--border-subtle)",
                          color: "var(--accent-cyan)",
                          padding: "6px 12px",
                          borderRadius: "6px",
                          cursor: "pointer",
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "6px",
                          fontSize: "0.75rem",
                          fontWeight: 600,
                          transition: "all 0.2s ease"
                        }}
                        onMouseOver={(e) => (e.currentTarget.style.borderColor = "var(--accent-cyan)")}
                        onMouseOut={(e) => (e.currentTarget.style.borderColor = "var(--border-subtle)")}
                      >
                        <Eye size={13} />
                        Auditar
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Modal de Auditoria IA */}
      <TradeDetailModal trade={selectedTrade} onClose={() => setSelectedTrade(null)} />
    </div>
  );
};
