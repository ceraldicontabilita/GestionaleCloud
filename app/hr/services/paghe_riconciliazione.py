"""
Servizio di Riconciliazione Automatica Paghe
============================================
Riconcilia stipendi e F24 con i movimenti bancari importati.
Ricerca sia in `prima_nota_banca` (Prima Nota) che in `estratto_conto_movimenti` (estratto conto).

Viene chiamato automaticamente al caricamento dell'estratto conto bancario.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


async def cerca_in_estratto_conto(
    db,
    importo_uscita: float,
    data_ref_str: str,
    giorni_tolleranza: int = 10,
    keywords_descrizione: Optional[list] = None
) -> Optional[Tuple[str, str]]:
    """
    Cerca un pagamento in uscita nell'estratto conto movimenti.
    Ritorna (id, collection) se trovato, altrimenti None.
    
    In `estratto_conto_movimenti`: importo è NEGATIVO per le uscite.
    In `prima_nota_banca`: importo è POSITIVO, tipo = "uscita".
    """
    try:
        data_ref = datetime.strptime(data_ref_str, "%Y-%m-%d")
        data_min = (data_ref - timedelta(days=giorni_tolleranza)).strftime("%Y-%m-%d")
        data_max = (data_ref + timedelta(days=giorni_tolleranza // 2)).strftime("%Y-%m-%d")
        
        # ---- 1. Cerca in estratto_conto_movimenti (importo negativo) ----
        query_ecm = {
            "importo": {"$gte": -(importo_uscita + 1.0), "$lte": -(importo_uscita - 1.0)},
            "data": {"$gte": data_min, "$lte": data_max},
            "riconciliato_paghe": {"$ne": True}
        }
        
        if keywords_descrizione:
            regex = "|".join(keywords_descrizione)
            query_ecm_kw = {**query_ecm, "descrizione_originale": {"$regex": regex, "$options": "i"}}
            mov = await db.estratto_conto_movimenti.find_one(query_ecm_kw)
            if mov:
                return (str(mov.get("id", str(mov.get("_id", "")))), "estratto_conto_movimenti")
        
        mov = await db.estratto_conto_movimenti.find_one(query_ecm)
        if mov:
            return (str(mov.get("id", str(mov.get("_id", "")))), "estratto_conto_movimenti")
        
        # ---- 2. Cerca in prima_nota_banca (importo positivo, tipo uscita) ----
        query_pnb = {
            "tipo": "uscita",
            "importo": {"$gte": importo_uscita - 1.0, "$lte": importo_uscita + 1.0},
            "data": {"$gte": data_min, "$lte": data_max},
            "riconciliato_paghe": {"$ne": True}
        }
        
        if keywords_descrizione:
            regex = "|".join(keywords_descrizione)
            query_pnb_kw = {**query_pnb, "descrizione": {"$regex": regex, "$options": "i"}}
            mov = await db.prima_nota_banca.find_one(query_pnb_kw)
            if mov:
                return (str(mov.get("id", str(mov.get("_id", "")))), "prima_nota_banca")
        
        mov = await db.prima_nota_banca.find_one(query_pnb)
        if mov:
            return (str(mov.get("id", str(mov.get("_id", "")))), "prima_nota_banca")
        
        return None
    except Exception as e:
        logger.warning(f"Errore ricerca bancaria importo={importo_uscita}: {e}")
        return None


async def marca_movimento_riconciliato(
    db, mov_id: str, collection: str,
    campo: str, documento_id: str
):
    """Marca un movimento bancario come riconciliato con un documento paghe."""
    try:
        update = {
            "riconciliato_paghe": True,
            f"documento_{campo}_id": documento_id,
            "data_riconciliazione_paghe": datetime.now(timezone.utc).isoformat()
        }
        await db[collection].update_one({"id": mov_id}, {"$set": update})
        # Anche per id ObjectId se necessario
        if not mov_id.startswith("EC-") and len(mov_id) < 30:
            pass
    except Exception as e:
        logger.warning(f"Errore marcatura movimento {mov_id}: {e}")


async def riconcilia_tutti_stipendi(db, anno: int = None, mese: int = None) -> dict:
    """
    Riconcilia tutti gli stipendi DA_PAGARE con i movimenti bancari.
    Chiamato automaticamente dopo import estratto conto.
    """
    # netto_mese >= 50: sotto quella soglia è quasi certo un valore mal estratto dal
    # parser PDF (pagina, aliquota, trattenuta isolata) e non un vero netto in busta —
    # va corretto a monte, non riconciliato con la banca.
    query = {"stato_pagamento": "DA_PAGARE", "netto_mese": {"$gte": 50}}
    if anno and mese:
        query["periodo"] = f"{anno:04d}-{mese:02d}"
    
    buste = await db.buste_paga.find(query, {"_id": 0}).to_list(length=500)
    
    riconciliati = 0
    non_trovati = 0
    
    for busta in buste:
        cf = busta.get("codice_fiscale", "")
        netto = busta.get("netto_mese", 0)
        periodo_iso = busta.get("periodo", "")
        busta_id = busta.get("busta_id", f"bp_{cf}_{periodo_iso}")
        cognome_nome = busta.get("dipendente_nome", "")
        
        # Ricostruisci data scadenza
        try:
            import calendar
            anno_p, mese_p = map(int, periodo_iso.split("-"))
            ultimo_giorno = calendar.monthrange(anno_p, mese_p)[1]
            data_scad = f"{anno_p:04d}-{mese_p:02d}-{ultimo_giorno:02d}"
        except (ValueError, AttributeError):
            continue
        
        # Keywords: cognome o "STIPENDIO"
        keywords = ["STIPENDIO", "CEDOLINO"]
        if cognome_nome:
            cognome = cognome_nome.split()[0]
            if len(cognome) > 3:
                keywords.append(cognome.upper())
        
        result = await cerca_in_estratto_conto(
            db, netto, data_scad,
            giorni_tolleranza=10,
            keywords_descrizione=keywords
        )
        
        if result:
            mov_id, collection = result
            now_iso = datetime.now(timezone.utc).isoformat()
            
            await db.buste_paga.update_one(
                {"codice_fiscale": cf, "periodo": periodo_iso},
                {"$set": {
                    "stato_pagamento": "PAGATO",
                    "data_pagamento": now_iso,
                    "movimento_bancario_id": mov_id,
                    "movimento_collection": collection
                }}
            )
            await db.scadenze.update_one(
                {"documento_id": busta_id},
                {"$set": {"completata": True}}
            )
            await marca_movimento_riconciliato(db, mov_id, collection, "stipendio", busta_id)
            riconciliati += 1
        else:
            non_trovati += 1
    
    logger.info(f"Riconciliazione stipendi: {riconciliati} saldati, {non_trovati} da saldare")
    return {
        "totale_analizzati": len(buste),
        "riconciliati": riconciliati,
        "non_trovati": non_trovati
    }


async def riconcilia_tutti_f24(db, anno: int = None) -> dict:
    """
    Riconcilia tutti gli F24 DA_PAGARE con i movimenti bancari.
    Chiamato automaticamente dopo import estratto conto.
    """
    query = {"stato": "DA_PAGARE", "totale_da_pagare": {"$gt": 0}}
    if anno:
        query["scadenza"] = {"$regex": str(anno)}
    
    f24_list = await db.f24_pagamenti.find(query, {"_id": 0}).to_list(length=200)
    
    riconciliati = 0
    non_trovati = 0
    
    for f24 in f24_list:
        f24_id = f24.get("f24_id", "")
        totale = f24.get("totale_da_pagare", 0)
        scadenza = f24.get("scadenza", "")
        distinta_id = f"dist_{f24_id}"
        
        # Calcola data scadenza ISO
        data_scad_iso = None
        try:
            if scadenza and "/" in scadenza:
                if len(scadenza) == 10:  # DD/MM/YYYY
                    data_scad_iso = datetime.strptime(scadenza, "%d/%m/%Y").strftime("%Y-%m-%d")
                elif len(scadenza) == 7:  # MM/YYYY
                    mm, yyyy = scadenza.split("/")
                    data_scad_iso = f"{yyyy}-{mm.zfill(2)}-16"
        except (ValueError, TypeError):
            continue
        
        if not data_scad_iso:
            continue
        
        keywords = ["F24", "ERARIO", "INPS", "AGENZIA", "ENTRATE", "TRIBUT"]
        
        result = await cerca_in_estratto_conto(
            db, totale, data_scad_iso,
            giorni_tolleranza=7,
            keywords_descrizione=keywords
        )
        
        if result:
            mov_id, collection = result
            now_iso = datetime.now(timezone.utc).isoformat()
            
            await db.f24_pagamenti.update_one(
                {"f24_id": f24_id},
                {"$set": {
                    "stato": "PAGATO",
                    "data_pagamento": now_iso,
                    "movimento_bancario_id": mov_id,
                    "riconciliato": True
                }}
            )
            await db.tributi_pagati.update_many(
                {"f24_id": f24_id},
                {"$set": {"stato": "PAGATO", "data_pagamento": now_iso}}
            )
            await db.distinte_f24.update_one(
                {"distinta_id": distinta_id},
                {"$set": {"stato": "PAGATO", "data_pagamento": now_iso, "movimento_bancario_id": mov_id}}
            )
            await db.scadenze.update_one(
                {"documento_id": f24_id},
                {"$set": {"completata": True}}
            )
            await marca_movimento_riconciliato(db, mov_id, collection, "f24", f24_id)
            riconciliati += 1
        else:
            non_trovati += 1
    
    logger.info(f"Riconciliazione F24: {riconciliati} pagati, {non_trovati} da pagare")
    return {
        "totale_analizzati": len(f24_list),
        "riconciliati": riconciliati,
        "non_trovati": non_trovati
    }


async def esegui_riconciliazione_paghe_completa(db) -> dict:
    """
    Entry point principale: riconcilia TUTTI i documenti paghe pendenti.
    Chiamato automaticamente dopo ogni import di estratto conto bancario.
    """
    try:
        stipendi_result = await riconcilia_tutti_stipendi(db)
        f24_result = await riconcilia_tutti_f24(db)
        
        return {
            "stipendi": stipendi_result,
            "f24": f24_result,
            "totale_riconciliati": stipendi_result["riconciliati"] + f24_result["riconciliati"]
        }
    except Exception as e:
        logger.error(f"Errore riconciliazione paghe completa: {e}")
        return {"error": str(e)}
