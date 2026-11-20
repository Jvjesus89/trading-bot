"use client";

import React from "react";
import { Bot, CheckCircle2, XCircle, Sparkles, AlertCircle, Clock, KeyRound } from "lucide-react";

interface AIMetrics {
  preco?: number;
  rsi?: number;
  rvol?: number;
  btc_trend_4h?: number;
}

interface AIData {
  autorizado: boolean;
  nivel_risco: string;
  motivo: string;
  timestamp: number;
  // Origem do veredito: "deepseek" (modelo real), "disabled" (configuração),
  // "missing_key" (sem chave), "error" (API indisponível) ou "pending".
  fonte?: string;
  modelo?: string;
  metricas?: AIMetrics;
}

interface AIAdvisorCardProps {
  ia: AIData;
}

export const AIAdvisorCard: React.FC<AIAdvisorCardProps> = ({ ia }) => {
  const isAuth = ia?.autorizado ?? false;
  const fonte = ia?.fonte ?? "pending";
  const isDeepSeek = fonte === "deepseek";
  const isDisabled = fonte === "disabled";
  const isMissingKey = fonte === "missing_key";
  const isPending = fonte === "pending";
  const isFailure = !isDeepSeek && !isDisabled && !isMissingKey && !isPending;
  const metricas = ia?.metricas;

  const accent = isDisabled || isMissingKey
    ? "rgba(110, 120, 140, 0.30)"
    : isPending
      ? "rgba(0, 240, 255, 0.18)"
      : isFailure
        ? "rgba(255, 176, 32, 0.35)"
        : isAuth
          ? "rgba(0, 240, 255, 0.25)"
          : "rgba(255, 51, 102, 0.35)";
  const glow = isDisabled || isMissingKey
    ? "rgba(110, 120, 140, 0.12)"
    : isPending
      ? "rgba(0, 240, 255, 0.10)"
      : isFailure
        ? "rgba(255, 176, 32, 0.15)"
        : isAuth
          ? "rgba(0, 240, 255, 0.15)"
          : "rgba(255, 51, 102, 0.15)";
  const timeFormatted = ia?.timestamp
    ? new Date(ia.timestamp * 1000).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" })
    : "--:--:--";

  const subtitle = isDisabled
    ? "Validação desativada — PAPER opera sem auditoria; LIVE bloqueia por segurança."
    : isMissingKey
      ? "DEEPSEEK_API_KEY ausente — PAPER opera sem auditoria; LIVE bloqueia por segurança."
      : isPending
        ? "Aguardando o primeiro setup técnico para auditar uma entrada."
        : isFailure
          ? "DeepSeek indisponível — entradas bloqueadas por segurança (fail-closed)."
          : "Audita cada compra com RSI, RVOL e tendência do BTC 4h antes de executar.";

  const reasonLabel = isDeepSeek
    ? "Justificativa do Modelo"
    : isFailure
      ? "Falha na auditoria"
      : "Estado da Auditoria";

  return (
    <div className="glass-panel" style={{
      padding: "20px",
      marginBottom: "20px",
      border: `1px solid ${accent}`,
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
        background: `radial-gradient(circle, ${glow} 0%, transparent 70%)`,
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
            <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
              <h2 style={{ fontSize: "1.05rem", fontWeight: 700, letterSpacing: "-0.3px" }}>
                Auditor de Entrada (DeepSeek)
              </h2>
              <span className="badge badge-cyan" style={{ fontSize: "0.68rem" }}>
                <Sparkles size={11} /> POR ENTRADA
              </span>
              {ia?.modelo && (
                <span className="mono" style={{ fontSize: "0.66rem", color: "var(--text-dim)" }}>
                  {ia.modelo}
                </span>
              )}
            </div>
            <p style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
              {subtitle}
            </p>
          </div>
        </div>

        {/* Status de Autorização e Risco */}
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          {isDisabled || isMissingKey ? (
            <span className="badge" style={{ fontSize: "0.8rem", padding: "6px 14px", background: "rgba(110, 120, 140, 0.15)", color: "var(--text-muted)", border: "1px solid rgba(110, 120, 140, 0.3)" }}>
              {isMissingKey ? <KeyRound size={14} /> : <Bot size={14} />}
              {isMissingKey ? "CHAVE AUSENTE" : "IA DESATIVADA"}
            </span>
          ) : isPending ? (
            <span className="badge badge-amber" style={{ fontSize: "0.8rem", padding: "6px 14px" }}>
              <Clock size={14} />
              AGUARDANDO SINAL
            </span>
          ) : isFailure ? (
            <span className="badge badge-amber" style={{ fontSize: "0.8rem", padding: "6px 14px" }}>
              <AlertCircle size={14} />
              FALHA NA IA
            </span>
          ) : (
            <span className={`badge ${isAuth ? "badge-green" : "badge-red"}`} style={{ fontSize: "0.8rem", padding: "6px 14px" }}>
              {isAuth ? <CheckCircle2 size={14} /> : <XCircle size={14} />}
              {isAuth ? "ENTRADA AUTORIZADA" : "ENTRADA BLOQUEADA"}
            </span>
          )}

          {isDeepSeek && (
            <span className={`badge ${
              ia.nivel_risco === "BAIXO" ? "badge-green" : ia.nivel_risco === "MEDIO" ? "badge-amber" : "badge-red"
            }`} style={{ fontSize: "0.8rem", padding: "6px 12px" }}>
              RISCO {ia.nivel_risco || "NORMAL"}
            </span>
          )}
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
              {reasonLabel}
            </div>
            <div style={{ fontSize: "0.88rem", color: "var(--text-main)", marginTop: "2px", lineHeight: "1.4" }}>
              {ia.motivo || "Aguardando leitura do modelo..."}
            </div>

            {/* Métricas exatas enviadas ao modelo (RSI, RVOL e BTC 4h) */}
            {metricas && (isDeepSeek || isFailure) && (
              <div style={{ display: "flex", gap: "16px", flexWrap: "wrap", marginTop: "8px", fontSize: "0.74rem", color: "var(--text-muted)" }}>
                {metricas.rsi != null && (
                  <span>RSI 5m: <strong className="mono" style={{ color: "var(--text-main)" }}>{Number(metricas.rsi).toFixed(1)}</strong></span>
                )}
                {metricas.rvol != null && (
                  <span>RVOL: <strong className="mono" style={{ color: "var(--text-main)" }}>{Number(metricas.rvol).toFixed(2)}x</strong></span>
                )}
                {metricas.btc_trend_4h != null && (
                  <span>BTC 4h: <strong className="mono" style={{ color: Number(metricas.btc_trend_4h) < -1.5 ? "var(--trade-red)" : "var(--text-main)" }}>{Number(metricas.btc_trend_4h) >= 0 ? "+" : ""}{Number(metricas.btc_trend_4h).toFixed(2)}%</strong></span>
                )}
                {metricas.preco != null && (
                  <span>Preço: <strong className="mono" style={{ color: "var(--text-main)" }}>R$ {Number(metricas.preco).toFixed(4)}</strong></span>
                )}
              </div>
            )}
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
