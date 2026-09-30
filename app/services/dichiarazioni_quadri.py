"""Lettura per posizione dei quadri delle dichiarazioni fiscali.

Le dichiarazioni annuali che il commercialista trasmette (IVA, Redditi SC,
IRAP) e l'esito ISA arrivano come PDF stampati dal software dell'Agenzia. Il
loro livello testo **non e' affidabile in ordine**: le etichette dei righi
(`VL33`, `RN17`, `IR26`) stanno in un blocco, i segnaposto `,00` di ogni
casella in un altro, e i valori compilati vengono accodati **in fondo alla
pagina** senza nessuna etichetta (`... 24.178 19.342 4.836 ... 935 935`).
Leggere in sequenza attribuisce un numero al rigo sbagliato.

Si legge quindi **per posizione**, come `lipe_parser.py`: ogni rigo ha la sua
etichetta sul margine sinistro del modulo (x ~= 107) e ogni casella un
segnaposto `,00`; il valore di una casella e' il numero il cui bordo destro
tocca il suo `,00` (`24.178` finisce a x = 548, il `,00` inizia a 549). Su un
rigo a piu' colonne (RN1: «Legge 112/2016», «Liberalita'», «Reddito») la
casella del valore e' l'**ultima a destra**.

Regole del modulo:

- una casella vuota resta `None` con `motivo = "casella_vuota"`, mai zero: il
  modello non stampa gli zeri, e uno 0 inventato sembrerebbe un dato letto;
- un rigo senza etichetta nel documento e' `rigo_non_trovato`;
- lo stesso rigo trovato con **due valori diversi** (due moduli, due pagine)
  non sceglie: finisce in `campi_da_verificare` con i candidati;
- gli importi sono `Decimal` (in uscita stringhe con due decimali), mai float.

Il tipo di documento si riconosce dal **contenuto** (quadro VX, quadro RN,
quadro IR, «Esito del ricalcolo» ISA), non dalla classificazione
dell'archivio: gli esiti ISA sono registrati come `REDDITI_SC`.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional

from app.db_collections import (
    COLL_DOCUMENTS_INBOX,
    COLL_FISCAL_DOCUMENTS,
    COLL_FISCAL_EVIDENCE,
    COLL_FISCAL_PAGES,
)

logger = logging.getLogger(__name__)

__all__ = [
    "PARSER_VERSION",
    "TIPI_CON_QUADRI",
    "CAMPI_PER_TIPO",
    "pagina_con_quadro",
    "riconosci_tipo",
    "valore_rigo",
    "estrai_quadri_pagine",
    "estrai_quadri_documento",
    "avvia_estrazione_archivio",
    "stato_estrazione_archivio",
]

PARSER_VERSION = "dichiarazioni-quadri-v1"

#: Tipi dell'archivio (`fiscal_documents.document_type`) che portano un quadro
#: leggibile. Gli esiti ISA stanno sotto `REDDITI_SC`: e' il contenuto a dirlo.
TIPI_CON_QUADRI = frozenset({"DICHIARAZIONE_IVA", "REDDITI_SC", "DICHIARAZIONE_IRAP", "ISA_ESITO"})

#: rigo del modulo -> nome del campo, per tipo letto.
CAMPI_PER_TIPO: Dict[str, Dict[str, str]] = {
    "DICHIARAZIONE_IVA": {
        "VL32": "vl32_iva_debito",
        "VL33": "vl33_iva_credito",
        "VX1": "vx1_da_versare",
        "VX2": "vx2_a_credito",
    },
    "REDDITI_SC": {
        "RN1": "rn1_reddito",
        "RN2": "rn2_perdita",
        "RN17": "rn17_ires_dovuta_differenza",
    },
    "DICHIARAZIONE_IRAP": {
        "IR26": "ir26_importo_a_debito",
        "IR27": "ir27_importo_a_credito",
    },
}

_ETICHETTE_QUADRO = re.compile(r"\b(VL32|VL33|VX1|VX2|RN1|RN2|RN17|IR26|IR27)\b")
_RE_ISA = re.compile(r"Esito del ricalcolo|INDICE\s+SINTETICO\s+DI\s+AFFIDABILIT", re.I)
#: Il frontespizio dell'esito ISA («DATI RICALCOLATI», motore «Il tuo Isa»)
#: porta codice ISA e protocollo: le sue coordinate vanno conservate.
_RE_ISA_FRONTESPIZIO = re.compile(r"DATI RICALCOLATI|Il tuo Isa", re.I)
_RE_IDENTIFICATIVO = re.compile(
    r"Identificativo dichiarazione:\s*(\d{11})\s*-\s*(\d{7})(?:\s+del\s+(\d{1,2}/\d{1,2}/\d{4}))?", re.I
)
_RE_ANNO_IMPOSTA = re.compile(r"PERIODO\s+D[’'`]\s*IMPOSTA\s+((?:19|20)\d{2})", re.I)
_RE_MODELLO_REDDITI = re.compile(r"REDDITI\s*SC\s*((?:19|20)\d{2})", re.I)
_RE_PROTOCOLLO = re.compile(r"Protocollo\s*\n?\s*(\d{20,26})")
_RE_CODICE_ISA = re.compile(r"^[A-Z]{2}\d{2}[A-Z]$")
_RE_SEGNAPOSTO = re.compile(r"^,\d{2}$|^00$")  # l'OCR perde la virgola del segnaposto
_RE_INTERO = re.compile(r"^(?:\d{1,3}(?:\.\d{3})+|\d+)$")
_RE_IMPORTO_CON_DECIMALI = re.compile(r"^(\d{1,3}(?:\.\d{3})*)[.,](\d{2})$")  # OCR: «1.462.00»
_RE_PUNTEGGIO = re.compile(r"^\d{1,2},\d{2}$")

#: L'etichetta del rigo sta sul margine sinistro del modulo.
_X_MAX_ETICHETTA = 200.0
#: Distanza verticale massima fra etichetta e segnaposto della sua casella.
_TOLLERANZA_RIGA = 10.0
#: Il numero tocca il suo `,00`: bordo destro a pochi punti dal segnaposto.
_TOLLERANZA_ACCOSTO = 5.0
_TOLLERANZA_Y_VALORE = 6.0


def _f(parola: Dict[str, Any], chiave: str) -> float:
    try:
        return float(parola.get(chiave) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _testo(parola: Dict[str, Any]) -> str:
    return str(parola.get("text") or "").strip()


def pagina_con_quadro(testo: str) -> bool:
    """La pagina porta un rigo da leggere (VL/VX/RN/IR) o l'esito ISA.

    Serve all'ingestione per decidere se conservare le coordinate: senza
    `layout_words` questi righi non si leggono.
    """
    t = str(testo or "")
    return bool(_ETICHETTE_QUADRO.search(t) or _RE_ISA.search(t) or _RE_ISA_FRONTESPIZIO.search(t))


def riconosci_tipo(pagine: Iterable[Dict[str, Any]]) -> Optional[str]:
    """Il tipo di dichiarazione dal contenuto delle pagine."""
    testo = "\n".join(str(p.get("text") or "") for p in pagine)
    if _RE_ISA.search(testo) and re.search(r"\bISA\b|Isa\b", testo):
        return "ISA_ESITO"
    # L'OCR salda le parole («QUADROVX», «MODELLOIVA2024»): spazio facoltativo.
    if re.search(r"QUADRO\s*VX(?![A-Z0-9])|MODELLO\s*IVA\s*20\d{2}", testo, re.I):
        return "DICHIARAZIONE_IVA"
    if re.search(r"QUADRO\s*RN(?![A-Z0-9])", testo, re.I):
        return "REDDITI_SC"
    if re.search(r"QUADRO\s*IR(?![A-Z0-9])", testo, re.I):
        return "DICHIARAZIONE_IRAP"
    return None


def _decimal(intero: str, decimali: str = "00") -> Optional[Decimal]:
    cifre = intero.replace(".", "")
    if not cifre.isdigit() or not decimali.isdigit():
        return None
    try:
        return Decimal(f"{cifre}.{decimali}")
    except InvalidOperation:
        return None


def _formatta(valore: Optional[Decimal]) -> Optional[str]:
    return None if valore is None else f"{valore.quantize(Decimal('0.01'))}"


def valore_rigo(parole: List[Dict[str, Any]], etichetta: str) -> Dict[str, Any]:
    """Il valore della casella di un rigo, letto per posizione su una pagina.

    Ritorna `{"valore": Decimal|None, "motivo": str|None, "candidati": [...]}`.
    Con piu' etichette uguali sul margine (due moduli sulla stessa pagina) o
    piu' numeri accostati alla stessa casella, i candidati diversi vanno in
    `candidati` e `valore` resta `None` con `motivo = "ambiguo"`.
    """
    etichette = [
        w for w in parole
        if (_testo(w) == etichetta or _testo(w).startswith(etichetta + " "))
        and _f(w, "x0") <= _X_MAX_ETICHETTA
    ]
    if not etichette:
        return {"valore": None, "motivo": "rigo_non_trovato", "candidati": []}

    letture: List[Optional[Decimal]] = []
    motivi: List[str] = []
    for lab in etichette:
        y_lab = _f(lab, "y0")
        riga = [w for w in parole if w is not lab and abs(_f(w, "y0") - y_lab) <= _TOLLERANZA_RIGA]
        segnaposti = [w for w in riga if _RE_SEGNAPOSTO.match(_testo(w))]
        if segnaposti:
            # La casella del rigo e' quella col segnaposto piu' vicino in
            # verticale; a parita' (righi a piu' colonne) l'ultima a destra.
            segnaposti.sort(key=lambda w: (round(abs(_f(w, "y0") - y_lab)), -_f(w, "x0")))
            cella = segnaposti[0]
            accostati = [
                w for w in riga
                if _RE_INTERO.match(_testo(w))
                and abs(_f(w, "x1") - _f(cella, "x0")) <= _TOLLERANZA_ACCOSTO
                and abs(_f(w, "y0") - _f(cella, "y0")) <= _TOLLERANZA_Y_VALORE
            ]
            valori = {_decimal(_testo(w), _testo(cella).lstrip(",")) for w in accostati}
            if not valori:
                # OCR: il valore porta i decimali attaccati («1.462,00») e
                # copre il segnaposto; vale se e' uno solo nella casella.
                for w in riga:
                    m = _RE_IMPORTO_CON_DECIMALI.match(_testo(w))
                    if m and _f(w, "x0") > _X_MAX_ETICHETTA and abs(_f(w, "x1") - _f(cella, "x1")) <= 8 \
                            and abs(_f(w, "y0") - _f(cella, "y0")) <= _TOLLERANZA_Y_VALORE:
                        valori.add(_decimal(m.group(1), m.group(2)))
            valori = sorted(valori - {None})
            if not valori:
                letture.append(None)
                motivi.append("casella_vuota")
            elif len(valori) == 1:
                letture.append(valori[0])
            else:
                return {"valore": None, "motivo": "ambiguo",
                        "candidati": [_formatta(v) for v in valori]}
            continue
        # Senza segnaposto (testo OCR: «1.462,00» in un pezzo solo) vale
        # l'importo con i decimali scritti, il piu' a destra del rigo.
        con_decimali = [
            w for w in riga
            if _RE_IMPORTO_CON_DECIMALI.match(_testo(w)) and _f(w, "x0") > _X_MAX_ETICHETTA
        ]
        if not con_decimali:
            letture.append(None)
            motivi.append("casella_vuota")
            continue
        con_decimali.sort(key=lambda w: -_f(w, "x1"))
        m = _RE_IMPORTO_CON_DECIMALI.match(_testo(con_decimali[0]))
        letture.append(_decimal(m.group(1), m.group(2)))

    distinti = sorted({v for v in letture if v is not None})
    if len(distinti) > 1:
        return {"valore": None, "motivo": "ambiguo", "candidati": [_formatta(v) for v in distinti]}
    if distinti:
        return {"valore": distinti[0], "motivo": None, "candidati": []}
    return {"valore": None, "motivo": motivi[0] if motivi else "casella_vuota", "candidati": []}


def _campo(valore: Optional[Decimal], motivo: Optional[str], pagina: Optional[int],
           rigo: Optional[str] = None, candidati: Optional[List[str]] = None) -> Dict[str, Any]:
    campo: Dict[str, Any] = {"valore": _formatta(valore), "motivo": motivo, "pagina": pagina}
    if rigo:
        campo["rigo"] = rigo
    if candidati:
        campo["candidati"] = candidati
    return campo


def _leggi_righi(pagine: List[Dict[str, Any]], righi: Dict[str, str]) -> Dict[str, Dict[str, Any]]:
    campi: Dict[str, Dict[str, Any]] = {}
    for rigo, nome in righi.items():
        # L'etichetta puo' stare nel testo o solo fra le parole con coordinate
        # (l'OCR a volte la salda alla descrizione del rigo).
        pagine_col_rigo = [
            p for p in pagine
            if re.search(rf"\b{rigo}\b", str(p.get("text") or ""))
            or any(_testo(w) == rigo or _testo(w).startswith(rigo + " ") for w in p.get("layout_words") or [])
        ]
        if not pagine_col_rigo:
            campi[nome] = _campo(None, "rigo_non_trovato", None, rigo)
            continue
        letture: List[tuple] = []
        vuote: List[int] = []
        senza_coordinate: List[int] = []
        ambigui: List[str] = []
        for p in pagine_col_rigo:
            parole = p.get("layout_words") or []
            numero = int(p.get("page_number") or 0)
            if not parole:
                senza_coordinate.append(numero)
                continue
            esito = valore_rigo(parole, rigo)
            if esito["motivo"] == "ambiguo":
                ambigui.extend(esito["candidati"])
            elif esito["valore"] is not None:
                letture.append((esito["valore"], numero))
            elif esito["motivo"] == "casella_vuota":
                vuote.append(numero)
        distinti = sorted({v for v, _ in letture})
        candidati = sorted({_formatta(v) for v in distinti} | set(ambigui))
        if len(candidati) > 1 or (ambigui and candidati):
            campi[nome] = _campo(None, "ambiguo", None, rigo, candidati)
        elif distinti:
            campi[nome] = _campo(distinti[0], None, next(n for v, n in letture if v == distinti[0]), rigo)
        elif vuote:
            campi[nome] = _campo(None, "casella_vuota", vuote[0], rigo)
        elif senza_coordinate:
            campi[nome] = _campo(None, "pagina_senza_coordinate", senza_coordinate[0], rigo)
        else:
            campi[nome] = _campo(None, "rigo_non_trovato", None, rigo)
    return campi


def _isa(pagine: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Punteggio, codice ISA e protocollo dell'esito del ricalcolo."""
    campi: Dict[str, Dict[str, Any]] = {}
    testo = "\n".join(str(p.get("text") or "") for p in pagine)

    m = _RE_PROTOCOLLO.search(testo)
    campi["protocollo"] = (
        {"valore": m.group(1), "motivo": None, "pagina": None} if m
        else {"valore": None, "motivo": "protocollo_non_trovato", "pagina": None}
    )

    codici: List[tuple] = []
    for p in pagine:
        parole = p.get("layout_words") or []
        for lab in (w for w in parole if _testo(w) == "Modello"):
            destra = [
                w for w in parole
                if _f(w, "x0") > _f(lab, "x1") and abs(_f(w, "y0") - _f(lab, "y0")) <= 4
                and _RE_CODICE_ISA.match(_testo(w))
            ]
            for w in destra:
                codici.append((_testo(w), int(p.get("page_number") or 0)))
    distinti = sorted({c for c, _ in codici})
    if len(distinti) == 1:
        campi["codice_isa"] = {"valore": distinti[0], "motivo": None, "pagina": codici[0][1]}
    elif distinti:
        campi["codice_isa"] = {"valore": None, "motivo": "ambiguo", "pagina": None, "candidati": distinti}
    else:
        campi["codice_isa"] = {"valore": None, "motivo": "codice_non_trovato", "pagina": None}

    punteggi: List[tuple] = []
    for p in pagine:
        if not re.search(r"Esito del ricalcolo", str(p.get("text") or "")):
            continue
        parole = p.get("layout_words") or []
        intestazioni = [w for w in parole if _testo(w) == "Punteggio" and _f(w, "x0") > 450]
        if not intestazioni:
            continue
        testata = min(intestazioni, key=lambda w: _f(w, "y0"))
        sotto = [
            w for w in parole
            if _RE_PUNTEGGIO.match(_testo(w)) and _f(w, "y0") > _f(testata, "y0")
            and _f(w, "x1") > _f(testata, "x0") and _f(w, "x0") < _f(testata, "x1") + 20
        ]
        if sotto:
            primo = min(sotto, key=lambda w: _f(w, "y0"))
            punteggi.append((Decimal(_testo(primo).replace(",", ".")), int(p.get("page_number") or 0)))
    distinti_p = sorted({v for v, _ in punteggi})
    if len(distinti_p) == 1:
        campi["isa_punteggio"] = _campo(distinti_p[0], None, punteggi[0][1])
    elif distinti_p:
        campi["isa_punteggio"] = _campo(None, "ambiguo", None, None, [_formatta(v) for v in distinti_p])
    else:
        motivo = "punteggio_non_trovato"
        if any(re.search(r"Esito del ricalcolo", str(p.get("text") or ""))
               and not p.get("layout_words") for p in pagine):
            motivo = "pagina_senza_coordinate"
        campi["isa_punteggio"] = _campo(None, motivo, None)
    return campi


def estrai_quadri_pagine(pagine: Iterable[Dict[str, Any]], document_type: Optional[str] = None) -> Dict[str, Any]:
    """Legge i campi del quadro dalle pagine di un documento (funzione pura).

    `pagine`: dizionari con `page_number`, `text`, `layout_words`. Il tipo si
    riconosce dal contenuto; `document_type` e' solo il ripiego quando il
    contenuto non dice niente.
    """
    elenco = sorted((dict(p) for p in pagine), key=lambda p: int(p.get("page_number") or 0))
    testo = "\n".join(str(p.get("text") or "") for p in elenco)
    tipo = riconosci_tipo(elenco) or (document_type if document_type in TIPI_CON_QUADRI else None)

    esito: Dict[str, Any] = {
        "tipo_letto": tipo,
        "parser_version": PARSER_VERSION,
        "identificativo": None,
        "data_presentazione": None,
        "anno_imposta": None,
        "anno_imposta_fonte": None,
        "campi": {},
        "campi_da_verificare": [],
    }
    m = _RE_IDENTIFICATIVO.search(testo)
    if m:
        esito["identificativo"] = f"{m.group(1)} - {m.group(2)}"
        esito["data_presentazione"] = m.group(3)
    m = _RE_ANNO_IMPOSTA.search(testo)
    if m:
        esito["anno_imposta"] = int(m.group(1))
        esito["anno_imposta_fonte"] = "periodo_imposta_stampato"

    if tipo is None:
        esito["motivo"] = "tipo_non_riconosciuto"
        return esito
    if tipo == "ISA_ESITO":
        esito["campi"] = _isa(elenco)
        m = _RE_MODELLO_REDDITI.search(testo)
        if m:
            esito["modello_dichiarazione"] = f"REDDITI SC{m.group(1)}"
            if esito["anno_imposta"] is None:
                # Il modello Redditi SC dell'anno N dichiara il periodo N-1.
                esito["anno_imposta"] = int(m.group(1)) - 1
                esito["anno_imposta_fonte"] = "modello_redditi_anno_meno_uno"
    else:
        esito["campi"] = _leggi_righi(elenco, CAMPI_PER_TIPO[tipo])

    esito["campi_da_verificare"] = sorted(
        nome for nome, campo in esito["campi"].items() if campo.get("motivo") == "ambiguo"
    )
    return esito


# ── Integrazione con l'archivio ────────────────────────────────────────────

_CHIAVE_STATO = "dichiarazioni_quadri_estrazione"
_job_lock = asyncio.Lock()
_job_task: Optional[asyncio.Task] = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _carica_originale(db, documento: Dict[str, Any], company_id: str) -> Optional[bytes]:
    """Il PDF originale: dal deposito Documenti, altrimenti da Drive per id."""
    inbox_id = (documento.get("metadata") or {}).get("documents_inbox_id")
    query = ({"id": inbox_id, "company_id": company_id} if inbox_id
             else {"company_id": company_id, "fiscal_document_id": documento.get("id")})
    riga = await db[COLL_DOCUMENTS_INBOX].find_one(query, {"_id": 0, "pdf_data": 1, "drive_file_id": 1})
    if riga and riga.get("pdf_data"):
        return base64.b64decode(riga["pdf_data"])
    meta = documento.get("source_metadata") or {}
    drive_ids = [meta.get("drive_file_id"), (riga or {}).get("drive_file_id")]
    drive_ids += [occ.get("drive_file_id") for occ in documento.get("source_occurrences") or []]
    for file_id in (i for i in drive_ids if i):
        from app.services.drive_download import scarica_originale

        contenuto = await scarica_originale(str(file_id))
        if contenuto:
            return contenuto
    return None


async def _pagine_con_coordinate(db, documento: Dict[str, Any], pagine: List[Dict[str, Any]],
                                 company_id: str, *, dry_run: bool) -> tuple:
    """Le pagine col quadro devono avere le coordinate; se l'archivio non le
    ha (ingestioni precedenti le tenevano solo per la LIPE) si rileggono
    dall'originale e, fuori dalla simulazione, si salvano."""
    mancanti = [p for p in pagine if pagina_con_quadro(p.get("text")) and not p.get("layout_words")]
    if not mancanti:
        return pagine, False
    contenuto = await _carica_originale(db, documento, company_id)
    if not contenuto:
        return pagine, False
    from app.services.fiscal_document_ingestion import extract_pdf_pages

    rilette = {p["page_number"]: p for p in await asyncio.to_thread(extract_pdf_pages, contenuto)}
    aggiornate: List[Dict[str, Any]] = []
    for p in pagine:
        nuova = rilette.get(int(p.get("page_number") or 0))
        if nuova and nuova.get("layout_words"):
            p = {**p, "layout_words": nuova["layout_words"], "text": nuova["text"],
                 "text_source": nuova["text_source"]}
            if not dry_run:
                await db[COLL_FISCAL_PAGES].update_one(
                    {"company_id": company_id, "version_id": p.get("version_id"),
                     "page_number": p["page_number"]},
                    {"$set": {"layout_words": p["layout_words"], "text": p["text"],
                              "text_source": p["text_source"], "updated_at": _now()}},
                )
        aggiornate.append(p)
    return aggiornate, True


async def estrai_quadri_documento(db, document_id: str, *, company_id: Optional[str] = None,
                                  dry_run: bool = False) -> Dict[str, Any]:
    """Legge i quadri di un documento dell'archivio e ne deposita le prove.

    Scrive una riga `fiscal_evidence` per ogni valore letto (id stabile:
    rilanciare non duplica) e il riepilogo `quadri` sulla riga di
    `fiscal_documents`. Con `dry_run` legge soltanto.
    """
    from app.config import settings
    from app.services.fiscal_domain import build_evidence

    company_id = company_id or settings.FISCAL_COMPANY_ID
    documento = await db[COLL_FISCAL_DOCUMENTS].find_one(
        {"company_id": company_id, "id": document_id}, {"_id": 0}
    )
    if not documento:
        return {"document_id": document_id, "esito": "documento_non_trovato"}
    version_id = documento.get("current_version_id")
    filtro = {"company_id": company_id, "document_id": document_id}
    if version_id:
        filtro["version_id"] = version_id
    pagine = await db[COLL_FISCAL_PAGES].find(filtro, {"_id": 0}).to_list(2000)
    if not pagine:
        return {"document_id": document_id, "esito": "pagine_assenti"}
    pagine, rilette = await _pagine_con_coordinate(db, documento, pagine, company_id, dry_run=dry_run)

    letto = estrai_quadri_pagine(pagine, documento.get("document_type"))
    quadri = {**letto, "estratto_at": _now(), "coordinate_rilette": rilette}
    prove = []
    for nome, campo in letto["campi"].items():
        if campo.get("valore") is None:
            continue
        prova = build_evidence(
            document_id=document_id, version_id=str(version_id or ""),
            page_number=int(campo.get("pagina") or 1), field_name=nome,
            raw_value=campo["valore"], normalized_value=campo["valore"],
            parser_version=PARSER_VERSION, confidence=1.0,
            reason=f"lettura_per_posizione:{campo.get('rigo') or nome}",
        )
        prova["company_id"] = company_id
        prove.append(prova)
    if not dry_run:
        for prova in prove:
            await db[COLL_FISCAL_EVIDENCE].update_one(
                {"company_id": company_id, "id": prova["id"]},
                {"$setOnInsert": prova}, upsert=True,
            )
        await db[COLL_FISCAL_DOCUMENTS].update_one(
            {"company_id": company_id, "id": document_id},
            {"$set": {"quadri": quadri, "updated_at": _now()}},
        )
    return {
        "document_id": document_id,
        "esito": "letto" if letto.get("tipo_letto") else "tipo_non_riconosciuto",
        "dry_run": dry_run,
        "quadri": quadri,
        "prove": len(prove),
    }


async def estrai_quadri_archivio(db, *, dry_run: bool = True, company_id: Optional[str] = None) -> Dict[str, Any]:
    """Ripassa tutte le dichiarazioni dell'archivio (un prefetch, poi per id)."""
    from app.config import settings

    company_id = company_id or settings.FISCAL_COMPANY_ID
    documenti = await db[COLL_FISCAL_DOCUMENTS].find(
        {"company_id": company_id, "document_type": {"$in": sorted(TIPI_CON_QUADRI)}},
        {"_id": 0, "id": 1, "filename": 1, "document_type": 1},
    ).to_list(10000)
    riepilogo: Dict[str, Any] = {
        "dry_run": dry_run, "documenti": len(documenti), "letti": 0,
        "tipo_non_riconosciuto": 0, "pagine_assenti": 0, "errori": 0,
        "campi_da_verificare": [], "senza_coordinate": [], "motivi_errore": [],
    }
    for doc in documenti:
        try:
            esito = await estrai_quadri_documento(db, doc["id"], company_id=company_id, dry_run=dry_run)
        except Exception as exc:  # noqa: BLE001 - il giro continua, l'errore resta scritto
            riepilogo["errori"] += 1
            riepilogo["motivi_errore"].append(f"{doc.get('filename')}: {type(exc).__name__}: {exc}")
            logger.warning("Quadri non letti su %s: %s: %s", doc.get("filename"), type(exc).__name__, exc)
            continue
        chiave = esito["esito"] if esito["esito"] in riepilogo else None
        if esito["esito"] == "letto":
            riepilogo["letti"] += 1
        elif chiave:
            riepilogo[chiave] += 1
        quadri = esito.get("quadri") or {}
        if quadri.get("campi_da_verificare"):
            riepilogo["campi_da_verificare"].append(
                {"filename": doc.get("filename"), "campi": quadri["campi_da_verificare"]}
            )
        if any(c.get("motivo") == "pagina_senza_coordinate" for c in (quadri.get("campi") or {}).values()):
            riepilogo["senza_coordinate"].append(doc.get("filename"))
    return riepilogo


async def _salva_stato(db, **campi) -> None:
    await db["sistema_stato"].update_one(
        {"chiave": _CHIAVE_STATO},
        {"$set": {**campi, "updated_at": _now()}}, upsert=True,
    )


async def _esegui(db, dry_run: bool) -> None:
    async with _job_lock:
        iniziato = _now()
        await _salva_stato(db, stato="in_corso", dry_run=dry_run, iniziato_at=iniziato,
                           terminato_at=None, risultato=None, errore=None)
        try:
            risultato = await estrai_quadri_archivio(db, dry_run=dry_run)
            await _salva_stato(db, stato="completato", dry_run=dry_run, iniziato_at=iniziato,
                               terminato_at=_now(), risultato=risultato, errore=None)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Estrazione quadri dichiarazioni fallita")
            await _salva_stato(db, stato="errore", dry_run=dry_run, iniziato_at=iniziato,
                               terminato_at=_now(), risultato=None,
                               errore=f"{type(exc).__name__}: {exc}")


async def stato_estrazione_archivio(db) -> Dict[str, Any]:
    stato = await db["sistema_stato"].find_one({"chiave": _CHIAVE_STATO}, {"_id": 0})
    if not stato:
        return {"stato": "mai_avviato"}
    stato.pop("chiave", None)
    return stato


async def avvia_estrazione_archivio(db, *, dry_run: bool = True) -> Dict[str, Any]:
    """Avvia il ripasso in sottofondo (regola 4: oltre i 5 minuti il proxy
    Render taglia la richiesta); l'esito si legge da `stato_estrazione_archivio`."""
    global _job_task
    if _job_lock.locked() or (_job_task is not None and not _job_task.done()):
        return {"avviato": False, **await stato_estrazione_archivio(db)}
    _job_task = asyncio.create_task(_esegui(db, dry_run))
    return {"avviato": True, "stato": "avvio", "dry_run": dry_run}
