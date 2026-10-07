"""Banco BPM via Enable Banking (PSD2, **sola lettura**), in modalita' ombra.

Portato dal servizio di prova ``enable_banking_probe`` (collaudo reale del
23/09/2026: 516 movimenti in 6 pagine, 514 su 514 uguali al CSV nel periodo
comune). Qui vive l'unica copia della logica: il probe si spegne quando il
gestionale fa tutto.

Cosa fa:
  - collega il conto (``avvia_collegamento`` → la banca → ``completa_collegamento``);
  - legge i movimenti contabilizzati (``BOOK``) con la paginazione della banca;
  - li confronta con ``estratto_conto_movimenti`` con **lo stesso motore dei
    doppioni** degli export CSV (``doppioni_estratto_conto.accoppia``):
    nuovi / gia' presenti / DA_VERIFICARE.

Cosa NON fa: nessun pagamento, nessuna funzione dispositiva, nessuna
scrittura di movimenti (arriva col pulsante «Aggiorna ora», dopo la conferma
del titolare). Una coppia trovata per sola data e importo e' DA_VERIFICARE:
data e importo da soli non provano che sia la stessa operazione.

Sessione: si salva **cifrato solo il session_id** di Enable Banking (decisione
del titolare del 25/09/2026), con la chiave gia' usata per le credenziali
(``CREDENTIALS_ENCRYPTION_KEY``, ``app/utils/crypto.py``). Mai password, PIN
o OTP: quelli restano sui sistemi della banca.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import secrets
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Awaitable, Callable, Dict, List, Optional
from urllib.parse import quote

logger = logging.getLogger(__name__)

FONTE = "enable_banking"
CHIAVE_SESSIONE = "enable_banking_sessione"
CHIAVE_STATI_ATTESA = "enable_banking_stati_attesa"
COUNTRY = "IT"
PSU_TYPE = "business"
STATE_TTL = timedelta(minutes=15)

# Una banca PSD2 restituisce pagine brevi: 500 pagine sono ben oltre un anno
# di movimenti. Superarle vuol dire che il cursore non avanza.
MAX_PAGINE = 500
TENTATIVI_TEMPORANEI = 3

# Codici Enable Banking che vogliono dire «il consenso non c'e' piu'»: si
# ricollega il conto, riprovare non serve.
ERRORI_CONSENSO = {
    "EXPIRED_SESSION", "CLOSED_SESSION", "REVOKED_SESSION", "SESSION_DOES_NOT_EXIST",
    "UNAUTHORIZED_ACCESS", "ASPSP_PSU_ACTION_REQUIRED",
}
# Limite di letture della banca (PSD2: poche al giorno senza l'utente
# presente). Riprovare consuma altre letture: ci si ferma.
ERRORI_LIMITE = {"ASPSP_RATE_LIMIT_EXCEEDED"}
ERRORI_TEMPORANEI = {"ASPSP_TIMEOUT", "ASPSP_ERROR", "TEMPORARILY_UNAVAILABLE", "TIMEOUT"}


# ── configurazione ──────────────────────────────────────────────────────────

def attivo() -> bool:
    """Feature flag: spenta per default."""
    return os.getenv("ENABLE_BANKING_ENABLED", "false").strip().lower() in {"1", "true", "si", "yes"}


def _application_id() -> str:
    return os.getenv("ENABLE_BANKING_APPLICATION_ID", "").strip()


def _private_key() -> str:
    return os.getenv("ENABLE_BANKING_PRIVATE_KEY_PEM", "").replace("\\n", "\n")


def redirect_url() -> str:
    return os.getenv(
        "ENABLE_BANKING_REDIRECT_URL",
        "https://gestionalecloud.onrender.com/api/banca/enable-banking/callback",
    ).strip()


def api_origin() -> str:
    return os.getenv("ENABLE_BANKING_API_ORIGIN", "https://api.enablebanking.com").rstrip("/")


def configurato() -> bool:
    return bool(_application_id() and _private_key())


def giorni_accesso() -> int:
    try:
        return min(max(int(os.getenv("ENABLE_BANKING_ACCESS_DAYS", "90")), 1), 180)
    except ValueError:
        return 90


def _jwt_applicazione() -> str:
    import jwt

    if not configurato():
        raise ErroreLettura("non_configurato", 0)
    adesso = int(datetime.now(timezone.utc).timestamp())
    return jwt.encode(
        {"iss": "enablebanking.com", "aud": "api.enablebanking.com",
         "iat": adesso, "exp": adesso + 15 * 60},
        _private_key(), algorithm="RS256", headers={"kid": _application_id()},
    )


def _headers_api() -> Dict[str, str]:
    return {"Authorization": f"Bearer {_jwt_applicazione()}", "Accept": "application/json"}


def headers_psu(ip: str = "", user_agent: str = "") -> Dict[str, str]:
    """Con l'utente presente la banca non conta la lettura nel limite
    giornaliero delle letture in background (PSD2)."""
    h = {}
    if ip:
        h["Psu-Ip-Address"] = ip
    if user_agent:
        h["Psu-User-Agent"] = user_agent[:512]
    return h


# ── errori e lettura ────────────────────────────────────────────────────────

class ErroreLettura(Exception):
    """Lettura interrotta: ``stato`` dice perche', mai il contenuto."""

    def __init__(self, stato: str, http: int, codice: str = ""):
        super().__init__(f"{stato} (HTTP {http}{', ' + codice if codice else ''})")
        self.stato = stato
        self.http = http
        self.codice = codice


def classifica_errore(http: int, corpo: Optional[Dict[str, Any]]) -> str:
    codice = str((corpo or {}).get("error") or "")
    if codice in ERRORI_CONSENSO or http == 401:
        return "consenso_scaduto"
    if codice in ERRORI_LIMITE:
        return "limite_banca"
    if codice == "WRONG_TRANSACTIONS_PERIOD":
        return "periodo_non_disponibile"
    if codice in ERRORI_TEMPORANEI or http in (408, 429) or http >= 500:
        return "temporaneo"
    return "rifiutato"


def _json(risposta) -> Optional[Dict[str, Any]]:
    try:
        corpo = risposta.json()
    except Exception:
        return None
    return corpo if isinstance(corpo, dict) else None


async def _get_json(client, url: str, *, headers: Dict[str, str], params: Dict[str, str],
                    attendi: Callable[[float], Awaitable[None]]) -> Dict[str, Any]:
    """GET con al piu' tre tentativi sui soli errori temporanei."""
    for tentativo in range(TENTATIVI_TEMPORANEI):
        risposta = await client.get(url, headers=headers, params=params)
        corpo = _json(risposta)
        if risposta.status_code == 200 and corpo is not None:
            return corpo
        stato = classifica_errore(risposta.status_code, corpo)
        codice = str((corpo or {}).get("error") or "")
        if stato != "temporaneo" or tentativo == TENTATIVI_TEMPORANEI - 1:
            raise ErroreLettura(stato, risposta.status_code, codice)
        await attendi(2 ** (tentativo + 1))
    raise ErroreLettura("temporaneo", 0)  # irraggiungibile: il ciclo solleva prima


async def leggi_transazioni(client, url: str, *, headers: Callable[[], Dict[str, str]],
                            date_from: str, date_to: Optional[str] = None,
                            attendi: Callable[[float], Awaitable[None]] = asyncio.sleep,
                            ) -> Dict[str, Any]:
    """Tutte le pagine di ``/transactions`` per il periodo richiesto.

    Solo i movimenti contabilizzati (``BOOK``); gli altri stati si contano a
    parte: un movimento in attesa cambia riferimento quando viene
    contabilizzato, e se entrasse ora tornerebbe come doppione.
    """
    contabilizzati: List[Dict[str, Any]] = []
    altri = Counter()
    pagine = 0
    chiave: Optional[str] = None
    viste = set()
    while True:
        params = {"date_from": date_from}
        if date_to:
            params["date_to"] = date_to
        if chiave:
            params["continuation_key"] = chiave
        corpo = await _get_json(client, url, headers=headers(), params=params, attendi=attendi)
        pagine += 1
        for tx in corpo.get("transactions") or []:
            if not isinstance(tx, dict):
                continue
            stato = str(tx.get("status") or "")
            if stato == "BOOK":
                contabilizzati.append(tx)
            else:
                altri[stato or "SENZA_STATO"] += 1
        chiave = corpo.get("continuation_key") or None
        if not chiave:
            break
        if chiave in viste or pagine >= MAX_PAGINE:
            raise ErroreLettura("cursore_bloccato", 200)
        viste.add(chiave)
    return {"pagine": pagine, "movimenti": contabilizzati, "altri_stati": dict(altri)}


# ── normalizzazione ─────────────────────────────────────────────────────────

def maschera_iban(valore: str) -> str:
    compatto = re.sub(r"\s+", "", str(valore or ""))
    if len(compatto) <= 8:
        return "****" if compatto else ""
    return f"{compatto[:4]}****{compatto[-4:]}"


def _importo(valore: Any) -> Optional[Decimal]:
    try:
        return Decimal(str(valore)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def descrizione_api(tx: Dict[str, Any]) -> str:
    righe = [str(r) for r in (tx.get("remittance_information") or []) if r]
    if not righe and tx.get("note"):
        righe = [str(tx["note"])]
    if not righe:
        codice = tx.get("bank_transaction_code") or {}
        if isinstance(codice, dict) and codice.get("description"):
            righe = [str(codice["description"])]
    return re.sub(r"\s+", " ", " ".join(righe)).strip()


def normalizza_api(tx: Dict[str, Any], conto: str, acquisito_il: str) -> Optional[Dict[str, Any]]:
    """Una transazione Enable Banking nella forma di ``estratto_conto_movimenti``."""
    importo_tx = tx.get("transaction_amount") or {}
    assoluto = _importo(importo_tx.get("amount"))
    data = str(tx.get("booking_date") or tx.get("value_date") or "")[:10]
    if assoluto is None or not data:
        return None
    uscita = str(tx.get("credit_debit_indicator") or "").upper() == "DBIT"
    importo = -abs(assoluto) if uscita else abs(assoluto)
    grezzo = json.dumps(tx, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return {
        "fonte": FONTE,
        "banca": "Banco BPM",
        "conto": conto,
        "data": data,
        "data_valuta": str(tx.get("value_date") or "")[:10] or None,
        "importo": importo,
        "divisa": str(importo_tx.get("currency") or "EUR"),
        "tipo": "uscita" if uscita else "entrata",
        "descrizione_originale": descrizione_api(tx),
        "entry_reference": tx.get("entry_reference"),
        "transaction_id": tx.get("transaction_id"),
        "hash_fonte": hashlib.sha256(grezzo.encode("utf-8")).hexdigest(),
        "acquisito_il": acquisito_il,
    }


# Parole che Banco BPM manda al posto del nome del conto: non sono nomi.
_NON_NOMI_CONTO = frozenset(("false", "true"))


def _testo_conto(valore: Any) -> str:
    """Banco BPM manda ``"false"`` al posto del nome del conto: non e' un nome."""
    testo = valore.strip() if isinstance(valore, str) else ""
    if testo.lower() in _NON_NOMI_CONTO:
        return ""
    return testo[:80]


def meta_conto(account: Dict[str, Any]) -> Dict[str, str]:
    ident = account.get("account_id") or {}
    iban = ident.get("iban") if isinstance(ident, dict) else None
    return {
        "uid": str(account.get("uid") or ""),
        "iban_mascherato": maschera_iban(iban or ""),
        "nome": _testo_conto(account.get("name")) or _testo_conto(account.get("product")),
    }


# ── confronto con l'archivio ────────────────────────────────────────────────

def confronta_con_archivio(api: List[Dict[str, Any]], archivio: List[Dict[str, Any]]) -> Dict[str, Any]:
    """nuovi / gia' presenti / DA_VERIFICARE contro ``estratto_conto_movimenti``.

    Le coppie le trova ``accoppia`` (giorno, segno, importo al centesimo e
    quante volte compaiono): e' la regola dei due export dello stesso conto,
    e le parole diverse non la smentiscono — la banca scrive «VERS. CONTANTI»,
    il vecchio archivio «VERSAMENTO CONTANTI». Fino al 26/09/2026 una coppia
    senza testo uguale restava fuori come DA_VERIFICARE: 41 movimenti gia' in
    archivio segnalati come «non importati» a ogni lettura. Resta dubbia solo
    la coppia che si **contraddice**: entrambe le righe portano codici della
    banca e nessuno e' in comune (gli assegni con numeri diversi non si
    accoppiano nemmeno). Il confronto vale sul periodo che la banca ha
    restituito: prima di quella data l'archivio non si giudica.
    """
    from app.services import doppioni_estratto_conto as doppioni

    if not api:
        return {"periodo": None, "nuovi": [], "gia_presenti": [], "da_verificare": []}
    inizio, fine = min(m["data"] for m in api), max(m["data"] for m in api)
    archivio_p = [m for m in archivio
                  if inizio <= str(m.get("data") or "")[:10] <= fine
                  and doppioni.conto_del_movimento(m) == "bpm"]
    gia, dubbi, abbinati = [], [], set()
    for nuovo, esistente in doppioni.accoppia(api, archivio_p):
        abbinati.add(id(nuovo))
        contraddice = (
            doppioni.codici(nuovo) and doppioni.codici(esistente)
            and not doppioni.stesso_riferimento(nuovo, esistente)
        )
        (dubbi if contraddice else gia).append({"banca": nuovo, "archivio_id": esistente.get("id")})
    return {
        "periodo": [inizio, fine],
        "nuovi": [m for m in api if id(m) not in abbinati],
        "gia_presenti": gia,
        "da_verificare": dubbi,
    }


# ── sessione cifrata ────────────────────────────────────────────────────────

def _cifra(testo: str) -> str:
    from app.utils.crypto import encrypt_credential

    return encrypt_credential(testo)


def _decifra(token: str) -> Optional[str]:
    """Fallisce chiuso: un token che non si decifra non e' una sessione."""
    from cryptography.fernet import InvalidToken

    from app.utils.crypto import _get_fernet

    if not token:
        return None
    try:
        return _get_fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        logger.warning("[enable-banking] sessione salvata non decifrabile: va ricollegato il conto")
        return None


async def leggi_sessione(db) -> Dict[str, Any]:
    """Stato pubblico della sessione: mai il session_id."""
    doc = await db["sistema_stato"].find_one({"chiave": CHIAVE_SESSIONE}, {"_id": 0}) or {}
    return {
        "collegata": bool(doc.get("session_id_cifrato")),
        "conti": [{k: c.get(k) for k in ("iban_mascherato", "nome")} for c in doc.get("conti") or []],
        "valida_fino": doc.get("valida_fino"),
        "collegata_il": doc.get("collegata_il"),
        "ultima_lettura": doc.get("ultima_lettura"),
        "ultimo_import": doc.get("ultimo_import"),
        "ultimo_import_esito": doc.get("ultimo_import_esito"),
        "giro_automatico": doc.get("giro_automatico"),
        "rilettura_dal": doc.get("rilettura_dal"),
    }


async def _sessione_privata(db) -> Optional[Dict[str, Any]]:
    doc = await db["sistema_stato"].find_one({"chiave": CHIAVE_SESSIONE}, {"_id": 0}) or {}
    session_id = _decifra(doc.get("session_id_cifrato") or "")
    if not session_id:
        return None
    return {"session_id": session_id, "conti": doc.get("conti") or []}


# ── collegamento ────────────────────────────────────────────────────────────

def _hash_state(state: str) -> str:
    return hashlib.sha256(state.encode()).hexdigest()


async def _risolvi_banco_bpm(client) -> Optional[Dict[str, str]]:
    risposta = await client.get(f"{api_origin()}/aspsps", headers=_headers_api(),
                                params={"country": COUNTRY, "psu_type": PSU_TYPE})
    candidati = [a for a in (_json(risposta) or {}).get("aspsps", [])
                 if isinstance(a, dict) and "banco bpm" in str(a.get("name", "")).lower()]
    if not candidati:
        return None
    scelto = next((a for a in candidati if "corporate" in str(a.get("name", "")).lower()), candidati[0])
    return {"name": str(scelto["name"]), "country": str(scelto.get("country", COUNTRY))}


async def avvia_collegamento(db, client) -> str:
    """Ritorna l'indirizzo della banca dove il titolare autorizza il conto.

    Lo ``state`` monouso si conserva solo come impronta SHA-256, con la data:
    il ritorno dalla banca lo deve presentare entro 15 minuti.
    """
    state = secrets.token_urlsafe(32)
    aspsp = await _risolvi_banco_bpm(client)
    if not aspsp:
        raise ErroreLettura("banca_non_disponibile", 0)
    risposta = await client.post(f"{api_origin()}/auth", headers=_headers_api(), json={
        "access": {"valid_until": (datetime.now(timezone.utc) + timedelta(days=giorni_accesso())).isoformat()},
        "aspsp": aspsp,
        "state": state,
        "redirect_url": redirect_url(),
        "psu_type": PSU_TYPE,
    })
    corpo = _json(risposta)
    if risposta.status_code != 200 or not corpo or not corpo.get("url"):
        raise ErroreLettura("autorizzazione_non_avviata", risposta.status_code, str((corpo or {}).get("error") or ""))
    adesso = datetime.now(timezone.utc)
    doc = await db["sistema_stato"].find_one({"chiave": CHIAVE_STATI_ATTESA}, {"_id": 0}) or {}
    attesi = {h: t for h, t in (doc.get("stati") or {}).items()
              if adesso - datetime.fromisoformat(t) < STATE_TTL}
    attesi[_hash_state(state)] = adesso.isoformat()
    await db["sistema_stato"].update_one(
        {"chiave": CHIAVE_STATI_ATTESA},
        {"$set": {"chiave": CHIAVE_STATI_ATTESA, "stati": attesi}}, upsert=True)
    return str(corpo["url"])


async def _consuma_state(db, state: str) -> bool:
    if not state:
        return False
    doc = await db["sistema_stato"].find_one({"chiave": CHIAVE_STATI_ATTESA}, {"_id": 0}) or {}
    attesi = dict(doc.get("stati") or {})
    creato = attesi.pop(_hash_state(state), None)
    await db["sistema_stato"].update_one(
        {"chiave": CHIAVE_STATI_ATTESA},
        {"$set": {"chiave": CHIAVE_STATI_ATTESA, "stati": attesi}}, upsert=True)
    return bool(creato) and datetime.now(timezone.utc) - datetime.fromisoformat(creato) < STATE_TTL


async def completa_collegamento(db, client, *, code: str, state: str) -> Dict[str, Any]:
    """Ritorno dalla banca: scambia il codice con la sessione e la salva cifrata."""
    if not code or not await _consuma_state(db, state):
        raise ErroreLettura("ritorno_non_valido", 400)
    risposta = await client.post(f"{api_origin()}/sessions", headers=_headers_api(), json={"code": code})
    corpo = _json(risposta)
    if risposta.status_code != 200 or not corpo or not corpo.get("session_id"):
        raise ErroreLettura("sessione_non_creata", risposta.status_code, str((corpo or {}).get("error") or ""))
    conti = [meta_conto(a) for a in corpo.get("accounts", []) if isinstance(a, dict) and a.get("uid")]
    adesso = datetime.now(timezone.utc).isoformat()
    await db["sistema_stato"].update_one({"chiave": CHIAVE_SESSIONE}, {"$set": {
        "chiave": CHIAVE_SESSIONE,
        "session_id_cifrato": _cifra(str(corpo["session_id"])),
        "conti": conti,
        "valida_fino": str((corpo.get("access") or {}).get("valid_until") or "") or None,
        "collegata_il": adesso,
    }}, upsert=True)
    return await leggi_sessione(db)


# ── lettura e anteprima ─────────────────────────────────────────────────────

async def leggi_movimenti(db, client, *, giorni: int = 90, psu: Optional[Dict[str, str]] = None,
                          attendi: Callable[[float], Awaitable[None]] = asyncio.sleep) -> Dict[str, Any]:
    """Legge i movimenti di tutti i conti collegati. Nessuna scrittura di movimenti."""
    sessione = await _sessione_privata(db)
    if not sessione:
        raise ErroreLettura("non_collegato", 0)
    date_from = (datetime.now(timezone.utc) - timedelta(days=giorni)).date().isoformat()
    acquisito_il = datetime.now(timezone.utc).isoformat()
    movimenti: List[Dict[str, Any]] = []
    conti: List[Dict[str, Any]] = []
    for conto in sessione["conti"]:
        uid = quote(str(conto.get("uid") or ""), safe="")
        etichetta = conto.get("iban_mascherato") or "conto"
        letti = await leggi_transazioni(
            client, f"{api_origin()}/accounts/{uid}/transactions",
            headers=lambda: {**_headers_api(), **(psu or {})},
            date_from=date_from, attendi=attendi,
        )
        normalizzati, scartati = [], 0
        for tx in letti["movimenti"]:
            mov = normalizza_api(tx, etichetta, acquisito_il)
            if mov is None:
                scartati += 1
            else:
                normalizzati.append(mov)
        movimenti.extend(normalizzati)
        conti.append({"conto": etichetta, "pagine": letti["pagine"], "movimenti": len(normalizzati),
                      "altri_stati": letti["altri_stati"], "senza_importo_o_data": scartati})
    await db["sistema_stato"].update_one(
        {"chiave": CHIAVE_SESSIONE}, {"$set": {"ultima_lettura": acquisito_il}})
    return {"movimenti": movimenti, "conti": conti, "letto_il": acquisito_il, "dal": date_from}


def _pubblico(mov: Dict[str, Any]) -> Dict[str, Any]:
    return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in mov.items()}


async def anteprima(db, client, *, giorni: int = 90, psu: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Legge dalla banca e dice cosa entrerebbe: e' una simulazione (dry_run)."""
    letti = await leggi_movimenti(db, client, giorni=giorni, psu=psu)
    archivio = await db["estratto_conto_movimenti"].find(
        {"data": {"$gte": letti["dal"]}},
        {"_id": 0, "id": 1, "data": 1, "importo": 1, "tipo": 1, "banca": 1,
         "descrizione": 1, "descrizione_originale": 1},
    ).to_list(None)
    confronto = confronta_con_archivio(letti["movimenti"], archivio)
    return {
        "dry_run": True,
        "letto_il": letti["letto_il"],
        "conti": letti["conti"],
        "periodo": confronto["periodo"],
        "conteggi": {
            "letti": len(letti["movimenti"]),
            "nuovi": len(confronto["nuovi"]),
            "gia_presenti": len(confronto["gia_presenti"]),
            "da_verificare": len(confronto["da_verificare"]),
        },
        "nuovi": [_pubblico(m) for m in confronto["nuovi"]],
        "da_verificare": [{"banca": _pubblico(c["banca"]), "archivio_id": c["archivio_id"]}
                          for c in confronto["da_verificare"]],
    }


async def importa_nuovi(
    db, client, *, giorni: int = 90, psu: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Importa soltanto i movimenti che il confronto giudica realmente nuovi.

    Le coppie ``DA_VERIFICARE`` (riferimenti della banca in contraddizione)
    restano fuori: non si decide a caso se sia nuova o duplicata. La fonte API e' operativa e
    resta provvisoria finche' non arriva l'estratto conto ufficiale PDF.
    """
    from app.routers.bank.estratto_conto import bank_operation_identity
    from app.services.bank_evidence import campi_evidenza
    from app.services.categorizzazione_movimenti import categorizza_movimento_bancario
    from app.services.regole_riconoscimento_banca import carica_regole

    letti = await leggi_movimenti(db, client, giorni=giorni, psu=psu)
    archivio = await db["estratto_conto_movimenti"].find(
        {"data": {"$gte": letti["dal"]}},
        {"_id": 0, "id": 1, "data": 1, "importo": 1, "tipo": 1, "banca": 1,
         "descrizione": 1, "descrizione_originale": 1, "entry_reference": 1,
         "transaction_id": 1},
    ).to_list(None)
    confronto = confronta_con_archivio(letti["movimenti"], archivio)
    regole = await carica_regole(db)
    evidenza = {
        **campi_evidenza("enable_banking_api.json"),
        "fonte_documento": "api_bancaria_operativa",
    }
    occorrenze: Counter = Counter()
    inseriti = []
    adesso = datetime.now(timezone.utc).isoformat()

    for movimento in confronto["nuovi"]:
        data = str(movimento.get("data") or "")[:10]
        tipo = str(movimento.get("tipo") or "").lower()
        importo = abs(float(movimento.get("importo") or 0))
        descrizione = str(movimento.get("descrizione_originale") or "").strip()
        base = (data, tipo, round(importo, 2), descrizione.upper())
        occorrenze[base] += 1
        operation_key, operation_id = bank_operation_identity(
            data, tipo, importo, descrizione, occorrenze[base]
        )
        record_id = f"EC-EB-{operation_key[:24]}"
        categoria = categorizza_movimento_bancario(descrizione, importo, regole=regole)
        campi_categoria: Dict[str, Any] = {"categoria": categoria.categoria or ""}
        if categoria.categoria or categoria.fornitore_id:
            campi_categoria.update({
                "categoria_auto": True,
                "categoria_auto_motivo": categoria.motivo,
            })
        if categoria.codice_tributo:
            campi_categoria["categoria_codice_tributo"] = categoria.codice_tributo
        if categoria.fornitore_id:
            campi_categoria.update({
                "fornitore_id": categoria.fornitore_id,
                "fornitore": categoria.fornitore_nome,
                "regola_riconoscimento_id": categoria.regola_id,
            })

        record = {
            "id": record_id,
            "operation_id": operation_id,
            "operation_key": operation_key,
            "identity_version": "bank_v2",
            "occurrence_index": occorrenze[base],
            "data": data,
            "data_valuta": movimento.get("data_valuta"),
            "data_pagamento": movimento.get("data_valuta") or data,
            "importo": importo,
            "tipo": tipo,
            "descrizione": descrizione,
            "descrizione_originale": descrizione,
            "banca": "Banco BPM",
            "rapporto": movimento.get("conto"),
            "divisa": movimento.get("divisa") or "EUR",
            "entry_reference": movimento.get("entry_reference"),
            "external_reference": movimento.get("entry_reference"),
            "transaction_id": movimento.get("transaction_id"),
            "hash_fonte": movimento.get("hash_fonte"),
            "fonte": FONTE,
            "source_filename": "Enable Banking API",
            "riconciliato": False,
            "created_at": adesso,
            **campi_categoria,
            **evidenza,
        }
        risultato = await db["estratto_conto_movimenti"].update_one(
            {"id": record_id}, {"$setOnInsert": record}, upsert=True
        )
        if getattr(risultato, "upserted_id", None) is not None:
            inseriti.append(record)

    riconciliazione_operativa = None
    if inseriti:
        from app.services.riconciliazione_operativa_banca import annota_movimenti_operativi

        riconciliazione_operativa = await annota_movimenti_operativi(
            db, [record["id"] for record in inseriti]
        )

    esito = {
        "success": True,
        "letto_il": letti["letto_il"],
        "periodo": confronto["periodo"],
        "letti": len(letti["movimenti"]),
        "importati": len(inseriti),
        "gia_presenti": len(confronto["gia_presenti"]),
        "da_verificare_esclusi": len(confronto["da_verificare"]),
        "ids_importati": [record["id"] for record in inseriti],
        "livello_evidenza": "provvisoria",
        "riconciliazione_operativa": riconciliazione_operativa,
    }
    await db["sistema_stato"].update_one(
        {"chiave": CHIAVE_SESSIONE},
        {"$set": {"ultimo_import": adesso, "ultimo_import_esito": {
            "importati": esito["importati"],
            "da_verificare_esclusi": esito["da_verificare_esclusi"],
        }}},
    )
    return esito


# ── giro automatico ─────────────────────────────────────────────────────────

# Senza l'utente presente la banca concede poche letture al giorno (PSD2):
# due giri bastano, e uno lasciato libero serve a «Aggiorna ora».
# Una settimana indietro (titolare, 07/10/2026): ``ENABLE_BANKING_GIORNI_GIRO``
# la cambia senza toccare il codice.
GIORNI_GIRO = 7
GIORNI_PRIMO_GIRO = 90


def giorni_giro() -> int:
    try:
        return min(max(int(os.getenv("ENABLE_BANKING_GIORNI_GIRO", str(GIORNI_GIRO))), 1), 366)
    except ValueError:
        return GIORNI_GIRO


def rilettura_dal() -> Optional[str]:
    """``ENABLE_BANKING_DAL=AAAA-MM-GG``: il giro automatico rilegge la banca da
    quella data, una volta sola per valore (archivio azzerato il 06/10/2026),
    poi torna alla finestra ordinaria. Il confronto con l'archivio evita i
    doppioni: rileggere non riscrive."""
    valore = os.getenv("ENABLE_BANKING_DAL", "").strip()
    if not valore:
        return None
    try:
        date.fromisoformat(valore)
    except ValueError:
        logger.warning("[enable-banking] ENABLE_BANKING_DAL non e' una data ISO: %r", valore)
        return None
    return valore


def rilettura_in_attesa(stato: Dict[str, Any]) -> Optional[str]:
    """La data di rilettura chiesta e non ancora eseguita, altrimenti None."""
    dal = rilettura_dal()
    if dal and stato.get("rilettura_dal") != dal:
        return dal
    return None


async def giro_automatico(db, client) -> Dict[str, Any]:
    """Importa da solo i movimenti certamente nuovi (scheduler, Europe/Rome).

    Stesso motore di «Importa»: i DA_VERIFICARE restano fuori, niente doppioni.
    L'esito, anche il salto o l'errore, resta in ``sistema_stato`` perche'
    Prima Nota Banca e il riquadro Aggiornamento dati lo mostrino.
    """
    adesso = datetime.now(timezone.utc).isoformat()
    stato = await leggi_sessione(db) if attivo() and configurato() else {}
    if not attivo() or not configurato():
        esito: Dict[str, Any] = {"eseguito_il": adesso, "saltato": "spento"}
    elif not stato.get("collegata"):
        esito = {"eseguito_il": adesso, "saltato": "non_collegato"}
    else:
        giorni = giorni_giro() if stato.get("ultimo_import") else GIORNI_PRIMO_GIRO
        dal = rilettura_in_attesa(stato)
        if dal:
            giorni = max(giorni, (date.today() - date.fromisoformat(dal)).days + 1)
        try:
            risultato = await importa_nuovi(db, client, giorni=giorni)
            esito = {"eseguito_il": adesso, "giorni": giorni,
                     "importati": risultato["importati"],
                     "gia_presenti": risultato["gia_presenti"],
                     "da_verificare_esclusi": risultato["da_verificare_esclusi"]}
            if dal:
                esito["rilettura_dal"] = dal
                await db["sistema_stato"].update_one(
                    {"chiave": CHIAVE_SESSIONE}, {"$set": {"rilettura_dal": dal}}, upsert=True,
                )
        except ErroreLettura as exc:
            esito = {"eseguito_il": adesso, "giorni": giorni, "errore": exc.stato}
            if dal:
                esito["rilettura_dal"] = dal
            logger.warning("[enable-banking] giro automatico non riuscito: %s", exc)
    await db["sistema_stato"].update_one(
        {"chiave": CHIAVE_SESSIONE}, {"$set": {"giro_automatico": esito}}, upsert=True,
    )
    return esito
