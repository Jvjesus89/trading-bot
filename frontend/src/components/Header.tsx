"use client";

import React from "react";
import { Activity, ShieldCheck, Zap, RefreshCw, Radio } from "lucide-react";

interface HeaderProps {
  symbol: string;
  mode: string;
  price: number;
  online: boolean;
  onRefresh: () => void;
  loading: boolean;
}

export const Header: React.FC<HeaderProps> = ({
  symbol,
  mode,
  price,
  online,
  onRefresh,
  loading,
}) => {
  return (
    <header className="glass-panel" style={{ padding: "16px 24px", marginBottom: "20px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "16px" }}>
        
        {/* Brand & Ticker */}
        <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
          <div style={{
            width: "44px",
            height: "44px",
            borderRadius: "12px",
            background: "linear-gradient(135deg, #00f0ff 0%, #8a2be2 100%)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            boxShadow: "var(--shadow-glow-cyan)"
          }}>
            <Zap size={24} color="#06090e" strokeWidth={2.5} />
          </div>

          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
              <h1 style={{ fontSize: "1.25rem", fontWeight: 800, letterSpacing: "-0.5px" }}>
                AETHER QUANT
              </h1>
              <span className={`badge ${mode === "LIVE" ? "badge-green" : "badge-amber"}`}>
                {mode === "LIVE" ? "LIVE SPOT" : "PAPER TRADING"}
              </span>
              <span className={`badge ${online ? "badge-green" : "badge-red"}`}>
                <Radio size={12} className={online ? "pulse-active" : ""} />
                {online ? "MOTOR ATIVO" : "OFFLINE / SYNC"}
              </span>
            </div>
            <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginTop: "2px" }}>
              Dual-Speed Engine // Binance Spot Reversion Strategy // Gemini Flash L2
            </p>
          </div>
        </div>

        {/* Ticker & Controls */}
        <div style={{ display: "flex", alignItems: "center", gap: "24px" }}>
          {price > 0 && (
            <div style={{ textAlign: "right" }}>
              <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.5px" }}>
                Preço Atual {symbol}
              </div>
              <div className="mono" style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--accent-cyan)" }}>
                R$ {price.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 4 })}
              </div>
            </div>
          )}

          <button
            onClick={onRefresh}
            disabled={loading}
            style={{
              background: "var(--bg-card-inner)",
              border: "1px solid var(--border-subtle)",
              color: "var(--text-main)",
              padding: "10px 16px",
              borderRadius: "10px",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: "8px",
              fontSize: "0.85rem",
              fontWeight: 600,
              transition: "all 0.2s ease"
            }}
            onMouseOver={(e) => (e.currentTarget.style.borderColor = "var(--accent-cyan)")}
            onMouseOut={(e) => (e.currentTarget.style.borderColor = "var(--border-subtle)")}
          >
            <RefreshCw size={16} className={loading ? "pulse-active" : ""} />
            Atualizar
          </button>
        </div>

      </div>
    </header>
  );
};
