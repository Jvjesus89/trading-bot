"use client";

import React from "react";
import { Wallet, TrendingUp, TrendingDown, ShieldAlert, Target, AlertTriangle } from "lucide-react";

interface RiskData {
  operacional: boolean;
  motivo: string;
  pnl_diario: number;
  trades_hoje: number;
  stops_consecutivos: number;
  banca_atual: number;
}

interface PositionData {
  symbol: string;
  preco_entrada: number;
  preco_atual: number;
  quantidade: number;
  stop_loss: number;
  take_profit: number;
  stop_state: string;
  highest_price: number;
  timestamp_in: number;
  lucro_flutuante_brl: number;
  lucro_flutuante_pct: number;
}

interface MetricCardsProps {
  risk: RiskData;
  position: PositionData | null;
  currentPrice: number;
}

export const MetricCards: React.FC<MetricCardsProps> = ({ risk, position, currentPrice }) => {
  const pnlIsPositive = risk.pnl_diario >= 0;
  const maxDrawdownLimit = 6.0; // R$ 6.00 (-6%)
  const drawdownUsedPct = Math.min(100, Math.max(0, (Math.abs(Math.min(0, risk.pnl_diario)) / maxDrawdownLimit) * 100));

  return (
    <div style={{
      display: "grid",
      gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
      gap: "16px",
      marginBottom: "20px"
    }}>
      
      {/* CARD 1: BANCA ATUAL */}
      <div className="glass-panel" style={{ padding: "18px 20px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "8px" }}>
          <span style={{ fontSize: "0.8rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 600 }}>
            Banca Atual
          </span>
          <div style={{ background: "rgba(59, 130, 246, 0.15)", padding: "8px", borderRadius: "8px" }}>
            <Wallet size={18} color="var(--accent-blue)" />
          </div>
        </div>
        <div className="mono" style={{ fontSize: "1.65rem", fontWeight: 700, color: "var(--text-main)" }}>
          R$ {risk.banca_atual.toFixed(2)}
        </div>
        <div style={{ fontSize: "0.78rem", color: "var(--text-dim)", marginTop: "6px" }}>
          Lote por Trade: <span className="mono" style={{ color: "var(--accent-cyan)", fontWeight: 600 }}>R$ {(risk.banca_atual * 0.25).toFixed(2)}</span> (25%)
        </div>
      </div>

      {/* CARD 2: PnL DIÁRIO */}
      <div className="glass-panel" style={{
        padding: "18px 20px",
        borderColor: pnlIsPositive ? "rgba(0, 230, 118, 0.2)" : "rgba(255, 51, 102, 0.2)"
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "8px" }}>
          <span style={{ fontSize: "0.8rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 600 }}>
            Resultado do Dia (PnL)
          </span>
          <div style={{
            background: pnlIsPositive ? "var(--trade-green-bg)" : "var(--trade-red-bg)",
            padding: "8px",
            borderRadius: "8px"
          }}>
            {pnlIsPositive ? <TrendingUp size={18} color="var(--trade-green)" /> : <TrendingDown size={18} color="var(--trade-red)" />}
          </div>
        </div>

        <div className="mono" style={{
          fontSize: "1.65rem",
          fontWeight: 700,
          color: pnlIsPositive ? "var(--trade-green)" : "var(--trade-red)"
        }}>
          {pnlIsPositive ? "+" : ""}R$ {risk.pnl_diario.toFixed(2)}
        </div>

        {/* Barra de risco de Drawdown */}
        <div style={{ marginTop: "10px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: "4px" }}>
            <span>Limite Drawdown (-R$ {maxDrawdownLimit.toFixed(2)})</span>
            <span className="mono">{drawdownUsedPct.toFixed(0)}%</span>
          </div>
          <div style={{ width: "100%", height: "4px", background: "var(--bg-card-inner)", borderRadius: "2px", overflow: "hidden" }}>
            <div style={{
              width: `${drawdownUsedPct}%`,
              height: "100%",
              background: drawdownUsedPct > 70 ? "var(--trade-red)" : "var(--trade-amber)",
              transition: "width 0.3s ease"
            }} />
          </div>
        </div>
      </div>

      {/* CARD 3: POSIÇÃO ABERTA / TRADE EM ANDAMENTO */}
      <div className="glass-panel" style={{
        padding: "18px 20px",
        borderColor: position ? "rgba(0, 240, 255, 0.3)" : "var(--border-subtle)",
        background: position ? "rgba(0, 240, 255, 0.03)" : "var(--bg-card)"
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "8px" }}>
          <span style={{ fontSize: "0.8rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 600 }}>
            Posição no Mercado
          </span>
          <div style={{ background: "rgba(0, 240, 255, 0.12)", padding: "8px", borderRadius: "8px" }}>
            <Target size={18} color="var(--accent-cyan)" />
          </div>
        </div>

        {position ? (
          <div>
            <div style={{ display: "flex", alignItems: "baseline", gap: "8px" }}>
              <span className="mono" style={{
                fontSize: "1.4rem",
                fontWeight: 700,
                color: position.lucro_flutuante_brl >= 0 ? "var(--trade-green)" : "var(--trade-red)"
              }}>
                {position.lucro_flutuante_brl >= 0 ? "+" : ""}R$ {position.lucro_flutuante_brl.toFixed(2)}
              </span>
              <span className={`badge ${position.lucro_flutuante_pct >= 0 ? "badge-green" : "badge-red"}`} style={{ fontSize: "0.7rem", padding: "2px 6px" }}>
                {position.lucro_flutuante_pct >= 0 ? "+" : ""}{position.lucro_flutuante_pct.toFixed(2)}%
              </span>
            </div>
            <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "6px" }}>
              Stop ({position.stop_state}): <span className="mono" style={{ color: "var(--trade-amber)" }}>R$ {position.stop_loss.toFixed(2)}</span>
            </div>
          </div>
        ) : (
          <div>
            <div style={{ fontSize: "1.2rem", fontWeight: 700, color: "var(--text-muted)" }}>
              LIQUIDEZ / NEUTRO
            </div>
            <div style={{ fontSize: "0.75rem", color: "var(--text-dim)", marginTop: "8px" }}>
              Aguardando gatilho de reversão 5m
            </div>
          </div>
        )}
      </div>

      {/* CARD 4: CIRCUIT BREAKER & SEGURANÇA */}
      <div className="glass-panel" style={{ padding: "18px 20px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "8px" }}>
          <span style={{ fontSize: "0.8rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 600 }}>
            Circuit Breaker
          </span>
          <div style={{
            background: risk.operacional ? "var(--trade-green-bg)" : "var(--trade-red-bg)",
            padding: "8px",
            borderRadius: "8px"
          }}>
            {risk.operacional ? <ShieldAlert size={18} color="var(--trade-green)" /> : <AlertTriangle size={18} color="var(--trade-red)" />}
          </div>
        </div>

        <div style={{ fontSize: "1.2rem", fontWeight: 700, color: risk.operacional ? "var(--trade-green)" : "var(--trade-red)" }}>
          {risk.operacional ? "OPERACIONAL" : "BLOQUEADO"}
        </div>

        <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "6px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {risk.operacional ? `Stops Seguidos: ${risk.stops_consecutivos}/2 | Trades: ${risk.trades_hoje}` : risk.motivo}
        </div>
      </div>

    </div>
  );
};
