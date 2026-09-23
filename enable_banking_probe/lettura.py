"""Lettura completa dei movimenti Banco BPM e confronto con l'export CSV.

Solo lettura, solo memoria: niente Supabase, niente scritture. Il probe gira
con le sole dipendenze di ``enable_banking_probe`` (FastAPI, httpx, PyJWT),
quindi qui si usa la libreria standard.

Il confronto dei doppioni **non** e' un secondo motore: carica
``accoppia`` da ``app/services/doppioni_estratto_conto.py`` (lo stesso che il
gestionale usa fra due export BPM) leggendo il file, senza importare il
pacchetto ``app`` e le sue dipendenze.
"""
from __future__ import annotations

import asyncio
import csv
import hashlib
import importlib.util
import io
import json
import re
from collections import Counter
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

# Una banca PSD2 restituisce pagine brevi: 500 pagine sono ben oltre un anno
# di movimenti. Superarle vuol dire che il cursore non avanza.
MAX_PAGINE = 500
TENTATIVI_TEMPORANEI = 3

# Codici Enable Banking (ErrorCode) che vogliono dire «il consenso non c'e'
# piu'»: si ricollega il conto, riprovare non serve.
ERRORI_CONSENSO = {
    "EXPIRED_SESSION", "CLOSED_SESSION", "REVOKED_SESSION", "SESSION_DOES_NOT_EXIST",
    "UNAUTHORIZED_ACCESS", "ASPSP_PSU_ACTION_REQUIRED",
}
# Limite di letture della banca (PSD2: poche al giorno senza l'utente
# presente). Riprovare consuma altre letture: ci si ferma.
ERRORI_LIMITE = {"ASPSP_RATE_LIMIT_EXCEEDED"}
ERRORI_TEMPORANEI = {"ASPSP_TIMEOUT", "ASPSP_ERROR", "TEMPORARILY_UNAVAILABLE", "TIMEOUT"}

_PERCORSO_DOPPIONI = (
    Path(__file__).resolve().parent.parent / "app" / "services" / "doppioni_estratto_conto.py"
)
_doppioni = None


def modulo_doppioni():
    """Il motore dei doppioni del gestionale, caricato dal suo file."""
    global _doppioni
    if _doppioni is None:
        spec = importlib.util.spec_from_file_location(
            "gestionale_doppioni_estratto_conto", _PERCORSO_DOPPIONI
        )
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        _doppioni = modulo
    return _doppioni


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


async def _get_json(
    client, url: str, *, headers: Dict[str, str], params: Dict[str, str],
    attendi: Callable[[float], Awaitable[None]],
) -> Dict[str, Any]:
    """GET con al piu' tre tentativi sui soli errori temporanei."""
    for tentativo in range(TENTATIVI_TEMPORANEI):
        risposta = await client.get(url, headers=headers, params=params)
        try:
            corpo = risposta.json()
        except Exception:
            corpo = None
        if risposta.status_code == 200 and isinstance(corpo, dict):
            return corpo
        stato = classifica_errore(risposta.status_code, corpo if isinstance(corpo, dict) else None)
        codice = str((corpo or {}).get("error") or "") if isinstance(corpo, dict) else ""
        if stato != "temporaneo" or tentativo == TENTATIVI_TEMPORANEI - 1:
            raise ErroreLettura(stato, risposta.status_code, codice)
        await attendi(2 ** (tentativo + 1))
    raise ErroreLettura("temporaneo", 0)  # irraggiungibile: il ciclo solleva prima


async def leggi_transazioni(
    client, url: str, *, headers: Callable[[], Dict[str, str]],
    date_from: str, date_to: Optional[str] = None,
    attendi: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> Dict[str, Any]:
    """Tutte le pagine di ``/transactions`` per il periodo richiesto.

    Ritorna i movimenti contabilizzati (``BOOK``) e, a parte, il conteggio
    degli altri stati: un movimento in attesa cambia riferimento quando viene
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
        "fonte": "enable_banking",
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


def _data_csv(valore: str) -> Optional[str]:
    try:
        return datetime.strptime(valore.strip().strip('"'), "%d/%m/%Y").date().isoformat()
    except ValueError:
        return None


def _importo_csv(valore: str) -> Optional[Decimal]:
    testo = valore.strip().strip('"').replace(" ", "")
    if "," in testo:
        testo = testo.replace(".", "").replace(",", ".")
    return _importo(testo)


def leggi_csv_bpm(contenuto: bytes) -> Dict[str, Any]:
    """L'export «Elenco entrate/uscite» di Banco BPM (separatore ``;``).

    Le righe illeggibili si contano, non si scartano in silenzio.
    """
    testo = None
    for codifica in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            testo = contenuto.decode(codifica)
            break
        except UnicodeDecodeError:
            continue
    if testo is None:
        raise ValueError("CSV non decodificabile")
    lettore = csv.DictReader(io.StringIO(testo), delimiter=";")
    colonne = {c.strip().strip('"') for c in (lettore.fieldnames or [])}
    if not {"Data contabile", "Importo", "Descrizione"} <= colonne:
        raise ValueError("Non e' l'export Banco BPM «Elenco entrate/uscite»")
    movimenti, illeggibili = [], 0
    for riga in lettore:
        riga = {str(k).strip().strip('"'): (v or "") for k, v in riga.items() if k}
        data = _data_csv(riga.get("Data contabile", ""))
        importo = _importo_csv(riga.get("Importo", ""))
        if not data or importo is None:
            illeggibili += 1
            continue
        movimenti.append({
            "fonte": "csv_bpm",
            "banca": "Banco BPM",
            "conto": maschera_iban(riga.get("Rapporto", "")),
            "data": data,
            "data_valuta": _data_csv(riga.get("Data valuta", "")),
            "importo": importo,
            "divisa": (riga.get("Divisa") or "EUR").strip() or "EUR",
            "tipo": "uscita" if importo < 0 else "entrata",
            "descrizione_originale": re.sub(r"\s+", " ", riga.get("Descrizione", "")).strip(),
        })
    return {"movimenti": movimenti, "illeggibili": illeggibili}


def confronta(api: List[Dict[str, Any]], csv_bpm: List[Dict[str, Any]]) -> Dict[str, Any]:
    """nuovi / gia' presenti / ambigui, sul solo periodo coperto da entrambi.

    Le coppie le trova ``accoppia`` del gestionale (giorno, segno, importo al
    centesimo e quante volte compaiono). Una coppia confermata da riferimento
    della banca, descrizione o numero d'assegno e' «gia' presente»; una coppia fatta solo per data e
    importo e' «ambigua» (DA_VERIFICARE): data e importo da soli non provano
    che sia la stessa operazione.
    """
    doppioni = modulo_doppioni()
    if not api or not csv_bpm:
        return {"periodo_comune": None, "nuovi": [], "gia_presenti": [], "ambigui": [],
                "solo_nel_csv": [], "fuori_periodo_api": len(api), "fuori_periodo_csv": len(csv_bpm)}
    inizio = max(min(m["data"] for m in api), min(m["data"] for m in csv_bpm))
    fine = min(max(m["data"] for m in api), max(m["data"] for m in csv_bpm))
    nel_periodo = lambda m: inizio <= m["data"] <= fine  # noqa: E731
    api_p = [m for m in api if nel_periodo(m)]
    csv_p = [m for m in csv_bpm if nel_periodo(m)]

    gia, ambigui, abbinati_api, abbinati_csv = [], [], set(), set()
    for nuovo, esistente in doppioni.accoppia(api_p, csv_p):
        abbinati_api.add(id(nuovo))
        abbinati_csv.add(id(esistente))
        a_nuovo, a_esistente = doppioni.numero_assegno(nuovo), doppioni.numero_assegno(esistente)
        certo = (
            doppioni.stesso_riferimento(nuovo, esistente)
            or doppioni.descrizione_canonica(nuovo) == doppioni.descrizione_canonica(esistente)
            or (a_nuovo and a_nuovo == a_esistente)
        )
        (gia if certo else ambigui).append({"api": nuovo, "csv": esistente})
    return {
        "periodo_comune": [inizio, fine] if inizio <= fine else None,
        "nuovi": [m for m in api_p if id(m) not in abbinati_api],
        "gia_presenti": gia,
        "ambigui": ambigui,
        "solo_nel_csv": [m for m in csv_p if id(m) not in abbinati_csv],
        "fuori_periodo_api": len(api) - len(api_p),
        "fuori_periodo_csv": len(csv_bpm) - len(csv_p),
    }


def riepilogo_periodo(movimenti: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not movimenti:
        return {"conteggio": 0, "dal": None, "al": None, "entrate": "0.00", "uscite": "0.00"}
    entrate = sum((m["importo"] for m in movimenti if m["importo"] > 0), Decimal("0.00"))
    uscite = sum((m["importo"] for m in movimenti if m["importo"] < 0), Decimal("0.00"))
    return {
        "conteggio": len(movimenti),
        "dal": min(m["data"] for m in movimenti),
        "al": max(m["data"] for m in movimenti),
        "entrate": str(entrate),
        "uscite": str(uscite),
    }


def oggi_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def data_it(valore: Optional[str]) -> str:
    if not valore:
        return "—"
    try:
        return date.fromisoformat(str(valore)[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return str(valore)
