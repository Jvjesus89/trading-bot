import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AETHER QUANT // Motor de Alta Performance (Binance Spot)",
  description: "Painel quantitativo institucional com execução dual-speed, indicadores em tempo real e auditoria macro via Gemini Flash.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  );
}
