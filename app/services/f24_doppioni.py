"""Doppioni F24: lo stesso modello arrivato da due PDF diversi.

``chiave_f24`` (``f24_canonico``) mette nella chiave l'impronta del PDF, quindi
due file dello stesso F24 («… F24.pdf» e «… F24 (2).pdf», o la «stampa di
controllo») diventavano due modelli: uno pagato e uno «da pagare», e il saldo
aperto raddoppiava. L'identita' di un F24 e' il suo **contenuto fiscale**:
contribuente, data di versamento, saldo al centesimo e le righe tributo
(codice, periodo, debito, credito) una per una. Stesso contenuto = stesso F24,
qualunque sia il file.

Un doppione non si cancella: va in quarantena (``status = "eliminato"`` con
``motivo_quarantena``, ``doppione_di`` e lo stato che aveva prima), resta
consultabile ed e' reversibile.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

COLL = "f24_unificato"
MOTIVO_DOPPIONE = "doppione"
STATO_QUARANTENA = "eliminato"


def _cents(valore: Any) -> Optional[int]:
    from app.services.f24_controllo_incrociato import centesimi

    return centesimi(valore)


def identita_f24(doc: Dict[str, Any]) -> Optional[str]:
    """Contenuto fiscale del modello; ``None`` se non basta a riconoscerlo."""
    from app.services import f24_controllo_incrociato as registro

    righe = registro.righe_modello(doc)
    saldo = registro.saldo_modello_cents(doc)
    if saldo is None:
        dg_saldo = (doc.get("dati_generali") or {}).get("saldo_delega_cents")
        saldo = dg_saldo if isinstance(dg_saldo, int) else _cents((doc.get("dati_generali") or {}).get("saldo_delega"))
    if not righe or saldo is None:
        return None
    dg = doc.get("dati_generali") or {}
    contribuente = str(doc.get("codice_fiscale") or dg.get("codice_fiscale") or "").strip().upper()
    firma = sorted(
        (r["codice"], r["periodo_riferimento"] or "", r["importo_debito_cents"], r["importo_credito_cents"])
        for r in righe
    )
    return "|".join([
        contribuente, registro.data_versamento_modello(doc) or "", str(saldo),
        ";".join(":".join(str(x) for x in riga) for riga in firma),
    ])


def _priorita(doc: Dict[str, Any]) -> Tuple[int, int, str]:
    """Quale copia resta: quella con la banca, poi con la quietanza, poi la prima arrivata."""
    from app.services.f24_payment_evidence import stato_evidenza_pagamento

    evidenza = stato_evidenza_pagamento(doc)
    return (
        0 if evidenza["verificato_banca"] or doc.get("movimento_bancario_id") else 1,
        0 if evidenza["quietanza_presente"] else 1,
        str(doc.get("created_at") or ""),
    )


def attivo(doc: Dict[str, Any]) -> bool:
    return doc.get("status") != STATO_QUARANTENA and doc.get("entity_status") != "deleted"


def trova_doppioni(modelli: Iterable[Dict[str, Any]]) -> List[Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    """Gruppi (copia che resta, copie da mettere in quarantena)."""
    per_identita: Dict[str, List[Dict[str, Any]]] = {}
    for doc in modelli:
        if not attivo(doc):
            continue
        chiave = identita_f24(doc)
        if chiave:
            per_identita.setdefault(chiave, []).append(doc)
    gruppi = []
    for docs in per_identita.values():
        if len(docs) > 1:
            docs = sorted(docs, key=_priorita)
            gruppi.append((docs[0], docs[1:]))
    return gruppi


async def modello_uguale(db, doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Il modello gia' in archivio con lo stesso contenuto fiscale, se c'e'."""
    chiave = identita_f24(doc)
    if not chiave:
        return None
    for esistente in await db[COLL].find({}, {"_id": 0, "pdf_data": 0}).to_list(5000):
        if attivo(esistente) and identita_f24(esistente) == chiave:
            return esistente
    return None


async def metti_in_quarantena(db, *, dry_run: bool = True) -> Dict[str, Any]:
    """Quarantena dei modelli con lo stesso contenuto di un altro. Idempotente."""
    modelli = await db[COLL].find({}, {"_id": 0, "pdf_data": 0}).to_list(5000)
    gruppi = trova_doppioni(modelli)
    ora = datetime.now(timezone.utc).isoformat()
    elenco = []
    for resta, copie in gruppi:
        for copia in copie:
            elenco.append({
                "id": copia.get("id"), "file_name": copia.get("file_name"),
                "doppione_di": resta.get("id"), "file_che_resta": resta.get("file_name"),
                "data_versamento": (copia.get("dati_generali") or {}).get("data_versamento"),
            })
            if not dry_run:
                await db[COLL].update_one({"id": copia["id"]}, {"$set": {
                    "status": STATO_QUARANTENA,
                    "stato_prima_della_quarantena": copia.get("status"),
                    "motivo_quarantena": MOTIVO_DOPPIONE,
                    "doppione_di": resta.get("id"),
                    "quarantena_il": ora,
                }})
    return {"dry_run": dry_run, "gruppi": len(gruppi), "in_quarantena": len(elenco), "modelli": elenco}
