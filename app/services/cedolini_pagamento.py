"""Stato di pagamento di un cedolino del gestionale (``cedolini``): un solo scrittore.

Il campo e' ``pagato`` (mai ``pagata``), con ``importo_pagato``, ``saldo_residuo``,
``data_pagamento``, ``metodo_pagamento`` e la lista ``pagamenti`` (una voce per
pagamento, con un ``riferimento`` univoco: la stessa prova vista due volte non
raddoppia). Lo usano:

* il motore automatico all'import (``salari_unificati_v2``, dopo
  ``associa_bonifici_stipendi``);
* il pagamento registrato a mano (``registra_pagamento_salario``);
* l'HR, quando l'associazione manuale di un bonifico porta il mese di
  ``paghe_mensili`` a ``pagato`` (``allinea_cedolino_gestionale_da_paghe``), e
  quando la ritira.

Nessun altro punto scrive ``pagato`` sui cedolini.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from app.constants.stati_associazione_bonifico import STATO_PAGA_PAGATO
from app.services.cedolini_versioni import STATUS_SOSTITUITO

logger = logging.getLogger(__name__)

FONTE_AUTOMATICA = "riconciliazione_automatica"
FONTE_MANUALE = "pagamento_manuale"
FONTE_HR = "hr_associazione_manuale"

__all__ = [
    "FONTE_AUTOMATICA", "FONTE_MANUALE", "FONTE_HR",
    "trova_cedolino_gestionale", "segna_cedolino_pagato", "riapri_cedolino",
    "allinea_cedolino_gestionale_da_paghe",
]


def _cents(valore: Any) -> Optional[int]:
    if valore in (None, ""):
        return None
    try:
        return int((Decimal(str(valore)) * 100).quantize(Decimal("1")))
    except (ValueError, ArithmeticError):
        return None


def _ora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tipo_normalizzato(valore: Any) -> str:
    """L'HR dice ``ordinario``, il gestionale ``mensile`` (o niente): stessa busta."""
    tipo = str(valore or "").strip().lower()
    return "mensile" if tipo in ("", "mensile", "ordinario") else tipo


async def trova_cedolino_gestionale(db, *, cedolino_id: Optional[str] = None,
                                    codice_fiscale: Optional[str] = None,
                                    anno: Optional[int] = None, mese: Optional[int] = None,
                                    tipo_cedolino: Any = None) -> Optional[Dict[str, Any]]:
    """Il cedolino del gestionale per id, altrimenti per CF + anno + mese + tipo.

    Una versione ``sostituito`` non e' il cedolino. Con piu' candidati attivi
    dello stesso tipo non si sceglie: ``None``, e chi chiama lo dichiara."""
    proiezione = {"_id": 0, "pdf_data": 0, "pdf_text": 0, "enhanced_parsing": 0}
    if cedolino_id:
        doc = await db["cedolini"].find_one({"id": cedolino_id}, proiezione)
        if doc and doc.get("status") != STATUS_SOSTITUITO:
            return doc
    cf = str(codice_fiscale or "").strip().upper()
    if not (cf and anno and mese):
        return None
    candidati = await db["cedolini"].find(
        {"codice_fiscale": cf, "anno": int(anno), "mese": int(mese)}, proiezione).to_list(50)
    tipo = _tipo_normalizzato(tipo_cedolino)
    attivi = [c for c in candidati if c.get("status") != STATUS_SOSTITUITO
              and _tipo_normalizzato(c.get("tipo_cedolino")) == tipo]
    if len(attivi) != 1:
        if len(attivi) > 1:
            logger.warning("[cedolini] %s %s/%s %s: %d cedolini attivi, nessuno scelto",
                           cf, mese, anno, tipo, len(attivi))
        return None
    return attivi[0]


def _stato_da_pagamenti(cedolino: Dict[str, Any], pagamenti: List[Dict[str, Any]],
                        pagato_forzato: Optional[bool]) -> Dict[str, Any]:
    netto = _cents(cedolino.get("netto") if cedolino.get("netto") not in (None, "") else cedolino.get("netto_mese"))
    importo = sum(_cents(p.get("importo")) or 0 for p in pagamenti)
    if pagato_forzato is not None:
        pagato = bool(pagato_forzato)
    else:
        pagato = netto is not None and importo >= netto and importo > 0
    date = sorted(str(p.get("data") or "")[:10] for p in pagamenti if p.get("data"))
    metodi = [p.get("metodo") for p in pagamenti if p.get("metodo")]
    return {
        "pagato": pagato,
        "importo_pagato": importo / 100,
        "saldo_residuo": (netto - importo) / 100 if netto is not None else None,
        "pagamenti": pagamenti,
        "data_pagamento": date[-1] if date else None,
        "metodo_pagamento": metodi[-1] if metodi else cedolino.get("metodo_pagamento"),
        "updated_at": _ora(),
    }


async def segna_cedolino_pagato(db, cedolino: Dict[str, Any], *, importo: Any, data: Optional[str],
                                riferimento: str, fonte: str, metodo: str = "bonifico",
                                pagato: Optional[bool] = None, tipo_pagamento: str = "saldo",
                                extra: Optional[Dict[str, Any]] = None,
                                campi_extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Registra (o aggiorna) il pagamento ``riferimento`` sul cedolino e ricalcola lo stato.

    ``pagato`` esplicito vince sul confronto importo/netto (l'HR conosce lo stato
    del mese, acconti compresi); ``None`` lo deduce: pagato quando i pagamenti
    coprono il netto al centesimo. Idempotente sul ``riferimento``."""
    voce = {
        "riferimento": riferimento, "fonte": fonte,
        "importo": (_cents(importo) or 0) / 100, "metodo": metodo,
        "data": str(data or "")[:10] or None, "tipo": tipo_pagamento,
        "registrato_il": _ora(), **(extra or {}),
    }
    pagamenti = [p for p in (cedolino.get("pagamenti") or []) if p.get("riferimento") != riferimento]
    pagamenti.append(voce)
    stato = _stato_da_pagamenti(cedolino, pagamenti, pagato)
    stato.update(campi_extra or {})
    await db["cedolini"].update_one({"id": cedolino["id"]}, {"$set": stato})
    cedolino.update(stato)
    return {"cedolino_id": cedolino["id"], "pagato": stato["pagato"],
            "importo_pagato": stato["importo_pagato"], "pagamenti": len(pagamenti)}


async def riapri_cedolino(db, cedolino: Dict[str, Any], *, riferimento: str,
                          pagato: Optional[bool] = None) -> Dict[str, Any]:
    """Toglie il pagamento ``riferimento`` e ricalcola lo stato dai pagamenti rimasti.

    Un riferimento che il cedolino non ha non cambia niente (un'altra prova,
    per esempio la riconciliazione automatica, resta com'e')."""
    prima = cedolino.get("pagamenti") or []
    pagamenti = [p for p in prima if p.get("riferimento") != riferimento]
    if len(pagamenti) == len(prima):
        return {"cedolino_id": cedolino["id"], "esito": "riferimento_assente",
                "pagato": bool(cedolino.get("pagato"))}
    stato = _stato_da_pagamenti(cedolino, pagamenti, pagato)
    await db["cedolini"].update_one({"id": cedolino["id"]}, {"$set": stato})
    cedolino.update(stato)
    return {"cedolino_id": cedolino["id"], "esito": "riaperto" if not stato["pagato"] else "ancora_pagato",
            "pagato": stato["pagato"], "importo_pagato": stato["importo_pagato"], "pagamenti": len(pagamenti)}


async def allinea_cedolino_gestionale_da_paghe(db_hr, db_gest, dipendente_id: str, anno: int, mese: int, *,
                                               riferimento: str, importo: Any = None,
                                               data: Optional[str] = None,
                                               ritira: bool = False) -> Dict[str, Any]:
    """L'associazione manuale di un bonifico in HR si riflette sul cedolino del gestionale.

    Lo stato vero del mese e' ``paghe_mensili.stato_pagamento`` (motore unico
    ``_ricalcola_stato_paga``): qui si legge quello e si porta sul cedolino
    collegato (``cedolino_id`` HR → ``gestionale_cedolino_id``, altrimenti
    CF + anno + mese + tipo). Con ``ritira`` il pagamento esce e il cedolino si
    riapre se non resta altro. Non blocca mai l'HR: un gestionale non
    raggiungibile o un cedolino non trovato si dichiarano nell'esito."""
    esito: Dict[str, Any] = {"riferimento": riferimento, "cedolino_id": None, "esito": None}
    if db_gest is None:
        esito["esito"] = "gestionale_non_raggiungibile"
        return esito
    try:
        paga = await db_hr.paghe_mensili.find_one(
            {"dipendente_id": dipendente_id, "anno": int(anno), "mese": int(mese)}, {"_id": 0})
        dip = await db_hr.dipendenti.find_one({"id": dipendente_id}, {"_id": 0, "codice_fiscale": 1})
        ced_hr = None
        if paga and paga.get("cedolino_id"):
            ced_hr = await db_hr.cedolini.find_one({"id": paga["cedolino_id"]},
                                                   {"_id": 0, "gestionale_cedolino_id": 1,
                                                    "tipo_cedolino": 1, "codice_fiscale": 1})
        cedolino = await trova_cedolino_gestionale(
            db_gest,
            cedolino_id=(ced_hr or {}).get("gestionale_cedolino_id"),
            codice_fiscale=(ced_hr or {}).get("codice_fiscale") or (dip or {}).get("codice_fiscale"),
            anno=anno, mese=mese, tipo_cedolino=(ced_hr or {}).get("tipo_cedolino"),
        )
        if not cedolino:
            esito["esito"] = "cedolino_gestionale_non_trovato"
            return esito
        esito["cedolino_id"] = cedolino["id"]
        stato_mese = (paga or {}).get("stato_pagamento")
        pagato = stato_mese == STATO_PAGA_PAGATO if stato_mese else None
        if importo in (None, ""):
            importo = (paga or {}).get("bonifico_importo")   # il bonifico ricevuto del registro paghe
        if ritira:
            # tolto il pagamento, lo stato lo dicono i pagamenti rimasti (il
            # registro paghe puo' non essere ancora stato ricalcolato)
            esito.update(await riapri_cedolino(db_gest, cedolino, riferimento=riferimento))
        else:
            esito.update(await segna_cedolino_pagato(
                db_gest, cedolino, importo=importo, data=data, riferimento=riferimento,
                fonte=FONTE_HR, pagato=pagato,
                extra={"dipendente_id_hr": dipendente_id, "stato_mese": stato_mese}))
            esito["esito"] = "segnato"
        esito["stato_mese"] = stato_mese
    except Exception as exc:  # noqa: BLE001 - il lato HR e' gia' scritto, il difetto si dichiara
        logger.warning("[cedolini] stato pagato non allineato per %s %s/%s (%s: %s)",
                       dipendente_id, mese, anno, type(exc).__name__, exc)
        esito["esito"] = f"errore:{type(exc).__name__}"
    return esito
