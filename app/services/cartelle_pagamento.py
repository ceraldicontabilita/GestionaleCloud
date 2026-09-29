"""Cartella di pagamento dell'Agente della riscossione (contravvenzioni e ruoli).

La cartella e' un fatto autorevole: crea subito l'attesa «da pagare» (una prova
successiva non crea mai l'obbligo che dovrebbe dimostrare). La soddisfa solo la
ricevuta di pagamento con lo **stesso IUV** e lo stesso importo al centesimo; con
lo stesso IUV e importo diverso resta ``DA_VERIFICARE``.

- Il termine e' 60 giorni dalla **notifica**, e la data di notifica non sta nel
  PDF: finche' il titolare non la dice, la scadenza resta vuota (mai inventata).
- Ogni riga di ruolo porta il numero del verbale e la targa: il verbale si
  aggancia solo se e' uno solo e la targa coincide; altrimenti si mostrano i
  candidati e nessun collegamento viene applicato.
- L'originale si conserva una volta sola per SHA-256, come gli atti giudiziari.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from app.services.expectation_policy import (
    ExpectationStatus, expectation_evidence_fields, expectation_fields,
)

logger = logging.getLogger(__name__)

COLL = "cartelle_pagamento"
PREFISSO_BLOB = "cartella-pagamento:"
TIPO_ATTESA = "CARTELLA_DA_PAGARE"
OWNER_ATTESA = "fiscale"
GIORNI_PAGAMENTO = 60

_NUMERO = re.compile(r"CARTELLA DI PAGAMENTO N\.\s*(\d{3}\s+\d{4}\s+\d{8}\s+\d{2}\s*/\s*\d{3})")
_RUOLO = re.compile(r"RUOLO N\.\s*(\d{4}/\d+)")
_ENTE = re.compile(r"RUOLO EMESSO DA\s*\n\s*([^\n]+)")
# Codice avviso pagoPA dell'Agente della riscossione: cifra iniziale + IUV di 17 cifre (800…).
_AVVISO = re.compile(r"\b(1800\d{14})\b")
_CBILL = re.compile(r"\b([A-Z0-9]{5})\s*\n\s*1800\d{14}\b")
_CF = re.compile(r"Destinatario\s+Cod\.\s*Fiscale\s+(\d{11})")
_SOMME = re.compile(r"\n\s*([\d.]+,\d{2})\s*\n\s*([\d.]+,\d{2})\s*\n\s*([\d.]+,\d{2})\s*\n")
_RIGA = re.compile(
    r"^\s*(\d{1,3})\s*\n\s*(\d{4})\s*\n\s*(\d{3,5})\s+([^\n]+)\n\s*([\d.]+,\d{2})\s*\n"
    r"(?:\s*VER\.\s*(\S+)\s+(\d{2}/\d{2}/\d{4})\s+NOT\.\s*IL\s+(\d{2}/\d{2}/\d{4})\s+TG\.\s*([A-Z0-9]+))?",
    re.MULTILINE,
)


def e_cartella_pagamento(testo: str) -> bool:
    """Vero se il testo e' una cartella di pagamento dell'Agente della riscossione."""
    compatto = re.sub(r"\s+", " ", testo or "").upper()
    return ("CARTELLA DI PAGAMENTO N." in compatto
            and "AGENZIA DELLE ENTRATE-RISCOSSIONE" in compatto.replace(" - ", "-"))


def _importo(valore: str) -> Decimal:
    return Decimal(valore.replace(".", "").replace(",", "."))


def _testo(contenuto: bytes) -> str:
    try:
        import fitz

        with fitz.open(stream=contenuto, filetype="pdf") as documento:
            return "\n".join(pagina.get_text() for pagina in documento)
    except Exception as exc:  # noqa: BLE001 - un PDF illeggibile non e' una cartella
        logger.info("Cartella di pagamento non leggibile: %s: %s", type(exc).__name__, exc)
        return ""


def _normalizza_numero(numero: str) -> str:
    return re.sub(r"\s+", " ", numero.replace(" /", "/").replace("/ ", "/")).strip()


def leggi_cartella(testo: str) -> Optional[Dict[str, Any]]:
    """I dati della cartella, o None se non lo e'. Importi in stringa, mai float."""
    if not e_cartella_pagamento(testo):
        return None
    numero = _NUMERO.search(testo)
    if not numero:
        return None
    ente = _ENTE.search(testo)
    ruolo = _RUOLO.search(testo)
    avviso = _AVVISO.search(testo)
    cbill = _CBILL.search(testo)
    cf = _CF.search(testo)
    righe: List[Dict[str, Any]] = []
    for m in _RIGA.finditer(testo):
        riga = {
            "progressivo": m.group(1), "anno": m.group(2), "codice_tributo": m.group(3),
            "descrizione": m.group(4).strip(), "importo": str(_importo(m.group(5))),
        }
        if m.group(6):
            riga.update({"numero_verbale": m.group(6).upper(), "data_verbale": m.group(7),
                         "data_notifica_verbale": m.group(8), "targa": m.group(9).upper()})
        righe.append(riga)
    somme = _SOMME.search(testo)
    ente_importo = diritti = totale = None
    if somme:
        ente_importo, diritti, totale = (_importo(somme.group(i)) for i in (1, 2, 3))
    somma_righe = sum((Decimal(r["importo"]) for r in righe), Decimal("0"))
    quadra = bool(
        righe and somme and somma_righe == ente_importo and ente_importo + diritti == totale
    )
    verbali = sorted({(r["numero_verbale"], r["targa"]) for r in righe if r.get("numero_verbale")})
    return {
        "numero_cartella": _normalizza_numero(numero.group(1)),
        "ente_creditore": ente.group(1).strip() if ente else None,
        "ruolo": ruolo.group(1) if ruolo else None,
        "codice_fiscale_destinatario": cf.group(1) if cf else None,
        "righe": righe,
        "importo_ente": str(ente_importo) if ente_importo is not None else None,
        "diritti_notifica": str(diritti) if diritti is not None else None,
        "totale": str(totale) if totale is not None else None,
        "importi_quadrano": quadra,
        "codice_avviso": avviso.group(1) if avviso else None,
        # Lo IUV e' il codice avviso senza la cifra iniziale (aux digit).
        "iuv": avviso.group(1)[1:] if avviso else None,
        "codice_cbill": cbill.group(1) if cbill else None,
        "verbali": [{"numero_verbale": n, "targa": t} for n, t in verbali],
        "termine": f"{GIORNI_PAGAMENTO} giorni dalla data di notifica",
    }


def scadenza_da_notifica(data_notifica: str) -> str:
    """60 giorni dalla notifica; un sabato o una domenica passa al lunedi' (festivita' escluse)."""
    giorno = date.fromisoformat(data_notifica) + timedelta(days=GIORNI_PAGAMENTO)
    while giorno.weekday() >= 5:
        giorno += timedelta(days=1)
    return giorno.isoformat()


def _archivio():
    from app.database import Database
    from app.services.blob_store import blob_store_per_runtime

    return blob_store_per_runtime(Database.db)


def _chiave(numero_verbale: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(numero_verbale or "").upper())


async def _candidati_verbale(db, numero: str, targa: str) -> List[Dict[str, Any]]:
    """I verbali in archivio con quel numero (e, se la scheda la ha, quella targa)."""
    chiave = _chiave(numero)
    trovati: List[Dict[str, Any]] = []
    for collezione in ("verbali_noleggio", "verbali_noleggio_completi"):
        async for v in db[collezione].find({}, {"_id": 0, "id": 1, "numero_verbale": 1, "targa": 1}):
            if _chiave(v.get("numero_verbale")) != chiave:
                continue
            if v.get("targa") and str(v["targa"]).upper() != targa:
                continue
            trovati.append({"collezione": collezione, "id": v.get("id"),
                            "numero_verbale": v.get("numero_verbale")})
    return trovati


async def collega_verbali(db, cartella_id: str) -> Dict[str, Any]:
    """Aggancia i verbali citati dalla cartella: solo se univoci (numero e targa)."""
    doc = await db[COLL].find_one({"id": cartella_id}, {"_id": 0})
    if not doc:
        return {"collegati": 0}
    collegati, candidati = [], {}
    for v in doc.get("verbali") or []:
        trovati = await _candidati_verbale(db, v["numero_verbale"], v["targa"])
        if len(trovati) == 1:
            collegati.append({**v, **trovati[0]})
        elif trovati:
            candidati[v["numero_verbale"]] = trovati
    await db[COLL].update_one({"id": cartella_id}, {"$set": {
        "verbali_collegati": collegati, "verbali_candidati": candidati,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }})
    return {"collegati": len(collegati), "candidati": sum(len(x) for x in candidati.values())}


async def registra_cartella(
    db, nome: str, contenuto: bytes, *, drive_file_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Conserva l'originale, apre l'attesa «da pagare» e cerca ricevuta e verbale."""
    dati = leggi_cartella(_testo(contenuto))
    if not dati:
        return {"success": False, "message": "Non e' una cartella di pagamento riconoscibile"}
    ora = datetime.now(timezone.utc).isoformat()
    id_cartella = "cartella:" + re.sub(r"\W+", "", dati["numero_cartella"])
    esistente = await db[COLL].find_one({"id": id_cartella}, {"_id": 0, "id": 1})
    if esistente:
        await db[COLL].update_one({"id": id_cartella}, {"$set": {"ultimo_caricamento": ora}})
        return {"success": True, "duplicate": True, "id": id_cartella, **dati}
    impronta = hashlib.sha256(contenuto).hexdigest()
    documento: Dict[str, Any] = {
        "id": id_cartella, "sha256": impronta, "nome": nome, "dimensione": len(contenuto),
        "mime": "application/pdf", "caricato_il": ora, "ultimo_caricamento": ora,
        "drive_file_id": drive_file_id, "data_notifica": None, "scadenza": None,
        **dati,
        **expectation_fields(
            expectation_type=TIPO_ATTESA, owner=OWNER_ATTESA, source_fact_id=id_cartella,
        ),
    }
    if not dati["importi_quadrano"]:
        # Le somme non tornano: si conserva, ma non si dichiara un dovuto certo.
        documento["expectation_status"] = ExpectationStatus.DA_VERIFICARE.value
    contenuto_b64 = base64.b64encode(contenuto).decode("ascii")
    archivio = _archivio()
    if getattr(archivio, "persistent", False):
        documento["blob_key"] = PREFISSO_BLOB + impronta
        await archivio.put(documento["blob_key"], contenuto_b64)
    else:
        documento["contenuto_b64"] = contenuto_b64
    await db[COLL].insert_one(documento)
    verbali = await collega_verbali(db, id_cartella)
    ricevuta = await chiudi_da_ricevuta_esistente(db, id_cartella)
    return {"success": True, "duplicate": False, "id": id_cartella, **dati,
            "verbali": verbali, "ricevuta": ricevuta}


async def imposta_notifica(db, cartella_id: str, data_notifica: str) -> Dict[str, Any]:
    """Il titolare dice quando la cartella e' stata notificata: parte il termine di 60 giorni."""
    try:
        scadenza = scadenza_da_notifica(data_notifica)
    except ValueError:
        return {"success": False, "message": "Data di notifica non valida (aaaa-mm-gg)"}
    trovata = await db[COLL].find_one({"id": cartella_id}, {"_id": 0, "id": 1})
    if not trovata:
        return {"success": False, "message": "Cartella non trovata"}
    await db[COLL].update_one({"id": cartella_id}, {"$set": {
        "data_notifica": data_notifica, "scadenza": scadenza,
        "scadenza_nota": "60 giorni dalla notifica, salvo festivita'",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }})
    return {"success": True, "scadenza": scadenza}


def _stesso_importo(totale: Optional[str], importo: Any) -> bool:
    try:
        return totale is not None and Decimal(str(totale)) == Decimal(str(importo)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return False


async def _applica_ricevuta(db, cartella: Dict[str, Any], ricevuta: Dict[str, Any]) -> str:
    importo = ricevuta.get("operation_amount")
    if importo is None:
        importo = ricevuta.get("importo")
    torna = _stesso_importo(cartella.get("totale"), importo)
    campi = expectation_evidence_fields(satisfied=torna, evidence_ids=[str(ricevuta.get("id") or "")])
    await db[COLL].update_one({"id": cartella["id"]}, {"$set": {
        **campi, "ricevuta_id": ricevuta.get("id"),
        "data_pagamento": ricevuta.get("data_pagamento"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }})
    return campi["expectation_status"]


async def chiudi_da_ricevuta(db, ricevuta: Dict[str, Any]) -> Optional[str]:
    """Arriva una ricevuta: se cita lo IUV di una cartella aperta, la chiude (importo uguale) o la segnala."""
    iuv = str(ricevuta.get("identificativo_bolletta") or ricevuta.get("iuv") or "").strip()
    if not iuv:
        return None
    cartella = await db[COLL].find_one({"iuv": iuv}, {"_id": 0})
    if not cartella:
        return None
    return await _applica_ricevuta(db, cartella, ricevuta)


async def chiudi_da_ricevuta_esistente(db, cartella_id: str) -> Optional[str]:
    """Arriva la cartella: se la ricevuta con il suo IUV c'e' gia', l'attesa nasce gia' chiusa."""
    cartella = await db[COLL].find_one({"id": cartella_id}, {"_id": 0})
    if not cartella or not cartella.get("iuv"):
        return None
    ricevuta = await db["ricevute_pagopa"].find_one(
        {"identificativo_bolletta": cartella["iuv"]}, {"_id": 0, "pdf_data": 0},
    )
    return await _applica_ricevuta(db, cartella, ricevuta) if ricevuta else None


async def contenuto(db, cartella_id: str) -> Optional[Tuple[bytes, str]]:
    """(byte, nome) dell'originale, o None."""
    doc = await db[COLL].find_one({"id": cartella_id}, {"_id": 0})
    if not doc:
        return None
    dati = doc.get("contenuto_b64")
    if not dati and doc.get("blob_key"):
        dati = await _archivio().get(doc["blob_key"])
    if not dati:
        return None
    return base64.b64decode(dati), doc.get("nome") or f"cartella_{cartella_id[-12:]}.pdf"
