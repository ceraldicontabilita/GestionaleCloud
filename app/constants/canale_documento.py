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

import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

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


# Etichette che dicono *chi* ha scritto la riga (motore, archivio di origine), non
# da che canale e' arrivato il file: `canale_da_fonte` le ridurrebbe a «altro» e
# nei conteggi per canale finirebbe un nome di programma.
ETICHETTE_NON_CANALE = frozenset({
    "cedolino_v2", "gestionale_cloud", "fiscal_documents", "salari_unificati_v2",
})
_CAMPI_ETICHETTA = ("fonte", "source", "origine", "import_source", "source_module",
                    "source_container", "gestionale_source")
# `AAAA-MM-GG_mittente@dominio_nomefile`: il nome con cui l'allegato di posta e'
# salvato (senza cartella davanti).
_PERCORSO_POSTA = re.compile(r"^\d{4}-\d{2}-\d{2}_[^/\s]+@[^/\s]+_")
# Le cartelle dello smistatore Drive (cartella unica e vecchi alberi per persona).
_CARTELLE_DRIVE = frozenset({"DA ELABORARE", "ELABORATE", "ERRORI"})


def _canale_da_percorso(percorso: Any) -> Optional[str]:
    testo = str(percorso or "").strip()
    if not testo:
        return None
    if _PERCORSO_POSTA.match(testo):
        return CANALE_POSTA
    parti = [p.strip().upper() for p in testo.split("/") if p.strip()]
    if len(parti) > 1 and any(p in _CARTELLE_DRIVE for p in parti[:-1]):
        return CANALE_DRIVE
    return None


def canale_ricavabile(doc: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """Il canale di un documento gia' in archivio, dai campi storici: ``(canale, regola)``.

    ``(None, None)`` se nessun campo lo dice: **non si inventa**. Il
    normalizzatore e' uno solo (``canale_da_fonte``); qui si decide l'ordine delle prove:

    1. ``canale`` gia' scritto: la prima copia arrivata lo ha fissato, non cambia;
    2. un'etichetta di provenienza che dice posta, Drive o caricato (le etichette
       che nominano un motore o un archivio, ``ETICHETTE_NON_CANALE``, non contano);
    3. posta: ``email_info``, id del messaggio, nome del file salvato dalla posta;
    4. Drive: id Drive scritto sul documento (anche nelle copie), cartella dello smistatore;
    5. un'etichetta scritta ma sconosciuta vale ``altro`` (come alla creazione).
    """
    esistente = canale_da_fonte(doc.get("canale"))
    if esistente:
        return esistente, "canale_esistente"
    etichette: List[Tuple[str, str]] = []
    for campo in _CAMPI_ETICHETTA:
        valore = str(doc.get(campo) or "").strip()
        if valore and valore.lower() not in ETICHETTE_NON_CANALE:
            etichette.append((campo, valore))
    for campo, valore in etichette:
        c = canale_da_fonte(valore)
        if c and c != CANALE_ALTRO:
            return c, f"etichetta:{campo}"
    if doc.get("email_info") or doc.get("gmail_message_id") or doc.get("email_id"):
        return CANALE_POSTA, "email"
    da_percorso = _canale_da_percorso(doc.get("source_path"))
    if da_percorso == CANALE_POSTA:
        return CANALE_POSTA, "percorso"
    occorrenze = doc.get("source_occurrences")
    if doc.get("drive_file_id") or any(
            isinstance(o, dict) and o.get("drive_file_id")
            for o in (occorrenze if isinstance(occorrenze, list) else [])):
        return CANALE_DRIVE, "drive_file_id"
    if da_percorso:
        return da_percorso, "percorso"
    if etichette:
        return CANALE_ALTRO, f"etichetta:{etichette[0][0]}"
    return None, None


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
