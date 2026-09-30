"""Da dove arriva un documento e in che stato sta: un vocabolario solo (MINI-01).

Ogni documento importato (modello F24, quietanza, LIPE, cedolino, ricevuta di
bonifico) porta ``canale``: il canale d'ingresso in quattro valori fissi,
``posta`` | ``drive`` | ``caricato`` | ``altro``. Il dettaglio grezzo resta nel
campo storico di ogni collezione (``import_source``, ``fonte``, ``source``,
``origine``: nomi diversi, valori liberi come ``gmail_scan`` o
``documenti_upload_auto``) e da quello ``canale_da_fonte`` ricava il canale.

Il campo si chiama ``canale`` e non ``fonte`` perché ``fonte`` è già preso con
valori grezzi (quietanze) o con l'archivio di provenienza (``gestionale_cloud``
sui cedolini HR, ``fiscal_documents`` nel registro F24).

Gli stati espliciti che nascono qui: una LIPE depositata è ``canonica`` finché
una ritrasmissione (protocollo più alto) non la ``sostituisce``; una ricevuta di
bonifico nasce ``documentato`` (PDF letto, nessuna prova bancaria) e diventa
``documento_associato_attesa_banca`` quando trova il suo stipendio, poi la
banca la riconcilia. Gli alert sono ``aperto`` | ``risolto`` | ``ignorato``.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

CANALE_POSTA = "posta"
CANALE_DRIVE = "drive"
CANALE_CARICATO = "caricato"
CANALE_ALTRO = "altro"

# Ordine fisso: e' anche l'ordine con cui si elencano le origini di un documento.
CANALI: Dict[str, str] = {
    CANALE_POSTA: "Posta",
    CANALE_DRIVE: "Drive",
    CANALE_CARICATO: "Caricato",
    CANALE_ALTRO: "Altro",
}

_SEGNI_POSTA = ("gmail", "email", "mail", "inbox", "posta", "pec", "imap")
_SEGNI_CARICATO = ("upload", "manuale", "caricat", "commercialista_upload", "libro_unico")

STATO_LIPE_CANONICA = "canonica"
STATO_LIPE_SOSTITUITA = "sostituita"
STATI_LIPE_PERIODO = (STATO_LIPE_CANONICA, STATO_LIPE_SOSTITUITA)

STATO_BONIFICO_DOCUMENTATO = "documentato"
STATO_BONIFICO_ASSOCIATO_ATTESA_BANCA = "documento_associato_attesa_banca"
STATO_BONIFICO_RICONCILIATO = "riconciliato"
STATI_BONIFICO_DOCUMENTO = (
    STATO_BONIFICO_DOCUMENTATO,
    STATO_BONIFICO_ASSOCIATO_ATTESA_BANCA,
    STATO_BONIFICO_RICONCILIATO,
)

STATO_ALERT_APERTO = "aperto"
STATO_ALERT_RISOLTO = "risolto"
STATO_ALERT_IGNORATO = "ignorato"
STATI_ALERT = (STATO_ALERT_APERTO, STATO_ALERT_RISOLTO, STATO_ALERT_IGNORATO)


def canale_da_fonte(fonte: Any) -> Optional[str]:
    """Riduce un valore grezzo di provenienza a uno dei quattro canali.

    ``None`` solo per un valore vuoto: un valore scritto ma sconosciuto è
    ``altro``, così un nuovo scrittore che inventa un nome non sparisce dai
    conteggi per canale.
    """
    s = str(fonte or "").strip().lower()
    if not s:
        return None
    if s in CANALI:
        return s
    if "drive" in s:
        return CANALE_DRIVE
    if any(k in s for k in _SEGNI_POSTA):
        return CANALE_POSTA
    if any(k in s for k in _SEGNI_CARICATO):
        return CANALE_CARICATO
    return CANALE_ALTRO


def canale_obbligatorio(fonte: Any, *, drive_file_id: Any = None) -> str:
    """Il canale da scrivere alla creazione: mai vuoto.

    Un'etichetta che dice il canale vince: un allegato di posta archiviato su
    Drive (`email_drive_archive`) resta «posta». L'id Drive decide solo quando
    l'etichetta manca o non dice niente.
    """
    canale = canale_da_fonte(fonte)
    if canale and canale != CANALE_ALTRO:
        return canale
    if drive_file_id:
        return CANALE_DRIVE
    return canale or CANALE_ALTRO


def canali_documento(doc: Dict[str, Any], *, fonti_registro: Iterable[str] = ()) -> List[str]:
    """Tutti i canali da cui è arrivato un documento, nell'ordine di ``CANALI``.

    Legge il campo ``canale`` scritto alla creazione e, per l'archivio che non
    lo ha, i campi grezzi (``fonte``, ``source``, ``origine``, ``source_module``)
    e le copie in ``source_occurrences``. ``fonti_registro`` sono i valori di
    ``fonte`` che indicano un archivio (es. ``quietanze_f24``), non un canale.
    """
    fonti_registro = set(fonti_registro)
    trovati = set()
    c = canale_da_fonte(doc.get("canale"))
    if c:
        trovati.add(c)
    for campo in ("fonte", "source", "origine", "source_module", "import_source"):
        valore = doc.get(campo)
        if campo == "fonte" and valore in fonti_registro:
            continue
        c = canale_da_fonte(valore)
        if c:
            trovati.add(c)
    for occ in doc.get("source_occurrences") or []:
        if isinstance(occ, dict):
            c = canale_da_fonte(occ.get("source") or occ.get("import_source"))
            if c:
                trovati.add(c)
            if occ.get("drive_file_id"):
                trovati.add(CANALE_DRIVE)
    if doc.get("drive_file_id"):
        trovati.add(CANALE_DRIVE)
    if doc.get("email_info") or doc.get("gmail_message_id") or doc.get("email_id"):
        trovati.add(CANALE_POSTA)
    return [c for c in CANALI if c in trovati] or [CANALE_ALTRO]
