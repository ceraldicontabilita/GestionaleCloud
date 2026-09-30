"""Anomalie F24 persistite: possibile doppio pagamento e righe «da verificare».

Il motore che decide resta `app/engines/tributi_engine.py` (`rileva_doppio_pagamento`,
`classifica_f24`): qui si tiene solo la memoria di cio' che il titolare ha deciso.

- **Doppio pagamento DM10 <-> RC01** (specifica §23): un documento per coppia di F24
  in `f24_anomalie_doppio_pagamento`, con id stabile. Il giro lo crea una volta sola
  (`da_verificare`, alert `POSSIBILE_DOPPIO_PAGAMENTO_F24`); una coppia gia' decisa non
  si riapre e non si duplica. Lo stato lo sceglie il titolare da una lista, con il motivo.
- **Controlli §18** (`controlli_f24`): un solo alert `F24_CONTROLLO_DA_VERIFICARE` per
  modello, col dettaglio delle righe; si chiude da solo quando il modello non ne ha piu'.

Niente si cancella: lo stato cambia e `storico` conserva ogni passaggio.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from app.db_collections import COLL_ALERTS
from app.document_repository import metadata_projection
from app.engines import tributi_engine as te

logger = logging.getLogger(__name__)

COLL_F24 = "f24_unificato"
COLL_ANOMALIE_DOPPIO = "f24_anomalie_doppio_pagamento"
ALERT_DOPPIO_PAGAMENTO = "POSSIBILE_DOPPIO_PAGAMENTO_F24"
ALERT_CONTROLLO = "F24_CONTROLLO_DA_VERIFICARE"

STATO_APERTO = "da_verificare"
# Ogni stato diverso da «da_verificare» e' una decisione: senza motivo non si registra.
STATI_CON_MOTIVO = tuple(s for s in te.STATI_ANOMALIA_DOPPIO_PAGAMENTO if s != STATO_APERTO)


def _ora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cents(valore: Any) -> int:
    return int((Decimal(str(valore or 0)) * 100).quantize(Decimal("1")))


def id_anomalia(f24_ordinario_id: Any, f24_rc01_id: Any) -> str:
    """Id stabile della coppia: lo stesso per ogni rilevazione, in qualunque ordine."""
    coppia = "|".join(sorted([str(f24_ordinario_id), str(f24_rc01_id)]))
    return "dp_" + hashlib.sha256(coppia.encode("utf-8")).hexdigest()[:24]


async def _leggi_f24(db) -> List[Dict[str, Any]]:
    docs = await db[COLL_F24].find({}, metadata_projection(COLL_F24, {"_id": 0, "pdf_data": 0})).to_list(5000)
    return [d for d in docs if d.get("status") != "eliminato"]


def trova_coppie_doppio_pagamento(docs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Coppie ordinario <-> RC01 con possibile doppio pagamento (funzione pura)."""
    ordinari, regolarizzazioni = [], []
    for d in docs:
        causali = te.causali_inps(d)
        if "RC01" in causali:
            regolarizzazioni.append(d)
        elif causali or d.get("sezione_erario"):
            ordinari.append(d)

    anomalie = []
    for rc in regolarizzazioni:
        periodo_rc = te.periodo_prevalente(rc)
        for ordinario in ordinari:
            if te.periodo_prevalente(ordinario) != periodo_rc:
                continue  # il confronto completo e' costoso: pre-filtro sul periodo
            esito = te.rileva_doppio_pagamento(ordinario, rc)
            if not esito.get("possibile_doppio_pagamento"):
                continue
            anomalie.append({
                "id": id_anomalia(ordinario.get("id"), rc.get("id")),
                "f24_ordinario_id": ordinario.get("id"),
                "f24_ordinario_file": ordinario.get("file_name") or ordinario.get("filename"),
                "f24_rc01_id": rc.get("id"),
                "f24_rc01_file": rc.get("file_name") or rc.get("filename"),
                "periodo": esito["dettaglio"]["controlli"][1]["rc01"],
                "quota_potenzialmente_duplicata": esito["quota_potenzialmente_duplicata"],
                "quota_sanzioni_interessi": esito["quota_sanzioni_interessi"],
                "messaggio": esito["messaggio"],
                "stato": esito["stato"],
            })
    return {"esaminati_ordinari": len(ordinari), "esaminati_rc01": len(regolarizzazioni),
            "anomalie": anomalie}


async def unisci_stati_salvati(db, anomalie: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Ogni anomalia rilevata prende lo stato scelto dal titolare, se c'e'."""
    if not anomalie:
        return anomalie
    salvate = await db[COLL_ANOMALIE_DOPPIO].find(
        {"id": {"$in": [a["id"] for a in anomalie]}}, {"_id": 0},
    ).to_list(len(anomalie))
    per_id = {s["id"]: s for s in salvate}
    for a in anomalie:
        salvata = per_id.get(a["id"])
        if salvata:
            a["stato"] = salvata.get("stato") or a["stato"]
            a["storico"] = salvata.get("storico") or []
    return anomalie


async def _apri_alert_doppio(db, doc: Dict[str, Any]) -> None:
    from app.services.alert_engine import genera_alert

    periodo = doc.get("periodo") or "periodo non letto"
    await genera_alert(
        ALERT_DOPPIO_PAGAMENTO, doc["id"], COLL_ANOMALIE_DOPPIO,
        (f"F24 {doc.get('f24_ordinario_file') or doc['f24_ordinario_id']} e "
         f"{doc.get('f24_rc01_file') or doc['f24_rc01_id']} ({periodo}): entrambi pagati per lo stesso debito. "
         f"Quota di capitale possibilmente duplicata {doc['quota_duplicata_cents'] / 100:.2f} EUR, "
         f"sanzioni e interessi {doc['quota_sanzioni_interessi_cents'] / 100:.2f} EUR."),
        db, extra={"f24_ordinario_id": doc["f24_ordinario_id"], "f24_rc01_id": doc["f24_rc01_id"]},
    )


async def rileva_doppi_pagamenti(db, *, dry_run: bool = True) -> Dict[str, Any]:
    """Crea le anomalie nuove (una per coppia) e il loro alert. Idempotente: una coppia
    gia' presente non si duplica, e una decisa non si riapre."""
    scansione = trova_coppie_doppio_pagamento(await _leggi_f24(db))
    nuove, presenti, alert_ripresi = [], 0, 0
    for a in scansione["anomalie"]:
        esistente = await db[COLL_ANOMALIE_DOPPIO].find_one({"id": a["id"]}, {"_id": 0})
        if esistente:
            presenti += 1
            if esistente.get("stato") == STATO_APERTO and not dry_run:
                # Rete: l'anomalia c'e' ma l'alert non e' partito (guasto al giro prima).
                await _apri_alert_doppio(db, esistente)
                alert_ripresi += 1
            continue
        doc = {
            "id": a["id"],
            "f24_ordinario_id": a["f24_ordinario_id"], "f24_ordinario_file": a["f24_ordinario_file"],
            "f24_rc01_id": a["f24_rc01_id"], "f24_rc01_file": a["f24_rc01_file"],
            "periodo": a["periodo"],
            "stato": STATO_APERTO,
            "quota_duplicata_cents": _cents(a["quota_potenzialmente_duplicata"]),
            "quota_sanzioni_interessi_cents": _cents(a["quota_sanzioni_interessi"]),
            "messaggio": a["messaggio"],
            "storico": [{"stato": STATO_APERTO, "motivo": "rilevata dal motore F24", "at": _ora(), "da": "sistema"}],
            "created_at": _ora(),
        }
        nuove.append(doc["id"])
        if dry_run:
            continue
        await db[COLL_ANOMALIE_DOPPIO].insert_one(dict(doc))
        await _apri_alert_doppio(db, doc)
    return {
        "dry_run": dry_run,
        "esaminati_ordinari": scansione["esaminati_ordinari"],
        "esaminati_rc01": scansione["esaminati_rc01"],
        "rilevate": len(scansione["anomalie"]),
        "nuove": len(nuove), "gia_presenti": presenti, "alert_ripresi": alert_ripresi,
        "ids_nuove": nuove,
    }


class StatoNonValido(ValueError):
    """Stato fuori lista o motivo mancante: l'API lo traduce in 422."""

    def __init__(self, messaggio: str, dettagli: Optional[Dict[str, Any]] = None):
        super().__init__(messaggio)
        self.dettagli = dettagli or {}


async def imposta_stato(db, anomalia_id: str, stato: str, motivo: Optional[str], da: str) -> Optional[Dict[str, Any]]:
    """Registra la decisione del titolare. None se l'anomalia non esiste.

    Lasciare `da_verificare` chiude l'alert; riportarla a `da_verificare` lo riapre.
    """
    from app.services.alert_engine import risolvi_alert

    if stato not in te.STATI_ANOMALIA_DOPPIO_PAGAMENTO:
        raise StatoNonValido("Stato non valido", {"stati_ammessi": list(te.STATI_ANOMALIA_DOPPIO_PAGAMENTO)})
    motivo = (motivo or "").strip()
    if stato in STATI_CON_MOTIVO and not motivo:
        raise StatoNonValido(
            "Il motivo e' obbligatorio per questo stato",
            {"stati_con_motivo": list(STATI_CON_MOTIVO)},
        )
    doc = await db[COLL_ANOMALIE_DOPPIO].find_one({"id": anomalia_id}, {"_id": 0})
    if not doc:
        return None
    storico = list(doc.get("storico") or [])
    storico.append({"stato": stato, "motivo": motivo, "at": _ora(), "da": da})
    await db[COLL_ANOMALIE_DOPPIO].update_one(
        {"id": anomalia_id}, {"$set": {"stato": stato, "storico": storico, "updated_at": _ora()}},
    )
    doc.update(stato=stato, storico=storico)
    if stato == STATO_APERTO:
        await _apri_alert_doppio(db, doc)
    else:
        await risolvi_alert(ALERT_DOPPIO_PAGAMENTO, anomalia_id, db, resolved_by=da)
    return doc


def _dettaglio_controlli(f24: Dict[str, Any], controlli: List[Dict[str, Any]]) -> str:
    nome = f24.get("file_name") or f24.get("filename") or f24.get("id")
    voci = "; ".join(
        f"{c['sezione']} {c['codice'] or '(codice assente)'}: {c['motivo']}" for c in controlli[:10]
    )
    return f"F24 {nome}: {len(controlli)} righe da verificare. {voci}"


async def controlla_f24_da_verificare(db, *, dry_run: bool = False) -> Dict[str, Any]:
    """Un alert per ogni modello con righe «da verificare»; lo chiude quando non ce ne sono piu'."""
    from app.constants.canale_documento import STATO_ALERT_APERTO
    from app.services.alert_engine import genera_alert, risolvi_alert

    aperti = chiusi = 0
    con_controlli: List[str] = []
    for f24 in await _leggi_f24(db):
        f24_id = str(f24.get("id") or "")
        controlli = te.controlli_f24(f24) if f24_id else []
        if not controlli:
            continue
        con_controlli.append(f24_id)
        if not dry_run:
            creato = await genera_alert(
                ALERT_CONTROLLO, f24_id, COLL_F24, _dettaglio_controlli(f24, controlli), db,
                extra={"controlli": controlli},
            )
            aperti += 1 if creato else 0
    if not dry_run:
        # Un solo giro sugli alert aperti: chiude quelli il cui modello non ha piu' controlli.
        ancora = set(con_controlli)
        for alert in await db[COLL_ALERTS].find(
            {"codice": ALERT_CONTROLLO, "stato": STATO_ALERT_APERTO}, {"_id": 0, "entita_id": 1},
        ).to_list(5000):
            if alert.get("entita_id") not in ancora:
                chiusi += await risolvi_alert(ALERT_CONTROLLO, alert["entita_id"], db)
    return {"dry_run": dry_run, "modelli_con_controlli": len(con_controlli),
            "alert_aperti": aperti, "alert_chiusi": chiusi, "ids": con_controlli}


async def giro_anomalie_f24(db) -> Dict[str, Any]:
    """Il giro dei 30 minuti: doppi pagamenti e controlli §18, scritti davvero."""
    doppi = await rileva_doppi_pagamenti(db, dry_run=False)
    controlli = await controlla_f24_da_verificare(db, dry_run=False)
    return {"doppi_pagamenti": doppi, "controlli": controlli}
