"""
Integração com Google Gemini Flash — Camada de Contexto IA (Slow Loop).
Atua como Auditor de Risco Sistêmico: autoriza ou bloqueia operações
com base em métricas de derivativos e sentimento macro.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx

from . import config

logger = logging.getLogger(__name__)

# Prompt de sistema para o Gemini — define o contrato de resposta
_SYSTEM_PROMPT = """Você é um auditor de risco sistêmico para um robô de day trade em criptomoedas na Binance Spot.

Seu papel NÃO é prever preço. Seu papel é identificar anomalias estruturais no mercado que quebram
a matemática de uma estratégia de reversão à média.

Você receberá 3 métricas:
1. Variação do BTC nas últimas 4h (em %)
2. Funding Rate do mercado de futuros
3. ATR de 1h do ativo-alvo (volatilidade)

Com base nessas métricas, responda ESTRITAMENTE no formato JSON abaixo.
Não inclua markdown, blocos de código ou qualquer texto fora do JSON.

{
  "autorizado": true ou false,
  "nivel_risco": "BAIXO" ou "MEDIO" ou "ALTO" ou "CRITICO",
  "motivo": "Explicação curta e objetiva da sua análise (máximo 120 caracteres)"
}

Regras de decisão:
- autorizado = false se: BTC caiu mais de 3% em 4h, OU funding rate > 0.05% (cascata de liquidação iminente), OU ATR está 3x acima da média normal (choque de volatilidade).
- autorizado = true em todos os outros casos.
- nivel_risco CRITICO bloqueia automaticamente as operações.
"""


@dataclass
class AIVerdict:
    """Resultado da análise da IA."""
    autorizado: bool = False
    nivel_risco: str = "ALTO"
    motivo: str = "Fail-Safe: resposta padrão bloqueante"
    timestamp: float = 0.0
    raw_response: Optional[str] = None

    def is_stale(self, max_age_seconds: int = 3600) -> bool:
        """Verifica se a leitura está obsoleta (mais de 1h por padrão)."""
        return (time.time() - self.timestamp) > max_age_seconds

    def to_dict(self) -> dict:
        """Serializa para armazenamento/log."""
        return {
            "autorizado": self.autorizado,
            "nivel_risco": self.nivel_risco,
            "motivo": self.motivo,
            "timestamp": self.timestamp,
        }


class AIAdvisor:
    """
    Gerencia consultas periódicas ao Gemini Flash.
    Implementa Fail-Safe: se a resposta falhar, bloqueia operações.
    """

    def __init__(self):
        self._last_verdict: AIVerdict = AIVerdict()  # Começa bloqueado (fail-safe)
        self._api_url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{config.gemini.model}:generateContent?key={config.gemini.api_key}"
        )

    @property
    def last_verdict(self) -> AIVerdict:
        """Retorna o último veredito da IA."""
        return self._last_verdict

    @property
    def is_authorized(self) -> bool:
        """Atalho: a IA autoriza operações?"""
        return self._last_verdict.autorizado and not self._last_verdict.is_stale()

    async def consult(
        self,
        btc_variation_4h: float,
        funding_rate: float,
        atr_1h: float,
    ) -> AIVerdict:
        """
        Submete payload ao Gemini e interpreta a resposta.
        Em caso de qualquer falha, retorna veredito bloqueante (fail-safe).
        """
        payload_text = (
            f"Métricas atuais para análise:\n"
            f"- Variação BTC (4h): {btc_variation_4h:+.2f}%\n"
            f"- Funding Rate: {funding_rate:.4f}%\n"
            f"- ATR 1h do ativo: {atr_1h:.4f}"
        )

        request_body = {
            "system_instruction": {
                "parts": [{"text": _SYSTEM_PROMPT}]
            },
            "contents": [
                {
                    "parts": [{"text": payload_text}]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 256,
                "responseMimeType": "application/json",
            }
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(self._api_url, json=request_body)
                response.raise_for_status()

            data = response.json()
            # Extrai o texto gerado
            generated_text = (
                data.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
            )

            # Parse do JSON retornado
            result = json.loads(generated_text)

            verdict = AIVerdict(
                autorizado=bool(result.get("autorizado", False)),
                nivel_risco=str(result.get("nivel_risco", "ALTO")),
                motivo=str(result.get("motivo", "Resposta sem motivo")),
                timestamp=time.time(),
                raw_response=generated_text,
            )

            logger.info(
                "[IA] Veredito: autorizado=%s | risco=%s | motivo=%s",
                verdict.autorizado, verdict.nivel_risco, verdict.motivo
            )
            self._last_verdict = verdict
            return verdict

        except httpx.HTTPStatusError as e:
            logger.error("[IA] Erro HTTP %d na API do Gemini: %s", e.response.status_code, e.response.text[:200])
        except json.JSONDecodeError as e:
            logger.error("[IA] Resposta do Gemini não é JSON válido: %s", e)
        except Exception as e:
            logger.error("[IA] Erro na consulta ao Gemini: %s", e)

        # Fallback inteligente:
        # Se for modo PAPER, usa auditoria heurística local com base nas métricas macro
        if config.is_paper():
            btc_ok = btc_variation_4h > -3.0
            funding_ok = funding_rate < 0.05
            paper_auth = btc_ok and funding_ok
            paper_verdict = AIVerdict(
                autorizado=paper_auth,
                nivel_risco="BAIXO" if paper_auth else "ALTO",
                motivo=f"Fallback Macro (Paper): BTC 4h={btc_variation_4h:+.2f}%, Funding={funding_rate:.4f}%",
                timestamp=time.time(),
            )
            logger.warning("[IA] Usando auditoria heurística de fallback para PAPER: autorizado=%s", paper_auth)
            self._last_verdict = paper_verdict
            return paper_verdict

        # FAIL-SAFE ESTRITO EM LIVE: qualquer falha bloqueia
        fail_verdict = AIVerdict(
            autorizado=False,
            nivel_risco="CRITICO",
            motivo=f"Fail-Safe (Live): falha na comunicação com Gemini",
            timestamp=time.time(),
        )
        self._last_verdict = fail_verdict
        return fail_verdict
