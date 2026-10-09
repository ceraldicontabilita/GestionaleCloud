"""Popola `paghe_mensili` (il registro che alimenta la pagina Buste Paga) dai
cedolini e dai bonifici reali, invece di lasciarlo alla compilazione manuale.

La pagina Buste Paga dell'app non legge affatto la collection `cedolini`: legge
`paghe_mensili`, un registro pensato per l'inserimento a mano (importo busta,
bonifico ricevuto, acconti). Con 1466 cedolini importati e 203 bonifici gia'
riconciliati, non ha senso ricopiarli a mano — questo modulo lo fa una volta
per tutti i mesi in archivio, e resta richiamabile a ogni nuovo import.

Il dovuto usa la regola unica di `posizione_dipendente.dovuto_busta`:
netto stampato + recupero acconto esplicito del cedolino. Entrambi restano
visibili separatamente. L'acconto recuperato non viene inserito in
`acconti[]` e non prova che un bonifico sia stato pagato. I pagamenti
provengono da `pagamenti_esiti`, `bonifici` e dagli acconti registrati,
contati una sola volta. Il saldo e' dovuto meno pagamenti effettivi.

Non tocca un mese che un umano ha gia' modificato a mano (`origine` diverso da
"cedolino"): l'inserimento manuale vince sempre sulla sincronizzazione.

Un bonifico arrivato **prima** della busta lascia il mese `in_attesa_busta`
(riga senza `importo_busta`, scritta dal motore unico `_ricalcola_stato_paga`):
qui, all'arrivo del cedolino, la riga riceve la busta e i pagamenti gia'
depositati (`pagamenti_esiti`, acconti) la chiudono da soli: pagato o parziale.
"""
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.constants.stati_associazione_bonifico import (
    esiti_riconciliati, esiti_confermati, ha_riscontro_bancario, stato_paga_mese,
)
from app.hr.database import Collections
from app.hr.services.regole_pagamenti_dipendenti import filtra_acconti_contanti
from app.services.posizione_dipendente import ZERO, acconti_registro_del_mese, dovuto_busta, importo


def _num(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _stato_e_saldo(busta: Any, erogato: Any, *, bonifico: Any = 0,
                   riconciliato: bool = False) -> Dict[str, Any]:
    """Stesso motore di ``_ricalcola_stato_paga``: confronto in Decimal al
    centesimo, nessuna tolleranza (titolare 02/10/2026)."""
    busta_d = importo(busta)
    erogato_d = importo(erogato) or ZERO
    stato = stato_paga_mese(busta_d, erogato_d)
    if (importo(bonifico) or ZERO) > ZERO and busta_d is not None and not riconciliato:
        stato = "da_verificare"
    return {"stato_pagamento": stato,
            "saldo": float(busta_d - erogato_d) if busta_d is not None else None}


def _mese_registro(c: Dict[str, Any]) -> int:
    """Mese tecnico usato dalla pagina Paghe: 13 e 14 restano separati."""
    tipo = str(c.get("tipo_cedolino") or "ordinario").strip().lower()
    if tipo == "tredicesima":
        return 13
    if tipo == "quattordicesima":
        return 14
    return int(c["mese"])


_SYNC_LOCK = asyncio.Lock()


async def sincronizza(db, anno: int = None) -> Dict[str, Any]:
    # Drive e upload manuale possono terminare insieme: non creare due righe
    # per lo stesso mese mentre entrambi vedono ancora il registro precedente.
    async with _SYNC_LOCK:
        return await _sincronizza(db, anno)


async def _sincronizza(db, anno: int = None) -> Dict[str, Any]:
    from app.hr.db_supabase import SupabaseDatabase

    if isinstance(db, SupabaseDatabase):
        await db.refresh_collections("cedolini", "paghe_mensili", "dipendenti", "pagamenti_esiti")
    filtro_ced: Dict[str, Any] = {
        "tipo_cedolino": {"$in": ["ordinario", "mensile", "tredicesima", "quattordicesima", None]}
    }
    if anno:
        filtro_ced["anno"] = anno
    cedolini = await db[Collections.PAYSLIPS].find(filtro_ced, {"_id": 0, "pdf_data": 0}).to_list(3000)
    from app.services.cedolini_rapporti import raggruppa_cedolini
    cedolini = list(raggruppa_cedolini(c for c in cedolini if c.get("dipendente_id")).values())

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
    prove_idx: Dict[tuple, list] = {}
    from app.services.pagamenti_mensilita import indice_coperture, stato_copertura, periodi_saldati
    tutte_prove = await db["pagamenti_esiti"].find({}, {"_id": 0, "pdf_data": 0, "file_data": 0}).to_list(None)
    for e in tutte_prove:
        if periodi_saldati(e):
            continue
        k = (e.get("dipendente_id"), e.get("anno"), e.get("mese"))
        esiti_idx[k] = round((esiti_idx.get(k) or 0) + (_num(e.get("importo")) or 0), 2)
        prove_idx.setdefault(k, []).append({campo: e.get(campo) for campo in (
            "associazione_certa", "origine", "gestionale_movimento_id",
            "dipendente_id", "confermato_manuale", "competenza_confermata")})

    coperture = indice_coperture(tutte_prove)
    # Prefetch di paghe_mensili in blocco: l'adattatore Supabase non ha indici,
    # un find_one per cedolino (fino a 3000) su una tabella che cresce ad ogni
    # giro dentro lo stesso ciclo e' un O(N^2) che porta la sincronizzazione a
    # decine di secondi e puo' far scadere la richiesta (502). Si legge una
    # volta sola e si indicizza in memoria.
    esistenti_idx: Dict[tuple, Dict[str, Any]] = {}
    async for p in db["paghe_mensili"].find({}, {"_id": 0}):
        esistenti_idx[(p.get("dipendente_id"), p.get("anno"), p.get("mese"))] = p

    # Acconti del registro unico, letti una volta: sono pagamenti sulla busta come
    # per la posizione dipendente e per `_ricalcola_stato_paga` (stesso conto).
    acconti_per_dip: Dict[Any, list] = {}
    async for a in db["acconti_dipendenti"].find({}, {"_id": 0}):
        acconti_per_dip.setdefault(a.get("dipendente_id"), []).append(a)

    dipendenti_idx: Dict[Any, Dict[str, Any]] = {}
    async for d in db["dipendenti"].find(
            {}, {"_id": 0, "id": 1, "stato": 1, "attivo": 1, "in_carico": 1,
                 "data_fine_rapporto": 1, "data_cessazione": 1,
                 "data_dimissione": 1, "data_cessazione_prevista": 1}):
        dipendenti_idx[d.get("id")] = d

    adesso = datetime.now(timezone.utc).isoformat()
    creati = aggiornati = saltati_manuali = invariati = 0

    for c in cedolini:
        dip, anno_c = c["dipendente_id"], int(c["anno"])
        mese_competenza = int(c["mese"])
        mese_c = _mese_registro(c)
        esistente = esistenti_idx.get((dip, anno_c, mese_c))
        netto_confermato = (esistente or {}).get("netto_confermato")
        if esistente and esistente.get("origine") not in (None, "cedolino") and netto_confermato is None:
            saltati_manuali += 1
            continue

        componenti = c.get("cedolini_componenti") or [c]
        bon = list({b.get("id") or str(b): b for part in componenti
                    for b in per_cedolino.get(part.get("id"), [])}.values())
        bonifico_importo = round(sum(_num(b.get("importo")) or 0 for b in bon), 2)
        bonifico_data = max((b.get("data") for b in bon), default=None)
        # pagamenti_esiti e' la fonte autorevole quando presente (copre anche i
        # bonifici senza cedolino_id): vince su quella derivata da `bonifici`.
        tot_esiti = esiti_idx.get((dip, anno_c, mese_c))
        if tot_esiti is not None:
            bonifico_importo = tot_esiti
        prove = prove_idx.get((dip, anno_c, mese_c), bon)
        riconciliato_auto = esiti_riconciliati(prove)
        riconciliato = (esistente or {}).get("bonifico_riconciliato") is True or esiti_confermati(prove)

        dovuto = dovuto_busta(esistente if netto_confermato is not None else {}, c)
        importo_dovuto = float(dovuto["dovuto"]) if dovuto["dovuto"] is not None else None

        doc = {
            "dipendente_id": dip, "anno": anno_c, "mese": mese_c,
            "mese_competenza": mese_competenza,
            "tipo_cedolino": str(c.get("tipo_cedolino") or "ordinario").strip().lower(),
            "importo_busta": importo_dovuto,
            "netto_stampato": float(dovuto["netto_busta"]) if dovuto["netto_busta"] is not None else None,
            "acconto_recuperato": float(dovuto["acconto"]),
            "dovuto_periodo": importo_dovuto,
            "bonifico_ricevuto": bonifico_importo > 0 and bool(prove) and all(ha_riscontro_bancario(e) for e in prove),
            "bonifico_riconciliato_auto": riconciliato_auto,
            "bonifico_importo": bonifico_importo or None,
            "pagamenti_copertura": [],
            "bonifico_data": bonifico_data,
            "acconti": esistente.get("acconti", []) if esistente else [],
            "giorni_lavorati": c.get("giorni_lavorati"),
            "acconto_da_cedolino": float(dovuto["acconto"]),
            "livello": c.get("livello"),
            "cedolino_id": c.get("id"),
            "cedolino_ids": [part["id"] for part in componenti if part.get("id")],
            "origine": "excel_cedolino" if netto_confermato is not None else "cedolino",
            "updated_at": adesso,
        }
        in_busta, _ = filtra_acconti_contanti(
            dipendenti_idx.get(dip, {}), (esistente or {}).get("acconti") or [])
        acconti_pagati = (sum(_num(a.get("importo")) or 0 for a in in_busta)
                          + float(acconti_registro_del_mese(acconti_per_dip.get(dip, []), anno_c, mese_c, in_busta)))
        doc.update(_stato_e_saldo(importo_dovuto, round(bonifico_importo + acconti_pagati, 2),
                                 bonifico=bonifico_importo, riconciliato=riconciliato))
        if prove := coperture.get((dip, anno_c, mese_c)):
            doc.update(stato_copertura(prove))
        doc = {k: v for k, v in doc.items() if v is not None or k in ("acconti", "importo_busta", "netto_stampato", "dovuto_periodo", "saldo", "bonifico_importo", "bonifico_data")}

        if esistente and all(esistente.get(k) == v for k, v in doc.items() if k != "updated_at"):
            invariati += 1
            continue

        await db["paghe_mensili"].update_one(
            {"dipendente_id": dip, "anno": anno_c, "mese": mese_c}, {"$set": doc}, upsert=True)
        if esistente:
            aggiornati += 1
        else:
            creati += 1
        esistenti_idx[(dip, anno_c, mese_c)] = {**(esistente or {}), **doc}

    return {"cedolini_considerati": len(cedolini), "creati": creati,
            "aggiornati": aggiornati, "saltati_manuali": saltati_manuali, "invariati": invariati}
