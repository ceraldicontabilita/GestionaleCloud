"""Popola `paghe_mensili` (il registro che alimenta la pagina Buste Paga) dai
cedolini e dai bonifici reali, invece di lasciarlo alla compilazione manuale.

La pagina Buste Paga dell'app non legge affatto la collection `cedolini`: legge
`paghe_mensili`, un registro pensato per l'inserimento a mano (importo busta,
bonifico ricevuto, acconti). Con 1466 cedolini importati e 203 bonifici gia'
riconciliati, non ha senso ricopiarli a mano — questo modulo lo fa una volta
per tutti i mesi in archivio, e resta richiamabile a ogni nuovo import.

Scelta prudente sul saldo: `bonifico_importo` viene SOLO dai bonifici bancari
davvero abbinati al cedolino (tabella `bonifici`, campo `cedolino_id`, gia'
verificato: 85 abbinamenti su 107 coincidono col netto al centesimo). Gli
acconti letti sulla busta (`cedolino.acconti.acconto_erogato`) vengono esposti
come campo informativo a parte, non sommati dentro `acconti[]`: sommarli al
bonifico rischierebbe di contare due volte la stessa somma, se il bonifico e'
gia' al netto dell'acconto trattenuto in busta. Il saldo del registro resta
quindi "netto dovuto meno bonifico ricevuto", il confronto piu' sicuro.

Non tocca un mese che un umano ha gia' modificato a mano (`origine` diverso da
"cedolino"): l'inserimento manuale vince sempre sulla sincronizzazione.
"""
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.hr.database import Collections


def _num(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _stato_e_saldo(busta: float, bonifico: float) -> Dict[str, Any]:
    if busta <= 0 and bonifico <= 0:
        stato = "vuoto"
    elif bonifico <= 0:
        stato = "in_attesa_pagamento"
    elif bonifico + 0.5 >= busta:
        stato = "pagato"
    else:
        stato = "parziale"
    return {"stato_pagamento": stato, "saldo": round(busta - bonifico, 2)}


async def sincronizza(db, anno: int = None) -> Dict[str, Any]:
    filtro_ced: Dict[str, Any] = {"tipo_cedolino": {"$in": ["ordinario", None]}}
    if anno:
        filtro_ced["anno"] = anno
    cedolini = await db[Collections.PAYSLIPS].find(filtro_ced, {"_id": 0, "pdf_data": 0}).to_list(3000)
    cedolini = [c for c in cedolini if c.get("dipendente_id") and c.get("anno") and c.get("mese")
               and c.get("netto") is not None]

    # pdf_data ESCLUSO (05/09/2026): con la quirk del $ne:None descritta sotto
    # questa query prende quasi tutti gli 887 bonifici, e 805 hanno il PDF
    # allegato (180 MB di base64). Qui servono solo cedolino_id e importo.
    bonifici = await db["bonifici"].find({"cedolino_id": {"$ne": None}}, {"_id": 0, "pdf_data": 0}).to_list(1000)
    per_cedolino: Dict[str, list] = {}
    for b in bonifici:
        # $ne:None nell'adattatore Supabase, come in Mongo, matcha anche i
        # documenti dove il campo manca del tutto (non solo quelli con null
        # esplicito) — b["cedolino_id"] andava in KeyError per la maggioranza
        # degli 887 bonifici (solo 142 hanno davvero cedolino_id), quindi
        # sincronizza() falliva SEMPRE prima ancora di leggere un cedolino.
        # Trovato dal primo giro reale dello scheduler in produzione.
        cid = b.get("cedolino_id")
        if cid:
            per_cedolino.setdefault(cid, []).append(b)

    # Prefetch di pagamenti_esiti (il motore unico di "Cedolini & Bonifici", che
    # copre anche i bonifici da Drive/ponte storico senza cedolino_id, non solo
    # quelli in `bonifici`): trovato da un review automatico prima del deploy,
    # senza questo ogni giro dello scheduler periodico sovrascriveva
    # stato_pagamento/bonifico_importo usando SOLO `bonifici.cedolino_id`
    # (una vista incompleta, 142 bonifici su 887), annullando le riconciliazioni
    # gia' fatte da _ricalcola_stato_paga in giri precedenti. Sommati una volta
    # sola per (dipendente_id, anno, mese), zero query aggiuntive nel ciclo.
    esiti_idx: Dict[tuple, float] = {}
    async for e in db["pagamenti_esiti"].find({}, {"_id": 0, "dipendente_id": 1, "anno": 1, "mese": 1, "importo": 1}):
        k = (e.get("dipendente_id"), e.get("anno"), e.get("mese"))
        esiti_idx[k] = round((esiti_idx.get(k) or 0) + (_num(e.get("importo")) or 0), 2)

    # Prefetch di paghe_mensili in blocco: l'adattatore Supabase non ha indici,
    # un find_one per cedolino (fino a 3000) su una tabella che cresce ad ogni
    # giro dentro lo stesso ciclo e' un O(N^2) che porta la sincronizzazione a
    # decine di secondi e puo' far scadere la richiesta (502). Si legge una
    # volta sola e si indicizza in memoria.
    esistenti_idx: Dict[tuple, Dict[str, Any]] = {}
    async for p in db["paghe_mensili"].find({}, {"_id": 0}):
        esistenti_idx[(p.get("dipendente_id"), p.get("anno"), p.get("mese"))] = p

    adesso = datetime.now(timezone.utc).isoformat()
    creati = aggiornati = saltati_manuali = 0

    for c in cedolini:
        dip, anno_c, mese_c = c["dipendente_id"], int(c["anno"]), int(c["mese"])
        esistente = esistenti_idx.get((dip, anno_c, mese_c))
        if esistente and esistente.get("origine") not in (None, "cedolino"):
            saltati_manuali += 1
            continue

        bon = per_cedolino.get(c.get("id"), [])
        bonifico_importo = round(sum(_num(b.get("importo")) or 0 for b in bon), 2)
        bonifico_data = max((b.get("data") for b in bon), default=None)
        # pagamenti_esiti e' la fonte autorevole quando presente (copre anche i
        # bonifici senza cedolino_id): vince su quella derivata da `bonifici`.
        tot_esiti = esiti_idx.get((dip, anno_c, mese_c))
        if tot_esiti is not None:
            bonifico_importo = tot_esiti

        acconti_busta = (c.get("acconti") or {}).get("acconto_erogato")

        doc = {
            "dipendente_id": dip, "anno": anno_c, "mese": mese_c,
            "importo_busta": c["netto"],
            "bonifico_ricevuto": bonifico_importo > 0,
            "bonifico_importo": bonifico_importo or None,
            "bonifico_data": bonifico_data,
            "acconti": esistente.get("acconti", []) if esistente else [],
            "giorni_lavorati": (c.get("periodo") or {}).get("giorni_lavorati") or c.get("giorni_lavorati"),
            "acconto_da_cedolino": acconti_busta,
            "livello": c.get("livello"),
            "cedolino_id": c.get("id"),
            "origine": "cedolino",
            "updated_at": adesso,
        }
        doc.update(_stato_e_saldo(c["netto"], bonifico_importo))
        doc = {k: v for k, v in doc.items() if v is not None or k in ("acconti",)}

        await db["paghe_mensili"].update_one(
            {"dipendente_id": dip, "anno": anno_c, "mese": mese_c}, {"$set": doc}, upsert=True)
        if esistente:
            aggiornati += 1
        else:
            creati += 1

    return {"cedolini_considerati": len(cedolini), "creati": creati,
            "aggiornati": aggiornati, "saltati_manuali": saltati_manuali}
