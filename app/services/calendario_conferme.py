"""Conferma manuale delle scadenze del calendario fiscale: writer unico.

La pagina Calendario fiscale conferma una scadenza alla volta; il titolare
puo' chiedere di confermare in blocco tutto il passato («dal 2015 ad oggi
tranne Intrastat», 07/10/2026). Entrambe le strade passano da qui: stessa
riga in ``calendario_fiscale`` (``completato_da = conferma_manuale``), stesso
evento di audit per scadenza, nessuna seconda scrittura.

La conferma manuale e' una dichiarazione del titolare, non una prova
documentale: la riga resta ``livello_evidenza = manuale`` e una quietanza
F24 che arriva dopo la sostituisce con la prova (``quietanza_f24``).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, Iterable, Optional

logger = logging.getLogger(__name__)

FONTE_PAGINA = "pagina_calendario_fiscale"
FONTE_MASSIVA = "conferma_massiva_titolare"
COMPLETATO_DA = "conferma_manuale"

# Decisione del titolare (07/10/2026): tutto il calendario dal 2015 a oggi
# risulta adempiuto, tranne Intrastat. Si esegue una volta sola al primo
# avvio dopo il deploy; il marcatore in ``sistema_stato`` conserva l'esito.
CONFERMA_MASSIVA_TITOLARE = {
    "chiave": "calendario_conferma_massiva_2015_oggi_v1",
    "dal": 2015,
    "escludi_tipi": ("INTRASTAT",),
    "note": "Conferma del titolare del 07/10/2026: scadenze dal 2015 a oggi adempiute (esclusa Intrastat)",
}


def _oggi() -> date:
    return datetime.now(timezone.utc).date()


async def conferma_scadenza(db, *, anno: int, scadenza_id: str, note: Optional[str], template: Optional[Dict[str, Any]],
                            fonte: str = FONTE_PAGINA, utente: str = "utente_autenticato",
                            oggi: Optional[date] = None) -> Dict[str, Any]:
    """Segna una scadenza come adempiuta per dichiarazione del titolare.

    Idempotente: una scadenza gia' completata (anche da quietanza) non si
    tocca. ``template`` e' la riga generata dal calendario, usata solo
    all'inserimento; senza template la riga deve gia' esistere. Una scadenza
    con data oltre ``oggi`` non si conferma (``esito = futura``).
    """
    esistente = await db["calendario_fiscale"].find_one({"anno": anno, "id": scadenza_id}, {"_id": 0})
    if not template and not esistente:
        return {"success": False, "esito": "non_trovata"}
    if esistente and esistente.get("completato"):
        return {"success": True, "esito": "gia_completata", "completato_da": esistente.get("completato_da")}
    # Una scadenza futura non puo' risultare adempiuta: il 06/10/2026 ventitre'
    # scadenze da ottobre 2026 ad aprile 2027 (770, Redditi, IVA, INPS, ritenute,
    # acconti) erano state confermate e lo scadenzario non le mostrava piu'.
    data_scadenza = str((esistente or template or {}).get("data") or "")
    if data_scadenza and data_scadenza > (oggi or _oggi()).isoformat():
        return {"success": False, "esito": "futura", "data": data_scadenza}

    now = datetime.now(timezone.utc).isoformat()
    result = await db["calendario_fiscale"].update_one(
        {"anno": anno, "id": scadenza_id},
        {
            "$setOnInsert": {**(template or {}), "anno": anno, "id": scadenza_id, "created_at": now},
            "$set": {
                "completato": True,
                "data_completamento": now,
                "note_completamento": note,
                "completato_da": COMPLETATO_DA,
                "updated_at": now,
            },
        },
        upsert=True,
    )

    from app.services.audit_logger import log_evento

    await log_evento(
        modulo="calendario_fiscale",
        azione="scadenza_confermata_manualmente",
        entita_id=scadenza_id,
        entita_collection="calendario_fiscale",
        vecchio_stato={"completato": False},
        nuovo_stato={"completato": True, "anno": anno, "note": note},
        fonte=fonte,
        utente=utente,
        db=db,
    )
    return {"success": True, "esito": "confermata", "modificati": int(getattr(result, "modified_count", 0) or 0)}


async def conferma_massiva(db, *, dal: int, al: Optional[int] = None, oggi: Optional[date] = None,
                           escludi_tipi: Iterable[str] = (), note: Optional[str] = None,
                           utente: str = "titolare", dry_run: bool = False) -> Dict[str, Any]:
    """Conferma tutte le scadenze con data fino a ``oggi`` degli anni ``dal``..``al``.

    Le scadenze future, quelle dei tipi esclusi e quelle gia' completate non
    si toccano e si contano a parte: il riepilogo dice esattamente cosa e'
    stato dichiarato adempiuto. Con ``dry_run`` non scrive nulla.
    """
    from app.routers.fiscalita_italiana import _leggi_calendario_anno

    oggi = oggi or _oggi()
    al = al or oggi.year
    esclusi = {str(t).upper() for t in escludi_tipi}
    oggi_iso = oggi.isoformat()
    riepilogo: Dict[str, Any] = {"dal": dal, "al": al, "oggi": oggi_iso, "escludi_tipi": sorted(esclusi), "dry_run": dry_run,
                                 "confermate": 0, "gia_completate": 0, "escluse": 0, "future": 0, "per_anno": {},
                                 "confermate_elenco": []}
    for anno in range(dal, al + 1):
        conteggio = {"confermate": 0, "gia_completate": 0, "escluse": 0, "future": 0}
        for scadenza in await _leggi_calendario_anno(db, anno):
            tipo = str(scadenza.get("tipo") or "").upper()
            data_scadenza = str(scadenza.get("data") or "")
            if tipo in esclusi:
                conteggio["escluse"] += 1
                continue
            if not data_scadenza or data_scadenza > oggi_iso:
                conteggio["future"] += 1
                continue
            if scadenza.get("completato"):
                conteggio["gia_completate"] += 1
                continue
            sid = str(scadenza.get("id") or "")
            if not sid:
                conteggio["escluse"] += 1
                continue
            if not dry_run:
                template = {k: v for k, v in scadenza.items()
                            if k not in ("provenienza_stato", "livello_evidenza", "origine_regola")}
                esito = await conferma_scadenza(db, anno=anno, scadenza_id=sid, note=note, template=template,
                                                fonte=FONTE_MASSIVA, utente=utente)
                if esito.get("esito") != "confermata":
                    conteggio["gia_completate"] += 1
                    continue
            conteggio["confermate"] += 1
            riepilogo["confermate_elenco"].append({"anno": anno, "id": sid, "tipo": tipo, "data": data_scadenza})
        riepilogo["per_anno"][str(anno)] = conteggio
        for k in ("confermate", "gia_completate", "escluse", "future"):
            riepilogo[k] += conteggio[k]
    return riepilogo


async def conferma_massiva_una_volta(db) -> Dict[str, Any]:
    """La conferma massiva decisa dal titolare, eseguita una volta per chiave."""
    chiave = CONFERMA_MASSIVA_TITOLARE["chiave"]
    stato = await db["sistema_stato"].find_one({"chiave": chiave}, {"_id": 0})
    if stato and stato.get("eseguito_il"):
        return {"eseguita": False, "gia_fatta_il": stato["eseguito_il"], "confermate": stato.get("confermate")}
    riepilogo = await conferma_massiva(
        db, dal=int(CONFERMA_MASSIVA_TITOLARE["dal"]), escludi_tipi=CONFERMA_MASSIVA_TITOLARE["escludi_tipi"],
        note=str(CONFERMA_MASSIVA_TITOLARE["note"]), utente="titolare",
    )
    now = datetime.now(timezone.utc).isoformat()
    await db["sistema_stato"].update_one(
        {"chiave": chiave},
        {"$set": {"chiave": chiave, "eseguito_il": now, "confermate": riepilogo["confermate"],
                  "gia_completate": riepilogo["gia_completate"], "escluse": riepilogo["escluse"],
                  "future": riepilogo["future"], "per_anno": riepilogo["per_anno"],
                  "note": CONFERMA_MASSIVA_TITOLARE["note"]}},
        upsert=True,
    )
    logger.info("[CALENDARIO] conferma massiva del titolare: confermate=%s gia' completate=%s escluse=%s future=%s",
                riepilogo["confermate"], riepilogo["gia_completate"], riepilogo["escluse"], riepilogo["future"])
    return {"eseguita": True, **{k: riepilogo[k] for k in ("confermate", "gia_completate", "escluse", "future", "per_anno")}}
