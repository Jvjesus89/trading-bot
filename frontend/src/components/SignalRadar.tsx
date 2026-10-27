"use client";

import React from "react";
import { Check, X, Crosshair, HelpCircle } from "lucide-react";

interface SignalsData {
  ema200_trend: boolean;
  bb_lower_touch: boolean;
  rsi_oversold: boolean;
  rvol_confirmed: boolean;
  ia_authorized: boolean;
}

interface IndicatorsData {
  rsi: number;
  bb_upper: number;
  bb_middle: number;
  bb_lower: number;
  atr: number;
  rvol: number;
  ema_200: number | null;
}

interface SignalRadarProps {
  signals: SignalsData;
  indicators: IndicatorsData;
  currentPrice: number;
}

export const SignalRadar: React.FC<SignalRadarProps> = ({ signals, indicators, currentPrice }) => {
  const rules = [
    {
      id: "ema",
      title: "1. Filtro de Tendência (1h)",
      desc: "Preço de fechamento 1h > EMA 200",
      active: signals.ema200_trend,
      currentValue: indicators.ema_200 ? `EMA 200: R$ ${indicators.ema_200.toFixed(2)}` : "Calculando...",
      target: "Preço acima da EMA",
    },
    {
      id: "bb",
      title: "2. Exaustão de Curto Prazo (5m)",
      desc: "Preço toca ou rompe Banda Inferior",
      active: signals.bb_lower_touch,
      currentValue: `BB Inf: R$ ${indicators.bb_lower.toFixed(2)}`,
      target: "Preço ≤ BB Inferior",
    },
    {
      id: "rsi",
      title: "3. Sobrevenda Extrema (5m)",
      desc: "RSI (14) < 32",
      active: signals.rsi_oversold,
      currentValue: `RSI Atual: ${indicators.rsi.toFixed(1)}`,
      target: "RSI < 32.0",
    },
    {
      id: "rvol",
      title: "4. Confirmação de Liquidez",
      desc: "Volume Relativo RVOL > 1.0",
      active: signals.rvol_confirmed,
      currentValue: `RVOL: ${indicators.rvol.toFixed(2)}x`,
      target: "RVOL > 1.0x da média",
    },
    {
      id: "ia",
      title: "5. Auditoria Gemini Flash",
      desc: "Validação macroeconômica e sem cascata",
      active: signals.ia_authorized,
      currentValue: signals.ia_authorized ? "Autorizado" : "Bloqueado",
      target: "Veredito = true",
    },
  ];

  const activeCount = rules.filter((r) => r.active).length;
  const isReadyToShoot = activeCount === 5;

  return (
    <div className="glass-panel" style={{ padding: "20px", marginBottom: "20px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px", flexWrap: "wrap", gap: "10px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <div style={{
            background: isReadyToShoot ? "var(--trade-green-bg)" : "rgba(0, 240, 255, 0.12)",
            padding: "8px",
            borderRadius: "8px"
          }}>
            <Crosshair size={20} color={isReadyToShoot ? "var(--trade-green)" : "var(--accent-cyan)"} />
          </div>
          <div>
            <h3 style={{ fontSize: "1.05rem", fontWeight: 700 }}>
              Radar de Gatilhos de Entrada (5 Condições Simultâneas)
            </h3>
            <p style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
              Para disparar compra a mercado (R$ 25), todas as 5 regras devem estar verdes.
            </p>
          </div>
        </div>

        {/* Contador de Gatilhos Ativos */}
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <span className={`badge ${isReadyToShoot ? "badge-green" : activeCount >= 3 ? "badge-amber" : "badge-cyan"}`} style={{ fontSize: "0.85rem", padding: "6px 14px" }}>
            {activeCount}/5 CONDIÇÕES ATENDIDAS
          </span>
        </div>
      </div>

      {/* Grid de Regras */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))",
        gap: "12px"
      }}>
        {rules.map((rule) => (
          <div
            key={rule.id}
            style={{
              background: rule.active ? "rgba(0, 230, 118, 0.06)" : "var(--bg-card-inner)",
              border: `1px solid ${rule.active ? "rgba(0, 230, 118, 0.3)" : "var(--border-subtle)"}`,
              borderRadius: "10px",
              padding: "14px",
              transition: "all 0.2s ease"
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "8px" }}>
              <span style={{ fontSize: "0.78rem", fontWeight: 700, color: rule.active ? "var(--trade-green)" : "var(--text-muted)" }}>
                {rule.title}
              </span>
              <div style={{
                width: "22px",
                height: "22px",
                borderRadius: "50%",
                background: rule.active ? "var(--trade-green)" : "rgba(255, 255, 255, 0.08)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0
              }}>
                {rule.active ? (
                  <Check size={14} color="#06090e" strokeWidth={3} />
                ) : (
                  <X size={14} color="var(--text-dim)" strokeWidth={2.5} />
                )}
              </div>
            </div>

            <div className="mono" style={{ fontSize: "0.85rem", fontWeight: 600, color: "var(--text-main)", marginBottom: "4px" }}>
              {rule.currentValue}
            </div>

            <div style={{ fontSize: "0.7rem", color: "var(--text-dim)" }}>
              Alvo: {rule.target}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
