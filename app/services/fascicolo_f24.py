"""Materializzazione del fascicolo F24 mensile (§21 della specifica).

Un *fascicolo* raccoglie, per un soggetto fiscale e un periodo, tutto ciò che
è collegato allo stesso debito mensile:

  - gli F24 di quel soggetto/periodo (ordinario con DM10, RC01 di
    regolarizzazione, eventuali ravveduti);
  - le quietanze che ne provano il pagamento;
  - i cedolini del periodo associabili (§15);
  - la relazione DM10↔RC01 e l'eventuale allerta di doppio pagamento (§23);
  - i totali classificati (debito originario, regolarizzazione, sanzioni/interessi).

Prima questi legami erano solo calcolati al volo a ogni richiesta. Qui vengono
**materializzati** nella collezione `fascicoli_f24` (upsert per chiave
`{codice_fiscale}_{MM_AAAA}`), così restano consultabili e coerenti.

NB (regole cardine F24): il fascicolo NON crea F24 mancanti e NON trasforma un
saldo in costo; si limita a collegare documenti già presenti e a classificarne
le righe. Se manca l'F24 di una quietanza, resta l'alert bloccante a monte.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.engines import tributi_engine as te

COLL_F24 = "f24_unificato"
COLL_QUIETANZE = "quietanze_f24"
COLL_FISCAL_DOCUMENTS = "fiscal_documents"
COLL_CEDOLINI = "cedolini"
COLL_FASCICOLI = "fascicoli_f24"


def _cf_di(f24: Dict[str, Any]) -> str:
    return ((f24.get("dati_generali", {}) or {}).get("codice_fiscale")
            or f24.get("codice_fiscale") or "").strip().upper()


def chiave_fascicolo(codice_fiscale: str, periodo: Tuple[int, int]) -> str:
    """Chiave stabile del fascicolo: CF + periodo 'MM_AAAA'."""
    mese, anno = periodo
    return f"{(codice_fiscale or '').strip().upper()}_{mese:02d}_{anno}"


def _ha_rc01(f24: Dict[str, Any]) -> bool:
    return "RC01" in te.causali_inps(f24)


def _totali_classificati(f24s: List[Dict[str, Any]]) -> Dict[str, float]:
    """Somma le righe di tutti gli F24 del fascicolo in classi §21."""
    tot = {"debito_originario": 0.0, "regolarizzazione": 0.0,
           "sanzioni_interessi": 0.0}
    for f24 in f24s:
        rc01 = _ha_rc01(f24)
        for r in te._righe_f24(f24):
            imp = float(r.get("importo_debito", 0) or r.get("importo", 0) or 0)
            if imp <= 0:
                continue
            if r["_codice"].upper() in te.CODICI_RAVVEDIMENTO:
                tot["sanzioni_interessi"] += imp
            elif rc01:
                tot["regolarizzazione"] += imp
            else:
                tot["debito_originario"] += imp
    return {k: round(v, 2) for k, v in tot.items()}


async def costruisci_fascicolo(
    db, codice_fiscale: str, periodo: Tuple[int, int]
) -> Dict[str, Any]:
    """Costruisce (senza salvare) il fascicolo per soggetto+periodo.

    `periodo` è la tupla (mese, anno). Legge F24, quietanze e cedolini già
    presenti; non crea nulla. Ritorna il documento fascicolo."""
    mese, anno = periodo
    cf = (codice_fiscale or "").strip().upper()

    # --- F24 del soggetto, non eliminati, che cadono in quel periodo ---
    cur = db[COLL_F24].find(
        {"status": {"$ne": "eliminato"},
         "$or": [{"dati_generali.codice_fiscale": codice_fiscale},
                 {"codice_fiscale": codice_fiscale}]},
        {"_id": 0},
    )
    tutti = await cur.to_list(500)
    f24s = [f for f in tutti if te.periodo_prevalente(f) == periodo]

    ordinari = [f for f in f24s if not _ha_rc01(f)]
    rc01s = [f for f in f24s if _ha_rc01(f)]

    # --- Relazione DM10↔RC01 + eventuale doppio pagamento (§21/§23) ---
    relazioni: List[Dict[str, Any]] = []
    for ord_f24 in ordinari:
        for rc_f24 in rc01s:
            legame = te.confronta_dm10_rc01(ord_f24, rc_f24)
            if not legame.get("collegati"):
                continue
            doppio = te.rileva_doppio_pagamento(ord_f24, rc_f24)
            relazioni.append({
                "f24_ordinario_id": ord_f24.get("id"),
                "f24_rc01_id": rc_f24.get("id"),
                "tributi_comuni": legame.get("tributi_comuni", []),
                "possibile_doppio_pagamento": doppio.get("possibile_doppio_pagamento", False),
                "quota_potenzialmente_duplicata": doppio.get("quota_potenzialmente_duplicata", 0.0),
            })

    # --- Quietanze collegate (stesso soggetto) ---
    quietanze = await db[COLL_QUIETANZE].find(
        {"$or": [{"codice_fiscale": codice_fiscale},
                 {"dati_generali.codice_fiscale": codice_fiscale}]},
        {"_id": 0},
    ).to_list(200)
    quietanza_ids = [q.get("id") for q in quietanze if q.get("id")]
    # Quietanze reali dell'indice fiscale (`fiscal_documents`, categoria
    # quietanza_f24) agganciate ai modelli del fascicolo o referenziate da
    # `f24.quietanza_id`: registro unico, non solo la collezione storica.
    f24_ids_periodo = {str(f.get("id")) for f in f24s if f.get("id")}
    quietanza_ids_f24 = {str(f.get("quietanza_id")) for f in f24s if f.get("quietanza_id")}
    fiscal = await db[COLL_FISCAL_DOCUMENTS].find(
        {"category": "quietanza_f24"}, {"_id": 0, "pdf_data": 0},
    ).to_list(5000)
    for q in fiscal:
        qid = q.get("id")
        if not qid or qid in quietanza_ids:
            continue
        collegati = {str(v) for v in ([q.get("f24_id")] + list(q.get("f24_associati") or [])) if v}
        if str(qid) in quietanza_ids_f24 or collegati & f24_ids_periodo:
            quietanza_ids.append(qid)

    # --- Cedolini del periodo (azienda) associabili (§15) ---
    cedolini = await db[COLL_CEDOLINI].find(
        {"anno": anno, "mese": mese}, {"_id": 0}
    ).to_list(500)
    matricole_ced = {str(c.get("matricola")).strip().upper()
                     for c in cedolini if c.get("matricola")}
    cedolini_associati: List[str] = []
    cedolini_associabili = False
    for f24 in f24s:
        val = te.valuta_associazione_cedolini(
            f24, mese, anno, codice_fiscale_azienda=cf,
            matricole_cedolini=matricole_ced or None,
        )
        if val.get("associabile"):
            cedolini_associabili = True
    if cedolini_associabili:
        cedolini_associati = [c.get("id") for c in cedolini if c.get("id")]

    now = datetime.now(timezone.utc).isoformat()
    return {
        "chiave": chiave_fascicolo(cf, periodo),
        "codice_fiscale": codice_fiscale,
        "periodo": f"{mese:02d}/{anno}",
        "mese": mese,
        "anno": anno,
        "f24_ids": [f.get("id") for f in f24s if f.get("id")],
        "f24_ordinari_ids": [f.get("id") for f in ordinari if f.get("id")],
        "f24_rc01_ids": [f.get("id") for f in rc01s if f.get("id")],
        "quietanza_ids": quietanza_ids,
        "cedolino_ids": cedolini_associati,
        "relazioni_dm10_rc01": relazioni,
        "totali": _totali_classificati(f24s),
        "conteggi": {
            "f24": len(f24s), "ordinari": len(ordinari), "rc01": len(rc01s),
            "quietanze": len(quietanza_ids), "cedolini": len(cedolini_associati),
        },
        "aggiornato_il": now,
    }


async def salva_fascicolo(db, fascicolo: Dict[str, Any]) -> Dict[str, Any]:
    """Upsert del fascicolo per chiave; ritorna il documento salvato."""
    await db[COLL_FASCICOLI].update_one(
        {"chiave": fascicolo["chiave"]},
        {"$set": fascicolo},
        upsert=True,
    )
    return fascicolo


async def costruisci_e_salva(
    db, codice_fiscale: str, periodo: Tuple[int, int]
) -> Dict[str, Any]:
    return await salva_fascicolo(db, await costruisci_fascicolo(db, codice_fiscale, periodo))


async def leggi_fascicolo(
    db, codice_fiscale: str, periodo: Tuple[int, int]
) -> Optional[Dict[str, Any]]:
    return await db[COLL_FASCICOLI].find_one(
        {"chiave": chiave_fascicolo(codice_fiscale, periodo)}, {"_id": 0}
    )
