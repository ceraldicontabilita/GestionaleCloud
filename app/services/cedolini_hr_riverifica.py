"""Riverifica dei netti in HR: il PDF della busta riletto col lettore unico.

Il confronto con l'analisi del titolare (``ANALISI_COMPLETA_CEDOLINI.md``,
28/09/2026) ha trovato in ``app_cedolini`` netti che il PDF non porta: 0,45 €
per una quattordicesima da 675,00 € (Dias, 14ª 2022), 0,23 € per una da
588,00 €. Vengono dal vecchio import «dipendenti-main.zip», che leggeva
l'arrotondamento al posto della cella del netto.

Il PDF originale di ogni busta e' gia' nella riga HR (``pdf_data``): qui si
rilegge con ``cedolini_motore.leggi_pdf``, l'unico lettore dei cedolini, e si
corregge solo quando la busta ritrovata (stesso codice fiscale, anno, tipo e,
per le mensili, mese) ha il netto **verificato dalla cella**. Il valore di
prima resta in ``storico_netto``; una busta che il lettore non ritrova o non
verifica si marca e non si tocca. Ogni riga riletta porta
``netto_riverificato_il``: il giro riprende da dove si era fermato.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from app.constants.stati_netto import NETTO_VERIFICATO_DA_CEDOLINO
from app.services.hr_cedolini_deposito import TABELLA_CEDOLINI, tipo_cedolino_hr

logger = logging.getLogger(__name__)

VERSIONE = "riverifica_pdf_v2"
#: La v1 toglieva l'acconto recuperato quando la riga HR non lo annotava: le
#: sue «correzioni» si rivalutano partendo dal netto che c'era prima.
VERSIONE_V1 = "riverifica_pdf_v1"
#: Arrotondamento della busta fra netto del mese e busta + acconto.
SCARTO_ARROTONDAMENTO = Decimal("1.00")
LOTTO = 120

_SQL_DA_RILEGGERE = (
    "SELECT id, doc->>'codice_fiscale' AS cf, doc->>'anno' AS anno, doc->>'mese' AS mese, "
    "doc->>'tipo_cedolino' AS tipo, doc->>'netto' AS netto, "
    "doc->'acconti'->>'acconto_recuperato' AS acconto, "
    "doc->'storico_netto_ultimo'->>'prima' AS prima_v1, "
    "doc->'storico_netto_ultimo'->>'fonte' AS fonte_ultima FROM " + TABELLA_CEDOLINI + " "
    "WHERE doc ? 'pdf_data' AND length(doc->>'pdf_data') > 100 "
    "AND coalesce(doc->>'netto_riverificato_versione', '') <> $1 ORDER BY id LIMIT $2"
)
_SQL_PDF = "SELECT doc->>'pdf_data' FROM " + TABELLA_CEDOLINI + " WHERE id = $1"
_SQL_AGGIORNA = "UPDATE " + TABELLA_CEDOLINI + " SET doc = doc || $2::jsonb WHERE id = $1"


def _cent(valore: Any) -> Optional[Decimal]:
    if valore in (None, ""):
        return None
    try:
        return Decimal(str(valore)).quantize(Decimal("0.01"))
    except InvalidOperation:  # un netto illeggibile resta nullo, non zero
        return None


def _intero(valore: Any) -> Optional[int]:
    try:
        return int(str(valore).strip())
    except (TypeError, ValueError):
        return None


def busta_della_riga(riga: Dict[str, Any], buste: List[Dict[str, Any]]) -> Dict[str, Any]:
    """La busta del PDF che corrisponde alla riga HR, o il motivo per cui non c'e'."""
    cf = str(riga.get("cf") or "").upper()
    anno = _intero(riga.get("anno"))
    tipo = tipo_cedolino_hr(riga.get("tipo"))
    mese = _intero(riga.get("mese"))
    candidate = [
        b for b in buste
        if str(b.get("codice_fiscale") or "").upper() == cf
        and _intero(b.get("anno")) == anno
        and tipo_cedolino_hr(b.get("tipo_cedolino")) == tipo
        # 13ª e 14ª: il vecchio import le metteva al mese 13/14, il lettore a
        # dicembre/luglio; basta il tipo. Le mensili vogliono il mese.
        and (tipo in ("tredicesima", "quattordicesima") or _intero(b.get("mese")) == mese)
    ]
    if not candidate:
        return {"esito": "non_ritrovata"}
    if len(candidate) > 1 and len({_cent(b.get("netto")) for b in candidate}) > 1:
        return {"esito": "ambigua", "netti": [str(_cent(b.get("netto"))) for b in candidate]}
    busta = candidate[0]
    if busta.get("stato_netto") != NETTO_VERIFICATO_DA_CEDOLINO or _cent(busta.get("netto")) is None:
        return {"esito": "netto_non_verificato", "stato_netto": busta.get("stato_netto")}
    return {"esito": "ritrovata", "netto": _cent(busta.get("netto")),
            # competenze − trattenute: con un acconto recuperato e' busta + acconto
            "netto_calcolato": _cent(busta.get("netto_calcolato"))}


def correzione(riga: Dict[str, Any], esito: Dict[str, Any], now: str) -> Dict[str, Any]:
    """Il pezzo di documento da fondere nella riga HR (sempre col marcatore del giro).

    Decisione del titolare (28/09/2026): in HR il netto e' quello della busta
    piu' l'acconto gia' recuperato, il totale del mese (la cella dice 598,00,
    la riga HR 1.597,06 con 1.000,00 di acconto). L'acconto si prende dalla
    riga HR o, se la riga non lo annota, dal PDF stesso: competenze meno
    trattenute supera la cella del netto. Lo scarto fino a 1,00 e'
    l'arrotondamento della busta.
    """
    patch: Dict[str, Any] = {
        "netto_riverificato_il": now, "netto_riverificato_versione": VERSIONE,
        "netto_riverifica_esito": esito["esito"],
    }
    if esito["esito"] != "ritrovata":
        return patch
    attuale, cella = _cent(riga.get("netto")), esito["netto"]
    # Una riga «corretta» dalla v1 si giudica dal netto che aveva prima.
    corretta_da_v1 = riga.get("fonte_ultima") == VERSIONE_V1
    prima = _cent(riga.get("prima_v1")) if corretta_da_v1 else attuale

    con_acconto = []
    acconto_hr = _cent(riga.get("acconto")) or Decimal("0")
    if acconto_hr > 0:
        con_acconto.append(cella + acconto_hr)
    calcolato = esito.get("netto_calcolato")
    if calcolato is not None and calcolato - cella > SCARTO_ARROTONDAMENTO:
        con_acconto.append(calcolato)
    if con_acconto:
        patch["netto_busta"] = float(cella)

    if prima is not None and any(abs(prima - v) <= SCARTO_ARROTONDAMENTO for v in con_acconto):
        giusto, patch["netto_riverifica_esito"] = prima, "confermato_con_acconto"
    elif prima == cella:
        giusto, patch["netto_riverifica_esito"] = prima, "confermato"
    else:
        giusto = con_acconto[0] if acconto_hr > 0 else cella
        patch["netto_riverifica_esito"] = "corretto"
    if giusto == attuale:
        return patch
    patch.update({
        "netto": float(giusto), "stato_netto": NETTO_VERIFICATO_DA_CEDOLINO,
        "netto_fonte": VERSIONE,
        "storico_netto_ultimo": {"prima": float(attuale) if attuale is not None else None,
                                 "dopo": float(giusto), "at": now, "fonte": VERSIONE},
    })
    if patch["netto_riverifica_esito"] != "corretto":
        patch["netto_riverifica_esito"] = "ripristinato"
    return patch


async def riverifica_lotto(con, *, dry_run: bool = False, lotto: int = LOTTO) -> Dict[str, Any]:
    """Rilegge al massimo ``lotto`` buste non ancora riverificate."""
    from app.services.cedolini_motore import leggi_pdf

    righe = [dict(r) for r in await con.fetch(_SQL_DA_RILEGGERE, VERSIONE, lotto)]
    conteggi: Dict[str, int] = {}
    correzioni: List[Dict[str, Any]] = []
    for riga in righe:
        now = datetime.now(timezone.utc).isoformat()
        try:
            pdf = base64.b64decode(await con.fetchval(_SQL_PDF, riga["id"]) or "")
            letto = await asyncio.to_thread(leggi_pdf, pdf)
            esito = busta_della_riga(riga, letto.get("buste") or [])
        except Exception as exc:  # noqa: BLE001 - un PDF rotto non ferma il lotto
            logger.warning("Riverifica netto %s: PDF non letto: %s: %s", riga["id"], type(exc).__name__, exc)
            esito = {"esito": "pdf_illeggibile"}
        patch = correzione(riga, esito, now)
        conteggi[patch["netto_riverifica_esito"]] = conteggi.get(patch["netto_riverifica_esito"], 0) + 1
        if "storico_netto_ultimo" in patch:
            correzioni.append({"id": riga["id"], "cf": riga["cf"], "anno": riga["anno"], "mese": riga["mese"],
                               "tipo": riga["tipo"], **patch["storico_netto_ultimo"]})
        if dry_run:
            continue
        if "storico_netto_ultimo" in patch:
            # Lo storico cresce, non si riscrive: la voce si accoda a quelle che ci sono.
            patch["storico_netto"] = (await _storico(con, riga["id"])) + [patch["storico_netto_ultimo"]]
        await con.execute(_SQL_AGGIORNA, riga["id"], json.dumps(patch))
    return {"lette": len(righe), "conteggi": conteggi, "correzioni": correzioni, "dry_run": dry_run}


async def _storico(con, riga_id: str) -> List[Dict[str, Any]]:
    valore = await con.fetchval(
        "SELECT doc->'storico_netto' FROM " + TABELLA_CEDOLINI + " WHERE id = $1", riga_id)
    if isinstance(valore, str):
        valore = json.loads(valore)
    return list(valore or [])
