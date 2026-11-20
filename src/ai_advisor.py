"""
Auditor de Entrada via DeepSeek — valida cada COMPRA antes da execução.

Diferente do antigo slow loop macro (que liberava/bloqueava o robô inteiro a
cada 30 min), esta camada audita a entrada específica: preço, RSI (5m), RVOL e
a tendência do BTC (4h). O veredito é gravado no trade (`ia_snapshot`), então o
botão "Auditar" do painel mostra exatamente o que o modelo viu e decidiu.

Política de falha (importante):
- AI_VALIDATION_ENABLED=false  -> PAPER libera, LIVE bloqueia (nunca sem auditor).
- Chave ausente                -> PAPER segue sem auditoria (fonte "missing_key"),
                                  LIVE bloqueia.
- Erro/timeout/HTTP != 200/JSON inválido -> bloqueia a entrada (fail-closed),
  conforme a regra de segurança operacional.
"""

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx

from . import config

logger = logging.getLogger(__name__)

# Cache curto do último veredito: o setup técnico pode ficar verde por vários
# ciclos de 10s. Sem isso o robô chamaria a API (e pagaria) a cada ciclo.
_AUDIT_CACHE_TTL = 120.0

_SYSTEM_PROMPT = (
    "Você é um auditor de trades de alta precisão. "
    "Responda APENAS com um objeto JSON válido, sem markdown."
)

_TRADE_PROMPT = """Você é um analista quantitativo de criptomoedas.
O robô identificou um gatilho de COMPRA para {symbol}.

Métricas atuais:
- Preço: {current_price:.6f}
- RSI (5m): {rsi:.2f} (Estratégia: Reversão de Fundo)
- Volume Relativo (RVOL): {rvol:.2f}
- Tendência do BTC (4h): {btc_trend:+.2f}%

Regra de risco obrigatória: se o BTC estiver em queda brusca (< -1.5%) e o
RVOL do ativo for baixo (< 2.0), a chance de ser um "falso fundo" é grande.
Nesse cenário, responda authorized=false.

Responda APENAS com JSON válido neste formato exato, sem markdown:
{{"authorized": true, "reason": "explicação curta de até 150 caracteres"}}
"""

# Regex para extrair JSON de dentro de blocos markdown (```json ... ```).
_JSON_CODE_BLOCK_RE = re.compile(
    r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE
)


def _extract_json(text: str) -> dict:
    """
    Tenta parsear JSON diretamente; se falhar, procura dentro de blocos de
    código markdown (```json ... ```) e, por fim, no primeiro { ... }.
    Lança json.JSONDecodeError se nenhuma estratégia funcionar.
    """
    text_stripped = (text or "").strip()
    if not text_stripped:
        raise json.JSONDecodeError("Resposta vazia recebida do modelo", text, 0)

    try:
        parsed = json.loads(text_stripped)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    match = _JSON_CODE_BLOCK_RE.search(text_stripped)
    if match:
        try:
            parsed = json.loads(match.group(1))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    brace_start = text_stripped.find("{")
    brace_end = text_stripped.rfind("}")
    if brace_start != -1 and brace_end > brace_start:
        try:
            parsed = json.loads(text_stripped[brace_start : brace_end + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    raise json.JSONDecodeError("Nenhum JSON válido encontrado na resposta", text, 0)


def _coerce_bool(value) -> Optional[bool]:
    """Normaliza true/false, 1/0 e "sim"/"não" para bool. None = inválido."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ("true", "1", "sim", "yes", "autorizado"):
            return True
        if normalized in ("false", "0", "nao", "não", "no", "bloqueado"):
            return False
    return None


def regras_macro(
    btc_variation_4h: float,
    atr_1h: float,
    atr_1h_mediana: float = 0.0,
) -> tuple[bool, str]:
    """
    Filtro macro determinístico: bloqueia entradas quando o BTC caiu forte em 4h
    ou a volatilidade de 1h está N vezes acima do normal (choque).
    Retorna (autorizado, motivo).
    """
    cfg = config.trading
    motivos = []
    if btc_variation_4h <= cfg.btc_queda_max_4h:
        motivos.append(f"BTC caiu {btc_variation_4h:+.2f}% em 4h")
    if atr_1h_mediana > 0 and atr_1h >= cfg.atr_choque_mult * atr_1h_mediana:
        motivos.append(f"choque de volatilidade (ATR 1h {atr_1h / atr_1h_mediana:.1f}x o normal)")
    if motivos:
        return False, "; ".join(motivos)
    return True, "OK"


@dataclass
class AIVerdict:
    """Resultado da auditoria de uma entrada."""
    autorizado: bool = False
    nivel_risco: str = "ALTO"
    motivo: str = "Fail-Safe: resposta padrão bloqueante"
    timestamp: float = 0.0
    raw_response: Optional[str] = None
    # "deepseek" (modelo real), "disabled" (configuração), "missing_key"
    # (sem chave) ou "error" (API indisponível). Nunca confundir fallback com
    # aprovação do modelo.
    fonte: str = "pending"
    modelo: str = ""
    metricas: dict = field(default_factory=dict)

    def is_stale(self, max_age_seconds: int = 3600) -> bool:
        """Verifica se a leitura está obsoleta (mais de 1h por padrão)."""
        return (time.time() - self.timestamp) > max_age_seconds

    def to_dict(self) -> dict:
        """Serializa para telemetria, persistência e modal de auditoria."""
        return {
            "autorizado": self.autorizado,
            "nivel_risco": self.nivel_risco,
            "motivo": self.motivo,
            "timestamp": self.timestamp,
            "fonte": self.fonte,
            "modelo": self.modelo,
            "metricas": self.metricas,
        }


class AIAdvisor:
    """
    Auditor de entrada DeepSeek.

    O Fast Loop chama `audit_entry()` somente quando os 4 filtros técnicos
    estão verdes; a ordem só é enviada se o veredito autorizar. O último
    veredito fica disponível para o dashboard e para o `ia_snapshot` do trade.
    """

    def __init__(self):
        self._last_verdict: AIVerdict = AIVerdict(
            autorizado=False,
            nivel_risco="ALTO",
            motivo="Aguardando primeiro sinal de entrada para auditoria.",
            timestamp=0.0,
            fonte="pending",
            modelo=config.deepseek.model,
        )
        self._last_audit_at: float = 0.0
        self._last_audit_symbol: str = ""

    # ------------------------------------------------------------------
    # Propriedades de leitura (dashboard / orquestrador)
    # ------------------------------------------------------------------

    @property
    def last_verdict(self) -> AIVerdict:
        """Retorna o último veredito da IA."""
        return self._last_verdict

    @property
    def is_authorized(self) -> bool:
        """Atalho: o último veredito autoriza a entrada?"""
        return self._last_verdict.autorizado and not self._last_verdict.is_stale()

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    async def authorize_trade(
        self,
        symbol: str,
        current_price: float,
        rsi: float,
        rvol: float,
        btc_trend: float,
    ) -> dict:
        """
        Consulta o DeepSeek para auditar a entrada antes da execução.

        Contrato: retorna um dict com `authorized` (bool) e `reason` (str).
        Chaves extras (`fonte`, `latency_ms`) são usadas internamente pelo
        `audit_entry` para distinguir bloqueio do modelo de falha de API.

        Em caso de falha de comunicação, a entrada é NEGADA (fail-closed).
        """
        if not config.trading.ai_validation_enabled:
            return {
                "authorized": True,
                "reason": "Validação de IA desativada",
                "fonte": "disabled",
            }

        if not config.deepseek.api_key:
            return {
                "authorized": True,
                "reason": "DEEPSEEK_API_KEY ausente",
                "fonte": "missing_key",
            }

        prompt = _TRADE_PROMPT.format(
            symbol=symbol,
            current_price=current_price,
            rsi=rsi,
            rvol=rvol,
            btc_trend=btc_trend,
        )
        payload = {
            "model": config.deepseek.model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            # Temperatura baixa: lógica estrita, sem "otimismo" inventado.
            "temperature": 0.1,
            "max_tokens": 200,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {config.deepseek.api_key}",
            "Content-Type": "application/json",
        }

        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(config.deepseek.timeout, connect=5.0)
            ) as client:
                response = await client.post(
                    config.deepseek.api_url, headers=headers, json=payload
                )

                # Algumas contas/versões da API rejeitam response_format.
                # Nesse caso repetimos uma única vez sem o modo JSON — o
                # parser `_extract_json` já cobre markdown/ruído ao redor.
                if response.status_code == 400:
                    payload.pop("response_format", None)
                    response = await client.post(
                        config.deepseek.api_url, headers=headers, json=payload
                    )

            latency_ms = int((time.perf_counter() - started) * 1000)

            if response.status_code != 200:
                detalhe = " ".join((response.text or "").split())[:200]
                logger.error(
                    "[IA AUDIT] %s | HTTP %d em %dms | %s",
                    symbol, response.status_code, latency_ms, detalhe or "<sem corpo>",
                )
                return {
                    "authorized": False,
                    "reason": f"Erro de API HTTP {response.status_code}",
                    "fonte": "error",
                    "latency_ms": latency_ms,
                }

            try:
                data = response.json()
                content = data["choices"][0]["message"]["content"] or ""
                decision = _extract_json(content)
                authorized = _coerce_bool(
                    decision.get("authorized", decision.get("autorizado"))
                )
                reason = " ".join(
                    str(decision.get("reason") or decision.get("motivo") or "").split()
                )[:200]
            except (KeyError, IndexError, TypeError, json.JSONDecodeError, ValueError) as exc:
                logger.error(
                    "[IA AUDIT] %s | resposta inválida do DeepSeek: %s",
                    symbol, exc,
                )
                return {
                    "authorized": False,
                    "reason": "Resposta inválida do oráculo de IA",
                    "fonte": "error",
                    "latency_ms": latency_ms,
                }

            if authorized is None:
                logger.error(
                    "[IA AUDIT] %s | JSON sem campo booleano 'authorized': %s",
                    symbol, content[:200],
                )
                return {
                    "authorized": False,
                    "reason": "Resposta sem veredito booleano",
                    "fonte": "error",
                    "latency_ms": latency_ms,
                }

            if not reason:
                reason = "Modelo não justificou a decisão"

            logger.info(
                "[IA AUDIT] %s | %s | autorizado=%s | RSI=%.2f RVOL=%.2f BTC4h=%+.2f%% "
                "| %dms | motivo=%s",
                symbol, config.deepseek.model, authorized, rsi, rvol, btc_trend,
                latency_ms, reason,
            )
            return {
                "authorized": authorized,
                "reason": reason,
                "fonte": "deepseek",
                "latency_ms": latency_ms,
            }

        except (httpx.TimeoutException, httpx.HTTPError) as exc:
            logger.error(
                "[IA AUDIT] %s | timeout/falha de conexão com DeepSeek: %s",
                symbol, exc,
            )
            return {
                "authorized": False,
                "reason": "Falha de comunicação com o oráculo de IA",
                "fonte": "error",
            }
        except Exception as exc:  # pragma: no cover - salvaguarda final
            logger.error(
                "[IA AUDIT] %s | erro inesperado na auditoria: %s",
                symbol, exc,
            )
            return {
                "authorized": False,
                "reason": "Falha interna na auditoria de IA",
                "fonte": "error",
            }

    async def audit_entry(
        self,
        symbol: str,
        current_price: float,
        rsi: float,
        rvol: float,
        btc_trend: float,
    ) -> AIVerdict:
        """
        Audita uma entrada e devolve o veredito estruturado (AIVerdict).

        Aplica a política de modo (PAPER/LIVE), o cache curto e a conversão do
        contrato `authorized/reason` para o formato consumido pelo dashboard.
        """
        now = time.time()
        if (
            self._last_audit_at
            and self._last_audit_symbol == symbol
            and (now - self._last_audit_at) < _AUDIT_CACHE_TTL
        ):
            logger.debug(
                "[IA AUDIT] Reutilizando veredito de %.0fs atrás para %s",
                now - self._last_audit_at, symbol,
            )
            return self._last_verdict

        metricas = {
            "preco": round(float(current_price), 6),
            "rsi": round(float(rsi), 2),
            "rvol": round(float(rvol), 2),
            "btc_trend_4h": round(float(btc_trend), 2),
        }

        if not config.trading.ai_validation_enabled:
            is_paper = config.is_paper()
            verdict = AIVerdict(
                autorizado=is_paper,
                nivel_risco="BAIXO" if is_paper else "CRITICO",
                motivo=(
                    "Validação de IA desativada — PAPER entra sem auditoria"
                    if is_paper
                    else "Validação de IA desativada em LIVE — entrada bloqueada (fail-safe)"
                ),
                timestamp=now,
                fonte="disabled",
                modelo=config.deepseek.model,
                metricas=metricas,
            )
            logger.info("[IA AUDIT] Validação desativada | %s | autorizado=%s", symbol, is_paper)

        elif not config.deepseek.api_key:
            is_paper = config.is_paper()
            verdict = AIVerdict(
                autorizado=is_paper,
                nivel_risco="BAIXO" if is_paper else "CRITICO",
                motivo=(
                    "DEEPSEEK_API_KEY ausente — PAPER entra sem auditoria"
                    if is_paper
                    else "DEEPSEEK_API_KEY ausente em LIVE — entrada bloqueada"
                ),
                timestamp=now,
                fonte="missing_key",
                modelo=config.deepseek.model,
                metricas=metricas,
            )
            logger.error(
                "[IA AUDIT] DEEPSEEK_API_KEY ausente | %s | autorizado=%s "
                "(PAPER libera sem auditor; LIVE bloqueia)",
                symbol, is_paper,
            )

        else:
            result = await self.authorize_trade(
                symbol=symbol,
                current_price=current_price,
                rsi=rsi,
                rvol=rvol,
                btc_trend=btc_trend,
            )
            fonte = str(result.get("fonte", "error"))
            autorizado = bool(result.get("authorized"))
            if fonte == "deepseek":
                nivel_risco = "BAIXO" if autorizado else "ALTO"
            else:
                # Falha de API/parse: bloqueio crítico, não "risco de mercado".
                nivel_risco = "CRITICO"
            verdict = AIVerdict(
                autorizado=autorizado,
                nivel_risco=nivel_risco,
                motivo=str(result.get("reason") or "Sem justificativa"),
                timestamp=now,
                fonte=fonte,
                modelo=config.deepseek.model,
                metricas=metricas,
            )

        self._last_verdict = verdict
        self._last_audit_at = now
        self._last_audit_symbol = symbol
        return verdict
