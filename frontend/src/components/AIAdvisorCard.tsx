"use client";

import React from "react";
import { Bot, CheckCircle2, XCircle, Sparkles, AlertCircle, Clock } from "lucide-react";

interface AIData {
  autorizado: boolean;
  nivel_risco: string;
  motivo: string;
  timestamp: number;
}

interface AIAdvisorCardProps {
  ia: AIData;
}

export const AIAdvisorCard: React.FC<AIAdvisorCardProps> = ({ ia }) => {
  const isAuth = ia?.autorizado ?? false;
  const timeFormatted = ia?.timestamp
    ? new Date(ia.timestamp * 1000).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" })
    : "--:--:--";

  return (
    <div className="glass-panel" style={{
      padding: "20px",
      marginBottom: "20px",
      border: `1px solid ${isAuth ? "rgba(0, 240, 255, 0.25)" : "rgba(255, 51, 102, 0.35)"}`,
      background: "linear-gradient(145deg, rgba(13, 19, 29, 0.85) 0%, rgba(10, 15, 24, 0.95) 100%)",
      position: "relative",
      overflow: "hidden"
    }}>
      {/* Glow de fundo */}
      <div style={{
        position: "absolute",
        top: "-50px",
        right: "-50px",
        width: "150px",
        height: "150px",
        background: isAuth ? "radial-gradient(circle, rgba(0, 240, 255, 0.15) 0%, transparent 70%)" : "radial-gradient(circle, rgba(255, 51, 102, 0.15) 0%, transparent 70%)",
        pointerEvents: "none"
      }} />

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "12px", marginBottom: "14px" }}>
        
        {/* Título & Badge de IA */}
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <div style={{
            background: "linear-gradient(135deg, #8a2be2 0%, #00f0ff 100%)",
            padding: "8px",
            borderRadius: "10px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center"
          }}>
            <Bot size={20} color="#06090e" strokeWidth={2.5} />
          </div>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <h2 style={{ fontSize: "1.05rem", fontWeight: 700, letterSpacing: "-0.3px" }}>
                Auditor de Risco Sistêmico (Gemini Flash L2)
              </h2>
              <span className="badge badge-cyan" style={{ fontSize: "0.68rem" }}>
                <Sparkles size={11} /> 30 MIN SLOW LOOP
              </span>
            </div>
            <p style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
              Avalia choque macroeconômico, funding rate e risco de cascata de liquidação.
            </p>
          </div>
        </div>

        {/* Status de Autorização e Risco */}
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <span className={`badge ${isAuth ? "badge-green" : "badge-red"}`} style={{ fontSize: "0.8rem", padding: "6px 14px" }}>
            {isAuth ? <CheckCircle2 size={14} /> : <XCircle size={14} />}
            {isAuth ? "OPERAÇÕES AUTORIZADAS" : "OPERAÇÕES BLOQUEADAS"}
          </span>

          <span className={`badge ${
            ia.nivel_risco === "BAIXO" ? "badge-green" : ia.nivel_risco === "MEDIO" ? "badge-amber" : "badge-red"
          }`} style={{ fontSize: "0.8rem", padding: "6px 12px" }}>
            RISCO {ia.nivel_risco || "NORMAL"}
          </span>
        </div>

      </div>

      {/* Motivo e Justificativa */}
      <div style={{
        background: "var(--bg-card-inner)",
        border: "1px solid var(--border-subtle)",
        borderRadius: "10px",
        padding: "14px 18px",
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        flexWrap: "wrap",
        gap: "12px"
      }}>
        <div style={{ display: "flex", alignItems: "flex-start", gap: "10px", flex: 1, minWidth: "280px" }}>
          <AlertCircle size={18} color="var(--accent-cyan)" style={{ marginTop: "2px", flexShrink: 0 }} />
          <div>
            <div style={{ fontSize: "0.72rem", color: "var(--text-dim)", textTransform: "uppercase", fontWeight: 600 }}>
              Justificativa Técnica do Modelo
            </div>
            <div style={{ fontSize: "0.88rem", color: "var(--text-main)", marginTop: "2px", lineHeight: "1.4" }}>
              {ia.motivo || "Aguardando leitura do modelo..."}
            </div>
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "6px", color: "var(--text-dim)", fontSize: "0.75rem" }}>
          <Clock size={14} />
          Última auditoria: <span className="mono" style={{ color: "var(--text-muted)" }}>{timeFormatted}</span>
        </div>
      </div>

    </div>
  );
};
