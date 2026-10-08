"""Atti giudiziari (sentenza, precetto, relata, attestazione) e i pagamenti che ne derivano.

Una causa persa lascia spese di lite da pagare a piu' controparti, a volte a
rate e dopo anni. I bonifici escono dal conto senza fattura, e senza l'atto
accanto nessuno sa piu' perche' sono usciti. Qui:

- l'originale di ogni atto si conserva una volta sola, per impronta SHA-256,
  in ``gestionale.blobs`` (come gli estratti conto, ``estratti_originali``);
- il registro ``atti_giudiziari`` dice tipo, numero della sentenza, ruolo
  generale e tribunale: tutti gli atti della stessa sentenza sono un
  fascicolo (``sentenza:<numero>/<anno>``);
- un movimento del conto BPM o della carta SumUp entra nel fascicolo se la
  causale **cita** la sentenza o il ruolo generale, oppure se il titolare l'ha
  **dichiarato** (``fascicolo_dichiarato`` sul movimento): mai per importo o
  per nome della controparte, che puo' essere una controparte di altro.

Il movimento del fascicolo va in Prima Nota come «Spese legali e contenzioso»
(``proiezione_bancaria``); la contropartita si decide in ``mapping_piano_conti``.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

COLL = "atti_giudiziari"
PREFISSO_BLOB = "atto-giudiziario:"
# I conti in cui un'uscita puo' essere una spesa di lite.
COLLEZIONI_MOVIMENTI = ("estratto_conto_movimenti", "sumup_conto_movimenti")

TIPO_SENTENZA = "sentenza"
TIPO_PRECETTO = "atto_di_precetto"
TIPO_RELATA = "relata_di_notifica"
TIPO_ATTESTAZIONE = "attestazione_di_conformita"

ETICHETTE = {
    TIPO_SENTENZA: "Sentenza",
    TIPO_PRECETTO: "Atto di precetto",
    TIPO_RELATA: "Relata di notifica",
    TIPO_ATTESTAZIONE: "Attestazione di conformità",
}

_SENTENZA = re.compile(r"SENTENZA[^0-9]{0,80}?N\.?\s*(\d{2,6})\s*/\s*(\d{4})")
_RG = (
    re.compile(r"\bR\.?\s*G\.?(?:\s*A\.?\s*C\.?)?[^0-9]{0,12}(\d{3,6})\s*/\s*(\d{4})"),
    re.compile(r"\b(\d{3,6})\s*/\s*(\d{4})\s*R\.?\s*G\.?"),
)
_TRIBUNALE = re.compile(r"TRIBUNALE DI ([A-Z]+)")
_IMPORTO_INTIMATO = re.compile(r"COMPLESSIVA SOMMA DI\s*€\.?\s*([\d.]+,\d{2})")

# Citazione nella causale di un bonifico: «sentenza 8657/21», «RG 35308/2016».
_CITA_SENTENZA = re.compile(r"SENTENZ\w*\D{0,20}?(\d{2,6})\s*/\s*(\d{2,4})\b")
_CITA_RG = re.compile(r"\bN?R\.?\s?G\.?\D{0,6}?(\d{3,6})\s*/\s*(\d{2,4})\b")


def _anno(valore: str) -> str:
    return valore if len(valore) == 4 else f"20{valore[-2:]}"


def _numero(numero: str, anno: str) -> str:
    return f"{int(numero)}/{_anno(anno)}"


def _testo(contenuto: bytes) -> str:
    try:
        import fitz

        with fitz.open(stream=contenuto, filetype="pdf") as documento:
            testo = "".join(pagina.get_text() for pagina in documento)
    except Exception as exc:  # noqa: BLE001 - un PDF illeggibile non e' un atto
        logger.info("Atto giudiziario non leggibile: %s: %s", type(exc).__name__, exc)
        return ""
    return re.sub(r"\s+", " ", testo).upper()


def tipo_atto(testo: str) -> Optional[str]:
    """Il tipo di atto dal testo (maiuscolo, spazi compattati), o None.

    Serve il tribunale e il numero di una sentenza: un atto che non cita la
    sua sentenza non si sa a quale causa appartenga.
    """
    if "TRIBUNALE" not in testo or not _SENTENZA.search(testo):
        return None
    if "RELATA DI NOTIFICA" in testo[:400]:
        return TIPO_RELATA
    if "IN NOME DEL POPOLO ITALIANO" in testo:
        return TIPO_SENTENZA
    if "ATTESTO CHE" in testo:
        return TIPO_ATTESTAZIONE
    if "ATTO DI PRECETTO" in testo:
        return TIPO_PRECETTO
    return None


def leggi_atto(contenuto: bytes, testo: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Tipo, sentenza, ruolo generale, tribunale e (per il precetto) la somma intimata."""
    testo = testo if testo is not None else _testo(contenuto)
    tipo = tipo_atto(testo)
    if not tipo:
        return None
    sentenza = _SENTENZA.search(testo)
    rg = next((m for m in (p.search(testo) for p in _RG) if m), None)
    tribunale = _TRIBUNALE.search(testo)
    atto: Dict[str, Any] = {
        "tipo": tipo,
        "etichetta": ETICHETTE[tipo],
        "numero_sentenza": _numero(*sentenza.groups()),
        "ruolo_generale": _numero(*rg.groups()) if rg else None,
        "tribunale": tribunale.group(1).title() if tribunale else None,
    }
    atto["fascicolo"] = f"sentenza:{atto['numero_sentenza']}"
    if tipo == TIPO_PRECETTO:
        importo = _IMPORTO_INTIMATO.search(testo)
        if importo:
            atto["importo_intimato"] = importo.group(1).replace(".", "").replace(",", ".")
    return atto


def _archivio():
    from app.database import Database
    from app.services.blob_store import blob_store_per_runtime

    return blob_store_per_runtime(Database.db)


async def registra_atto(
    db, nome: str, contenuto: bytes, *, drive_file_id: Optional[str] = None,
    atto: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Conserva l'originale e registra l'atto; lo stesso file due volte e' un solo atto."""
    atto = atto or leggi_atto(contenuto)
    if not atto:
        return {"success": False, "message": "Non e' un atto giudiziario riconoscibile"}
    impronta = hashlib.sha256(contenuto).hexdigest()
    ora = datetime.now(timezone.utc).isoformat()
    esistente = await db[COLL].find_one({"id": impronta}, {"_id": 0, "id": 1})
    if esistente:
        await db[COLL].update_one({"id": impronta}, {"$set": {"ultimo_caricamento": ora}})
        return {"success": True, "duplicate": True, "id": impronta, **atto}
    documento: Dict[str, Any] = {
        "id": impronta, "nome": nome, "dimensione": len(contenuto), "mime": "application/pdf",
        "caricato_il": ora, "ultimo_caricamento": ora, "drive_file_id": drive_file_id, **atto,
    }
    archivio = _archivio()
    if getattr(archivio, "persistent", False):
        if not drive_file_id:
            from app.services.email_drive_archive import archive_binary_copy

            esito = await asyncio.to_thread(
                archive_binary_copy, contenuto, nome,
                source="atti_giudiziari", area=COLL,
            )
            if esito.get("status") not in {"archived", "duplicate"}:
                raise RuntimeError("Originale giudiziario non verificato su Drive")
            drive_file_id = esito["drive_file_id"]
            documento["drive_md5"] = esito.get("md5")
        documento["drive_file_id"] = drive_file_id
        documento["drive_archive_status"] = "verified"
    else:
        # Senza Supabase (test, sviluppo) il contenuto resta nel registro.
        documento["contenuto_b64"] = base64.b64encode(contenuto).decode("ascii")
    await db[COLL].insert_one(documento)
    return {"success": True, "duplicate": False, "id": impronta, **atto}


async def contenuto(db, atto_id: str) -> Optional[Tuple[bytes, str]]:
    """(byte, nome) dell'originale, o None se non c'e'."""
    doc = await db[COLL].find_one({"id": atto_id}, {"_id": 0})
    if not doc:
        return None
    if doc.get("drive_file_id"):
        from app.services.drive_download import scarica_originale

        originale = await scarica_originale(str(doc["drive_file_id"]), md5=doc.get("drive_md5"))
        if originale:
            return originale, doc.get("nome") or f"atto_{atto_id[:12]}.pdf"
    dati = doc.get("contenuto_b64")
    if not dati and doc.get("blob_key"):
        dati = await _archivio().get(doc["blob_key"])
    if not dati:
        return None
    return base64.b64decode(dati), doc.get("nome") or f"atto_{atto_id[:12]}.pdf"


def numeri_citati(causale: str) -> set:
    """Le sentenze e i ruoli generali citati in una causale, come «8657/2021»."""
    testo = str(causale or "").upper()
    return {_numero(*m.groups()) for regola in (_CITA_SENTENZA, _CITA_RG) for m in regola.finditer(testo)}


def _testo_movimento(mov: Dict[str, Any]) -> str:
    return " ".join(str(mov.get(campo) or "") for campo in ("causale", "descrizione", "descrizione_originale"))


def fascicolo_del_movimento(
    mov: Dict[str, Any], fascicoli: Dict[str, Dict[str, Any]],
) -> Optional[Tuple[str, str]]:
    """(fascicolo, come) se il movimento appartiene a una causa, altrimenti None.

    ``fascicoli`` mappa ogni numero noto (sentenza e ruolo generale) al suo
    fascicolo. Vince la dichiarazione del titolare; altrimenti la causale deve
    citare il numero, e un solo fascicolo.
    """
    dichiarato = str(mov.get("fascicolo_dichiarato") or "").strip()
    if dichiarato:
        chiave = dichiarato if dichiarato.startswith("sentenza:") else None
        if chiave is None:
            citati = numeri_citati(f"SENTENZA {dichiarato}") | numeri_citati(f"RG {dichiarato}")
            trovati = {fascicoli[n]["fascicolo"] for n in citati if n in fascicoli}
            chiave = trovati.pop() if len(trovati) == 1 else None
        if chiave:
            return chiave, "dichiarato_titolare"
    trovati = {fascicoli[n]["fascicolo"] for n in numeri_citati(_testo_movimento(mov)) if n in fascicoli}
    if len(trovati) == 1:
        return trovati.pop(), "citato_in_causale"
    return None


async def _indice_fascicoli(db) -> Dict[str, Dict[str, Any]]:
    indice: Dict[str, Dict[str, Any]] = {}
    for atto in await db[COLL].find(
        {}, {"_id": 0, "id": 1, "fascicolo": 1, "numero_sentenza": 1, "ruolo_generale": 1},
    ).to_list(None):
        for numero in (atto.get("numero_sentenza"), atto.get("ruolo_generale")):
            if numero:
                indice[numero] = atto
    return indice


async def atti_del_fascicolo(db, fascicolo: str) -> List[Dict[str, Any]]:
    """Gli atti di una causa, senza contenuto: la sentenza per prima."""
    ordine = [TIPO_SENTENZA, TIPO_PRECETTO, TIPO_RELATA, TIPO_ATTESTAZIONE]
    atti = await db[COLL].find(
        {"fascicolo": fascicolo},
        {"_id": 0, "id": 1, "tipo": 1, "etichetta": 1, "nome": 1, "numero_sentenza": 1,
         "ruolo_generale": 1, "tribunale": 1},
    ).to_list(None)
    return sorted(atti, key=lambda a: (ordine.index(a["tipo"]) if a.get("tipo") in ordine else 9,
                                       str(a.get("nome") or "")))


async def collega_pagamenti(
    db, collezioni: Iterable[str] = COLLEZIONI_MOVIMENTI,
) -> Dict[str, Any]:
    """Aggancia al fascicolo le uscite che lo citano o che il titolare vi ha messo.

    Idempotente: una riga gia' agganciato allo stesso fascicolo non si riscrive.
    """
    fascicoli = await _indice_fascicoli(db)
    esito: Dict[str, Any] = {"fascicoli": len({a["fascicolo"] for a in fascicoli.values()}),
                             "collegati": 0, "gia_collegati": 0, "dettaglio": []}
    if not fascicoli:
        return esito
    ora = datetime.now(timezone.utc).isoformat()
    for collezione in collezioni:
        movimenti = await db[collezione].find(
            {"$or": [
                {"fascicolo_dichiarato": {"$exists": True}},
                {"causale": {"$regex": "SENTENZ|R\\.?\\s?G", "$options": "i"}},
                {"descrizione": {"$regex": "SENTENZ|R\\.?\\s?G", "$options": "i"}},
            ]},
            {"_id": 0, "id": 1, "data": 1, "importo": 1, "causale": 1, "descrizione": 1,
             "descrizione_originale": 1, "fascicolo_dichiarato": 1, "fascicolo_giudiziario": 1},
        ).to_list(None)
        for mov in movimenti:
            trovato = fascicolo_del_movimento(mov, fascicoli)
            if not trovato or float(mov.get("importo") or 0) >= 0:
                continue
            fascicolo, come = trovato
            if mov.get("fascicolo_giudiziario") == fascicolo:
                esito["gia_collegati"] += 1
                continue
            await db[collezione].update_one({"id": mov["id"]}, {"$set": {
                "fascicolo_giudiziario": fascicolo,
                "fascicolo_collegato_da": come,
                "fascicolo_collegato_at": ora,
            }})
            esito["collegati"] += 1
            esito["dettaglio"].append({"movimento_id": mov["id"], "fascicolo": fascicolo,
                                       "come": come, "importo": mov.get("importo")})
    return esito


async def collega_e_registra(db) -> Dict[str, Any]:
    """All'arrivo di un atto: aggancia le uscite e le porta in Prima Nota Banca.

    La Prima Nota la scrive ``proiezione_bancaria`` (la stessa del giro dei 30
    minuti), solo per i movimenti del fascicolo ancora senza riga, ognuno sul
    conto del suo estratto.
    """
    from app.services import conti_pos
    from app.services.proiezione_bancaria import proietta_movimenti_bancari_semantici

    esito = await collega_pagamenti(db)
    conti = {"estratto_conto_movimenti": conti_pos.CONTO_BPM,
             "sumup_conto_movimenti": conti_pos.CONTO_SUMUP_MASTERCARD}
    registrati = 0
    for collezione, conto in conti.items():
        ids = [
            m["id"] for m in await db[collezione].find(
                {"fascicolo_giudiziario": {"$exists": True}},
                {"_id": 0, "id": 1, "prima_nota_banca_id": 1},
            ).to_list(None)
            if not m.get("prima_nota_banca_id")
        ]
        if ids:
            proiezione = await proietta_movimenti_bancari_semantici(
                db, movimento_ids=ids, collezione=collezione, conto_contabile=conto,
            )
            registrati += int(proiezione.get("proiettati") or 0)
    esito["prima_nota_scritte"] = registrati
    return esito
