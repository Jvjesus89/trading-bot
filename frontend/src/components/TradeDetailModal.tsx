"use client";

import React from "react";
import { X, Bot, Shield, CheckCircle2, AlertTriangle } from "lucide-react";

interface Trade {
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

interface TradeDetailModalProps {
  trade: Trade | null;
  onClose: () => void;
}

export const TradeDetailModal: React.FC<TradeDetailModalProps> = ({ trade, onClose }) => {
  if (!trade) return null;

  const ia = trade.ia_snapshot || {};
  const isAuth = ia?.autorizado ?? false;
  const metricas = ia?.metricas || null;
  const metricItems = metricas
    ? [
        { label: "RSI 5m", value: metricas.rsi != null ? Number(metricas.rsi).toFixed(1) : "--" },
        { label: "RVOL", value: metricas.rvol != null ? `${Number(metricas.rvol).toFixed(2)}x` : "--" },
        {
          label: "BTC 4h",
          value: metricas.btc_trend_4h != null
            ? `${Number(metricas.btc_trend_4h) >= 0 ? "+" : ""}${Number(metricas.btc_trend_4h).toFixed(2)}%`
            : "--",
        },
        { label: "Preço", value: metricas.preco != null ? `R$ ${Number(metricas.preco).toFixed(4)}` : "--" },
      ]
    : [];

  return (
    <div style={{
      position: "fixed",
      top: 0,
      left: 0,
      width: "100vw",
      height: "100vh",
      background: "rgba(0, 0, 0, 0.75)",
      backdropFilter: "blur(8px)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      zIndex: 9999,
      padding: "20px"
    }}>
      <div className="glass-panel" style={{
        maxWidth: "600px",
        width: "100%",
        padding: "24px",
        borderRadius: "16px",
        border: "1px solid rgba(0, 240, 255, 0.3)",
        position: "relative"
      }}>
        {/* Botão Fechar */}
        <button
          onClick={onClose}
          style={{
            position: "absolute",
            top: "16px",
            right: "16px",
            background: "transparent",
            border: "none",
            color: "var(--text-muted)",
            cursor: "pointer",
            padding: "4px"
          }}
        >
          <X size={20} />
        </button>

        {/* Header do Modal */}
        <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "20px" }}>
          <div style={{
            background: "linear-gradient(135deg, #00f0ff 0%, #8a2be2 100%)",
            padding: "10px",
            borderRadius: "10px"
          }}>
            <Bot size={22} color="#06090e" strokeWidth={2.5} />
          </div>
          <div>
            <h3 style={{ fontSize: "1.15rem", fontWeight: 700 }}>
              Auditoria de IA // Trade {trade.id.slice(0, 8)}...
            </h3>
            <p style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
              Snapshot exato das métricas enviadas ao DeepSeek e do veredito que autorizou esta entrada
            </p>
          </div>
        </div>

        {/* Resumo do Trade */}
        <div style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "10px",
          marginBottom: "16px",
          background: "var(--bg-card-inner)",
          padding: "12px 16px",
          borderRadius: "10px",
          fontSize: "0.82rem"
        }}>
          <div>
            <span style={{ color: "var(--text-muted)" }}>Entrada: </span>
            <span className="mono" style={{ color: "var(--text-main)", fontWeight: 600 }}>R$ {Number(trade.preco_entrada).toFixed(4)}</span>
          </div>
          <div>
            <span style={{ color: "var(--text-muted)" }}>Saída: </span>
            <span className="mono" style={{ color: "var(--text-main)", fontWeight: 600 }}>
              {trade.preco_saida ? `R$ ${Number(trade.preco_saida).toFixed(4)}` : "Em Aberto"}
            </span>
          </div>
          <div>
            <span style={{ color: "var(--text-muted)" }}>Resultado Líquido: </span>
            <span className="mono" style={{
              fontWeight: 700,
              color: (trade.pnl_liquido ?? 0) >= 0 ? "var(--trade-green)" : "var(--trade-red)"
            }}>
              {trade.pnl_liquido != null ? `R$ ${Number(trade.pnl_liquido).toFixed(2)}` : "--"}
            </span>
          </div>
          <div>
            <span style={{ color: "var(--text-muted)" }}>Motivo de Saída: </span>
            <span className="badge badge-cyan" style={{ fontSize: "0.68rem" }}>
              {trade.motivo_saida || "POSICIONADO"}
            </span>
          </div>
        </div>

        {/* Veredito da IA */}
        <div style={{
          border: "1px solid var(--border-subtle)",
          borderRadius: "10px",
          padding: "14px",
          marginBottom: "16px",
          background: "rgba(10, 15, 24, 0.7)"
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
            <span style={{ fontSize: "0.8rem", color: "var(--text-muted)", fontWeight: 600 }}>
              {ia?.fonte === "deepseek"
                ? `Veredito do DeepSeek${ia?.modelo ? ` (${ia.modelo})` : ""}`
                : "Auditoria da Entrada"}
            </span>
            <span className={`badge ${isAuth ? "badge-green" : "badge-red"}`}>
              {isAuth ? <CheckCircle2 size={12} /> : <AlertTriangle size={12} />}
              {ia.nivel_risco || "NORMAL"}
            </span>
          </div>
          <p style={{ fontSize: "0.88rem", color: "var(--text-main)", lineHeight: "1.4" }}>
            "{ia.motivo || "Sem justificativa registrada para esta entrada."}"
          </p>

          {metricItems.length > 0 && (
            <div style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(110px, 1fr))",
              gap: "8px",
              marginTop: "12px",
              borderTop: "1px solid var(--border-subtle)",
              paddingTop: "12px"
            }}>
              {metricItems.map((item) => (
                <div key={item.label}>
                  <div style={{ fontSize: "0.68rem", color: "var(--text-dim)", textTransform: "uppercase" }}>
                    {item.label}
                  </div>
                  <div className="mono" style={{ fontSize: "0.85rem", color: "var(--text-main)", fontWeight: 600 }}>
                    {item.value}
                  </div>
                </div>
              ))}
            </div>
          )}

          {ia?.fonte && ia.fonte !== "deepseek" && (
            <div style={{ fontSize: "0.7rem", color: "var(--trade-amber)", marginTop: "10px" }}>
              {ia.fonte === "disabled"
                ? "Validação de IA desativada — esta entrada não passou pelo modelo."
                : ia.fonte === "missing_key"
                  ? "DEEPSEEK_API_KEY ausente — esta entrada não passou pelo modelo."
                  : "Falha na auditoria de IA — entrada registrada sem aprovação do modelo."}
            </div>
          )}
        </div>

        {/* JSON Raw Snapshot */}
        <div>
          <div style={{ fontSize: "0.75rem", color: "var(--text-dim)", marginBottom: "6px", textTransform: "uppercase", fontWeight: 600 }}>
            Payload Raw Retornado (JSONB)
          </div>
          <pre className="mono" style={{
            background: "#05070b",
            border: "1px solid var(--border-subtle)",
            borderRadius: "8px",
            padding: "12px",
            fontSize: "0.75rem",
            color: "var(--accent-cyan)",
            maxHeight: "160px",
            overflowY: "auto",
            lineHeight: "1.5"
          }}>
            {JSON.stringify(ia, null, 2)}
          </pre>
        </div>
      </div>
    </div>
  );
};
