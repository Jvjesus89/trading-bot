"""
Integração com Google Gemini Flash — Camada de Contexto IA (Slow Loop).
Atua como Auditor de Risco Sistêmico: autoriza ou bloqueia operações
com base em métricas de derivativos e sentimento macro.
"""

import json
import logging
import re
import time
import asyncio
from dataclasses import dataclass, field
from typing import Optional

import httpx

from . import config

logger = logging.getLogger(__name__)

# Número máximo de tentativas para a API do Gemini
_MAX_RETRIES = 3
# Backoff: 5s, 15s, 30s — mais conservador para não esgotar quota
_RETRY_DELAYS = [5.0, 15.0, 30.0]

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

# Regex para extrair JSON de dentro de blocos markdown (```json ... ```)
_JSON_CODE_BLOCK_RE = re.compile(
    r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE
)


def _extract_json(text: str) -> dict:
    """
    Tenta parsear JSON diretamente; se falhar, procura dentro de blocos
    de código markdown (```json ... ```) antes de desistir.
    """
    # Tentativa 1: parse direto
    text_stripped = text.strip()
    try:
        return json.loads(text_stripped)
    except json.JSONDecodeError:
        pass

    # Tentativa 2: extrai de bloco markdown
    match = _JSON_CODE_BLOCK_RE.search(text_stripped)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Tentativa 3: procura a primeira ocorrência de { ... } no texto
    brace_start = text_stripped.find("{")
    brace_end = text_stripped.rfind("}")
    if brace_start != -1 and brace_end > brace_start:
        try:
            return json.loads(text_stripped[brace_start : brace_end + 1])
        except json.JSONDecodeError:
            pass

    raise json.JSONDecodeError("Nenhum JSON válido encontrado na resposta", text, 0)


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

        # Constrói URL dinamicamente para sempre refletir o modelo configurado
        api_url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{config.gemini.model}:generateContent?key={config.gemini.api_key}"
        )

        try:
            last_error: Optional[Exception] = None
            for attempt in range(1, _MAX_RETRIES + 1):
                try:
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        response = await client.post(api_url, json=request_body)
                        response.raise_for_status()

                    data = response.json()
                    # Extrai o texto gerado
                    generated_text = (
                        data.get("candidates", [{}])[0]
                        .get("content", {})
                        .get("parts", [{}])[0]
                        .get("text", "")
                    )

                    # Parse defensivo: aceita JSON puro ou envolto em markdown
                    result = _extract_json(generated_text)

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
                    status_code = e.response.status_code
                    if status_code == 404:
                        logger.error(
                            "[IA] HTTP 404: modelo '%s' não encontrado. "
                            "Verifique GEMINI_MODEL no .env ou o default em config.py.",
                            config.gemini.model
                        )
                        break  # Retry não resolve um modelo inexistente
                    if status_code in (429, 500, 503) and attempt < _MAX_RETRIES:
                        wait = _RETRY_DELAYS[attempt - 1]
                        logger.warning(
                            "[IA] Erro HTTP %d na API do Gemini (tentativa %d/%d). Aguardando %.0fs...",
                            status_code, attempt, _MAX_RETRIES, wait
                        )
                        await asyncio.sleep(wait)
                        last_error = e
                        continue
                    logger.error(
                        "[IA] Erro HTTP %d na API do Gemini (modelo: %s): %s",
                        status_code, config.gemini.model, e.response.text[:300]
                    )
                    last_error = e
                    break

                except json.JSONDecodeError as e:
                    logger.error("[IA] Resposta do Gemini não é JSON válido: %s", e)
                    last_error = e
                    break

                except Exception as e:
                    if attempt < _MAX_RETRIES:
                        wait = _RETRY_DELAYS[attempt - 1]
                        logger.warning(
                            "[IA] Erro na consulta ao Gemini (tentativa %d/%d). Aguardando %.0fs: %s",
                            attempt, _MAX_RETRIES, wait, e
                        )
                        await asyncio.sleep(wait)
                        last_error = e
                        continue
                    logger.error("[IA] Erro na consulta ao Gemini após %d tentativas: %s", _MAX_RETRIES, e)
                    last_error = e
                    break

        except Exception as e:
            logger.error("[IA] Erro inesperado no bloco de retry: %s", e)

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
            motivo="Fail-Safe (Live): falha na comunicação com Gemini",
            timestamp=time.time(),
        )
        self._last_verdict = fail_verdict
        return fail_verdict
