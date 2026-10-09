"""Conferma manuale di un bonifico: chi la scrive, chi la legge, chi la ritira.

Quando il titolare associa un bonifico a un dipendente (coda «Bonifici da
associare») il bonifico porta ``confermato_manuale=True`` con ``confermato_da``
e ``confermato_il``. Da quel momento:

* nessun motore automatico lo riassegna (``associa_bonifici_stipendi`` salta il
  movimento, il ponte HR non lo tocca);
* per gli altri dipendenti e' **consumato**: la stessa operazione, vista da un
  altro documento (la ricevuta PDF e la riga d'estratto dello stesso «MB…»),
  non offre candidati ne' si puo' associare una seconda volta.

Il segno sta sulle righe HR (coda, bonifico, esito di pagamento) e, se si
raggiungono, sul movimento d'estratto e sulla ricevuta del gestionale da cui
il bonifico nasce. Lo scrive un punto solo: qui.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Set

from app.constants.stati_associazione_bonifico import (
    CAMPO_CONFERMATO,
    CAMPO_CONFERMATO_DA,
    CAMPO_CONFERMATO_IL,
    CHIAVI_IDENTITA_BONIFICO,
)

logger = logging.getLogger(__name__)

#: Collezioni HR dove sta un bonifico confermato.
COLLEZIONI_HR = ("bonifici_da_associare", "pagamenti_esiti", "bonifici")
#: Collezioni del gestionale da cui nasce il bonifico: (collezione, campo id
#: sulla riga in coda).
ORIGINI_GESTIONALE = (
    ("estratto_conto_movimenti", "gestionale_movimento_id"),
    ("bonifici_transfers", "gestionale_transfer_id"),
)


def _adesso() -> str:
    return datetime.now(timezone.utc).isoformat()


def campi_conferma(attore: Optional[str] = None) -> Dict[str, Any]:
    """I campi da scrivere quando il titolare conferma."""
    return {CAMPO_CONFERMATO: True, CAMPO_CONFERMATO_DA: attore or "admin",
            CAMPO_CONFERMATO_IL: _adesso()}


def campi_ritiro() -> Dict[str, Any]:
    """I campi da scrivere quando la conferma si ritira (il segno si spegne)."""
    return {CAMPO_CONFERMATO: False, CAMPO_CONFERMATO_DA: None, CAMPO_CONFERMATO_IL: None}


def _norm_chiave(campo: str, valore: Any) -> Optional[str]:
    testo = str(valore or "").strip().upper()
    if not testo:
        return None
    if campo == "rif_banca":
        testo = testo.split("/")[0]  # «MB0B00923006/90679785» e «MB0B00923006» sono lo stesso
    return f"{campo}:{testo}"


def chiavi_bonifico(riga: Optional[Dict[str, Any]]) -> Set[str]:
    """Le chiavi con cui un bonifico si riconosce da una collezione all'altra."""
    from app.services.hr_pagamenti_deposito import rif_interno_banca

    riga = riga or {}
    chiavi: Set[str] = set()
    for campo in CHIAVI_IDENTITA_BONIFICO:
        chiave = _norm_chiave(campo, riga.get(campo))
        if chiave:
            chiavi.add(chiave)
    # Lo stesso MB... può essere stato archiviato come CRO dalle vecchie
    # importazioni. L'identità bancaria non dipende dal nome della colonna.
    rif = rif_interno_banca(riga.get("rif_banca"), riga.get("cro"), riga.get("rif_interno"))
    if rif:
        chiavi.add(_norm_chiave("rif_banca", rif))
    if not riga.get("rif_banca"):
        # righe nate prima del campo: il «MB…» si legge dalla causale o dal nome del file
        chiave = _norm_chiave("rif_banca", rif_interno_banca(riga.get("causale"), riga.get("pdf_filename")))
        if chiave:
            chiavi.add(chiave)
    return chiavi


async def chiavi_confermate(db_hr, escludi_id: Optional[str] = None) -> Set[str]:
    """Le chiavi di tutti i bonifici confermati a mano (insieme delle collezioni HR).

    ``escludi_id``: la riga in coda che si sta guardando, per non escludere se
    stessa."""
    chiavi: Set[str] = set()
    for nome in COLLEZIONI_HR:
        async for riga in db_hr[nome].find(
                {CAMPO_CONFERMATO: True}, {"_id": 0, "pdf_data": 0}):
            if escludi_id and riga.get("id") == escludi_id:
                continue
            chiavi |= chiavi_bonifico(riga)
    return chiavi


def e_consumato(riga: Dict[str, Any], confermate: Iterable[str]) -> bool:
    """Vero se questo bonifico e' gia' stato confermato a mano da un'altra riga."""
    return bool(chiavi_bonifico(riga) & set(confermate))


async def imposta_conferma_gestionale(db_gest, in_coda: Dict[str, Any], campi: Dict[str, Any]) -> List[str]:
    """Scrive (o spegne) il segno sul movimento d'estratto e sulla ricevuta del
    gestionale da cui nasce il bonifico. Non blocca mai l'associazione: un
    archivio non raggiungibile lascia il segno solo sul lato HR, e lo dice nel log."""
    toccati: List[str] = []
    if db_gest is None:
        return toccati
    for collezione, campo_id in ORIGINI_GESTIONALE:
        doc_id = in_coda.get(campo_id)
        if not doc_id:
            continue
        try:
            res = await db_gest[collezione].update_one({"id": doc_id}, {"$set": campi})
            if getattr(res, "matched_count", 1):
                toccati.append(f"{collezione}:{doc_id}")
        except Exception as exc:  # noqa: BLE001 - il lato HR e' gia' scritto
            logger.warning("Conferma bonifico: %s %s non aggiornato (%s: %s)",
                           collezione, doc_id, type(exc).__name__, exc)
    return toccati

