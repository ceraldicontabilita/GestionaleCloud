"""
Client LLM basato direttamente sull'SDK anthropic ufficiale (nessuna
dipendenza da servizi terzi non disponibili su PyPI).

E' l'unico client da usare nel codice nuovo (CLAUDE.md, «Un solo sistema per
funzione»): porta timeout, ritentativi con attesa crescente e il conteggio dei
token di ogni chiamata (``usage``), cosi' chi lo usa puo' registrare il costo
senza un secondo client.
"""
import asyncio
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

DEFAULT_DOCUMENT_MODEL = "claude-sonnet-4-6"
#: Secondi concessi a una chiamata (lettura di un PDF di decine di pagine).
TIMEOUT_DEFAULT_S = 120.0
#: Tentativi complessivi per una chiamata; l'attesa fra uno e l'altro cresce.
TENTATIVI_DEFAULT = 3
ATTESE_S = (2.0, 6.0, 18.0)


def document_model_name() -> str:
    """Modello documentale configurabile, senza snapshot ritirati hardcoded."""
    return (
        os.getenv("ANTHROPIC_DOCUMENT_MODEL", "").strip()
        or os.getenv("ANTHROPIC_MODEL", "").strip()
        or DEFAULT_DOCUMENT_MODEL
    )

@dataclass
class ImageContent:
    image_data: str  # base64
    mime_type: str = "image/jpeg"

@dataclass
class FileContentWithMimeType:
    file_data: str  # base64
    mime_type: str = "application/pdf"

@dataclass
class UserMessage:
    content: str
    images: list = field(default_factory=list)
    files: list = field(default_factory=list)


def e_errore_transitorio(exc: BaseException) -> bool:
    """429, 5xx, timeout e rete: si riprova. Un 4xx di contenuto (400, 401, 413) no."""
    try:
        import anthropic
    except ImportError:  # pragma: no cover - senza SDK la chiamata non parte
        return False
    if isinstance(exc, (anthropic.APITimeoutError, anthropic.APIConnectionError)):
        return True
    if isinstance(exc, anthropic.APIStatusError):
        stato = getattr(exc, "status_code", 0) or 0
        return stato == 429 or stato >= 500
    return False


class LlmChat:
    def __init__(self, api_key: str, session_id: str = "", system_prompt: str = "",
                 model: str = DEFAULT_DOCUMENT_MODEL, *, timeout_s: float = TIMEOUT_DEFAULT_S,
                 tentativi: int = TENTATIVI_DEFAULT, max_tokens: int = 4096):
        self.api_key = api_key
        self.system_prompt = system_prompt
        self.model = model
        self.timeout_s = float(timeout_s)
        self.tentativi = max(1, int(tentativi))
        self.max_tokens = int(max_tokens)
        self._client = None

    def _cliente(self):
        # L'SDK si importa e la chiamata parte in un thread: sul loop del
        # server l'import e la risposta dell'AI (13-38 s) fermavano tutto,
        # /api/health compreso, e Render riavviava l'istanza (502).
        if self._client is None:
            import anthropic

            # I ritentativi li fa `send_message_con_usage`, con la sua attesa
            # crescente: quelli interni dell'SDK raddoppierebbero i tempi.
            self._client = anthropic.Anthropic(api_key=self.api_key, timeout=self.timeout_s, max_retries=0)
        return self._client

    def with_model(self, provider: str, model: str):
        self.model = model
        return self

    def _contenuto(self, message: UserMessage) -> list:
        content = []

        # Immagini
        for img in getattr(message, "images", []):
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": img.mime_type,
                    "data": img.image_data,
                }
            })

        # File (PDF)
        for f in getattr(message, "files", []):
            content.append({
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": f.mime_type,
                    "data": f.file_data,
                }
            })

        content.append({"type": "text", "text": message.content})
        return content

    async def send_message_con_usage(self, message: UserMessage) -> Dict[str, Any]:
        """La risposta con il conteggio dei token: ``{"testo", "usage", "modello", "tentativi"}``.

        Ritenta sui guasti transitori (429, 5xx, timeout, rete) fino a
        ``tentativi`` volte con attesa crescente; un errore di contenuto esce
        subito. L'ultimo errore si rilancia com'e'.
        """
        kwargs = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "user", "content": self._contenuto(message)}],
        }
        if self.system_prompt:
            kwargs["system"] = self.system_prompt

        ultimo: Optional[BaseException] = None
        for tentativo in range(1, self.tentativi + 1):
            try:
                response = await asyncio.to_thread(lambda: self._cliente().messages.create(**kwargs))
            except Exception as exc:  # noqa: BLE001 - si decide qui se riprovare
                ultimo = exc
                if tentativo >= self.tentativi or not e_errore_transitorio(exc):
                    raise
                await asyncio.sleep(ATTESE_S[min(tentativo - 1, len(ATTESE_S) - 1)])
                continue
            usage = getattr(response, "usage", None)
            testo = "".join(getattr(blocco, "text", "") or "" for blocco in (response.content or []))
            return {
                "testo": testo,
                "usage": {
                    "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
                    "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
                },
                "modello": getattr(response, "model", None) or self.model,
                "tentativi": tentativo,
            }
        raise ultimo if ultimo else RuntimeError("nessun tentativo eseguito")

    async def send_message(self, message: UserMessage) -> str:
        return (await self.send_message_con_usage(message))["testo"]
