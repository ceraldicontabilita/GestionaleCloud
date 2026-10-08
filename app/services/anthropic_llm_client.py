"""
Client LLM basato direttamente sull'SDK anthropic ufficiale (nessuna
dipendenza da servizi terzi non disponibili su PyPI).

E' **l'unico client** del gestionale (CLAUDE.md, «Un solo sistema per
funzione»): nessun altro modulo importa ``anthropic`` ne' chiama
``api.anthropic.com`` a mano (``tests/runtime/test_ai_client_unico.py`` lo
fissa). Porta in un punto solo:

* chiave (``chiave_api``), modelli (``document_model_name`` per le letture
  documentali, ``modello_veloce`` per classificazioni e letture brevi: mai
  uno snapshot datato cablato nel codice);
* timeout, ritentativi con attesa crescente sui soli guasti transitori;
* la chiamata fuori dall'event loop (``asyncio.to_thread``);
* il **registro delle chiamate** ``agenti_ai_chiamate`` (``registra_chiamata``,
  un solo scrittore: giorno di Roma, scopo, modello, token, esito) e il
  **tetto giornaliero** ``AI_TETTO_GIORNALIERO`` su tutte le chiamate vere
  (``TettoRaggiunto``); ogni scopo puo' tenere un tetto piu' basso con
  ``chiamate_oggi(db, scopo=...)``.

``send_message`` / ``send_message_con_usage`` restano l'uso semplice (un
messaggio utente con immagini o PDF); ``crea_messaggio`` e' la chiamata
completa (conversazione a piu' turni, strumenti propri o server-side come la
ricerca web, temperatura) e torna i blocchi di risposta come dizionari.
"""
import asyncio
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

DEFAULT_DOCUMENT_MODEL = "claude-sonnet-4-6"
#: Modello per classificazioni e letture brevi (dizionario Lotti, centri di costo).
DEFAULT_FAST_MODEL = "claude-haiku-4-5"
#: Secondi concessi a una chiamata (lettura di un PDF di decine di pagine).
TIMEOUT_DEFAULT_S = 120.0
#: Tentativi complessivi per una chiamata; l'attesa fra uno e l'altro cresce.
TENTATIVI_DEFAULT = 3
ATTESE_S = (2.0, 6.0, 18.0)
#: Registro di ogni chiamata vera (un solo scrittore: ``registra_chiamata``).
COLL_CHIAMATE = "agenti_ai_chiamate"
#: Tetto su tutte le chiamate del giorno (Roma), tutti gli scopi insieme.
TETTO_GIORNALIERO_DEFAULT = 1000
#: Strumento server-side di ricerca web nella versione che il modello veloce accetta.
WEB_SEARCH_TOOL = "web_search_20250305"


def chiave_api() -> str:
    return os.getenv("ANTHROPIC_API_KEY", "").strip()


def document_model_name() -> str:
    """Modello documentale configurabile, senza snapshot ritirati hardcoded."""
    return (
        os.getenv("ANTHROPIC_DOCUMENT_MODEL", "").strip()
        or os.getenv("ANTHROPIC_MODEL", "").strip()
        or DEFAULT_DOCUMENT_MODEL
    )


def modello_veloce() -> str:
    """Modello per classificazioni brevi ed economiche (``ANTHROPIC_MODEL_VELOCE``)."""
    return os.getenv("ANTHROPIC_MODEL_VELOCE", "").strip() or DEFAULT_FAST_MODEL


def tetto_giornaliero() -> int:
    try:
        return max(0, int(os.getenv("AI_TETTO_GIORNALIERO", str(TETTO_GIORNALIERO_DEFAULT))))
    except ValueError:
        return TETTO_GIORNALIERO_DEFAULT


def oggi_roma() -> str:
    return datetime.now(ZoneInfo("Europe/Rome")).date().isoformat()


def _adesso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TettoRaggiunto(RuntimeError):
    """Le chiamate del giorno hanno raggiunto il tetto: nessuna chiamata parte."""


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


# ---------------------------------------------------------------------------
# Registro delle chiamate e tetto (un solo scrittore)
# ---------------------------------------------------------------------------

def _archivio(db=None):
    """L'archivio del gestionale, se raggiungibile: senza (test, avvio) il
    registro e il tetto si saltano e lo si scrive nel log a livello debug."""
    if db is not None:
        return db
    try:
        from app.database import Database

        return Database.get_db()
    except Exception as exc:  # noqa: BLE001 - archivio non pronto: nessun registro
        logger.debug("[llm] archivio non disponibile per il registro: %s: %s", type(exc).__name__, exc)
        return None


async def chiamate_oggi(db, scopo: Optional[str] = None) -> int:
    """Chiamate vere registrate oggi (Roma), tutte o di un solo scopo."""
    filtro: Dict[str, Any] = {"giorno": oggi_roma()}
    if scopo:
        filtro["scopo"] = scopo
    return await db[COLL_CHIAMATE].count_documents(filtro)


async def registra_chiamata(db, *, scopo: str, esito: str, usage: Optional[Dict[str, Any]] = None,
                            modello: Optional[str] = None, tentativi: int = 1,
                            errore: Optional[str] = None, **extra: Any) -> Optional[str]:
    """La riga del registro di una chiamata vera. Torna l'``id`` della riga.

    ``extra`` sono i campi propri dello scopo (impronta del file, versione
    del prompt, proposta): il registro e' uno solo, i campi in piu' no."""
    if db is None:
        return None
    riga = {
        "id": f"aic_{uuid.uuid4().hex[:12]}", "giorno": oggi_roma(), "creato": _adesso(),
        "scopo": scopo, "esito": esito,
        "input_tokens": int((usage or {}).get("input_tokens") or 0),
        "output_tokens": int((usage or {}).get("output_tokens") or 0),
        "modello": modello, "tentativi": int(tentativi), "errore": errore,
    }
    riga.update(extra)
    try:
        await db[COLL_CHIAMATE].insert_one(riga)
    except Exception as exc:  # noqa: BLE001 - il registro non ferma la lettura
        logger.warning("[llm] registro chiamate non scritto (%s): %s: %s", scopo, type(exc).__name__, exc)
        return None
    return riga["id"]


def _blocco_in_dizionario(blocco: Any) -> Dict[str, Any]:
    if isinstance(blocco, dict):
        return blocco
    metodo = getattr(blocco, "model_dump", None)
    if callable(metodo):
        try:
            # senza i campi nulli: rimandati al modello come turno assistant, un
            # `citations: null` verrebbe rifiutato
            dato = metodo(exclude_none=True)
            if isinstance(dato, dict):
                return dato
        except Exception:  # noqa: BLE001 - si cade sulla lettura per attributi
            pass
    out: Dict[str, Any] = {}
    for campo in ("type", "text", "id", "name", "input", "content", "tool_use_id"):
        if hasattr(blocco, campo):
            out[campo] = getattr(blocco, campo)
    if "type" not in out and "text" in out:
        out["type"] = "text"
    return out


def testo_dei_blocchi(blocchi: List[Dict[str, Any]]) -> str:
    return "".join(str(b.get("text") or "") for b in blocchi if isinstance(b, dict) and b.get("type") == "text")


def fonti_web_dei_blocchi(blocchi: List[Dict[str, Any]]) -> List[str]:
    """Gli URL consultati dallo strumento di ricerca (dai blocchi del tool, mai dal testo)."""
    fonti: List[str] = []
    for b in blocchi:
        if isinstance(b, dict) and b.get("type") == "web_search_tool_result" and isinstance(b.get("content"), list):
            for voce in b["content"]:
                voce = _blocco_in_dizionario(voce)
                url = str(voce.get("url") or "")
                if url.startswith("http") and url not in fonti:
                    fonti.append(url)
    return fonti


class LlmChat:
    def __init__(self, api_key: str, session_id: str = "", system_prompt: str = "",
                 model: Optional[str] = None, *, timeout_s: float = TIMEOUT_DEFAULT_S,
                 tentativi: int = TENTATIVI_DEFAULT, max_tokens: int = 4096,
                 scopo: str = "generico", db=None, registra: bool = True):
        self.api_key = api_key
        self.session_id = session_id
        self.system_prompt = system_prompt
        self.model = model or document_model_name()
        self.timeout_s = float(timeout_s)
        self.tentativi = max(1, int(tentativi))
        self.max_tokens = int(max_tokens)
        self.scopo = scopo
        self.db = db
        self.registra = registra
        self._client = None

    def _cliente(self):
        # L'SDK si importa e la chiamata parte in un thread: sul loop del
        # server l'import e la risposta dell'AI (13-38 s) fermavano tutto,
        # /api/health compreso, e Render riavviava l'istanza (502).
        if self._client is None:
            import anthropic

            # I ritentativi li fa `crea_messaggio`, con la sua attesa
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

    async def _verifica_tetto(self, db) -> None:
        if db is None:
            return
        tetto = tetto_giornaliero()
        if tetto <= 0:
            return
        try:
            fatte = await chiamate_oggi(db)
        except Exception as exc:  # noqa: BLE001 - registro illeggibile: la chiamata parte lo stesso
            logger.warning("[llm] tetto non verificabile: %s: %s", type(exc).__name__, exc)
            return
        if fatte >= tetto:
            raise TettoRaggiunto(f"tetto giornaliero AI raggiunto ({fatte}/{tetto}, AI_TETTO_GIORNALIERO)")

    async def crea_messaggio(self, messages: List[Dict[str, Any]], *, tools: Optional[List[Dict[str, Any]]] = None,
                             max_tokens: Optional[int] = None, temperature: Optional[float] = None,
                             system: Optional[str] = None, annotazioni: Optional[Dict[str, Any]] = None
                             ) -> Dict[str, Any]:
        """La chiamata completa: ``{"content": [blocchi dict], "stop_reason", "testo", "fonti_web",
        "usage", "modello", "tentativi"}``.

        Ritenta sui guasti transitori (429, 5xx, timeout, rete) fino a
        ``tentativi`` volte con attesa crescente; un errore di contenuto esce
        subito. Prima della chiamata verifica il tetto giornaliero e dopo
        registra la chiamata (``registra=False`` lascia il registro al
        chiamante, che usa ``registra_chiamata`` con i suoi campi).
        """
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": int(max_tokens or self.max_tokens),
            "messages": messages,
        }
        sistema = system if system is not None else self.system_prompt
        if sistema:
            kwargs["system"] = sistema
        if tools:
            kwargs["tools"] = tools
        if temperature is not None:
            kwargs["temperature"] = float(temperature)

        db = _archivio(self.db)
        await self._verifica_tetto(db)

        ultimo: Optional[BaseException] = None
        for tentativo in range(1, self.tentativi + 1):
            try:
                response = await asyncio.to_thread(lambda: self._cliente().messages.create(**kwargs))
            except Exception as exc:  # noqa: BLE001 - si decide qui se riprovare
                ultimo = exc
                if tentativo >= self.tentativi or not e_errore_transitorio(exc):
                    if self.registra:
                        await registra_chiamata(db, scopo=self.scopo, esito="errore", modello=self.model,
                                                tentativi=tentativo, errore=f"{type(exc).__name__}: {exc}"[:300],
                                                **(annotazioni or {}))
                    raise
                await asyncio.sleep(ATTESE_S[min(tentativo - 1, len(ATTESE_S) - 1)])
                continue
            usage_grezzo = getattr(response, "usage", None)
            blocchi = [_blocco_in_dizionario(b) for b in (getattr(response, "content", None) or [])]
            usage = {
                "input_tokens": int(getattr(usage_grezzo, "input_tokens", 0) or 0),
                "output_tokens": int(getattr(usage_grezzo, "output_tokens", 0) or 0),
            }
            modello = getattr(response, "model", None) or self.model
            if self.registra:
                await registra_chiamata(db, scopo=self.scopo, esito="ok", usage=usage, modello=modello,
                                        tentativi=tentativo, **(annotazioni or {}))
            return {
                "content": blocchi,
                "stop_reason": getattr(response, "stop_reason", None),
                "testo": testo_dei_blocchi(blocchi),
                "fonti_web": fonti_web_dei_blocchi(blocchi),
                "usage": usage,
                "modello": modello,
                "tentativi": tentativo,
            }
        raise ultimo if ultimo else RuntimeError("nessun tentativo eseguito")

    async def send_message_con_usage(self, message: UserMessage,
                                     annotazioni: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """La risposta con il conteggio dei token: ``{"testo", "usage", "modello", "tentativi"}``."""
        esito = await self.crea_messaggio([{"role": "user", "content": self._contenuto(message)}],
                                          annotazioni=annotazioni)
        return {chiave: esito[chiave] for chiave in ("testo", "usage", "modello", "tentativi", "stop_reason")}

    async def send_message(self, message: UserMessage) -> str:
        return (await self.send_message_con_usage(message))["testo"]

    async def cerca_sul_web(self, prompt: str, *, max_tokens: int = 1500, max_uses: int = 3) -> Dict[str, Any]:
        """Una domanda con lo strumento server-side di ricerca web: ``{"testo", "fonti"}``."""
        esito = await self.crea_messaggio(
            [{"role": "user", "content": prompt}], max_tokens=max_tokens,
            tools=[{"type": WEB_SEARCH_TOOL, "name": "web_search", "max_uses": int(max_uses)}])
        return {"testo": esito["testo"], "fonti": esito["fonti_web"]}
