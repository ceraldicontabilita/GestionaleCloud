"""
Prima Nota Module - Manutenzione e Fix.
Funzioni di fix, cleanup, recalculate per manutenzione dati.
"""
from fastapi import HTTPException, Query, Body, Depends
from app.utils.dependencies import get_current_admin_user
from pydantic import BaseModel
from typing import Dict, Optional, Any
from datetime import datetime, timezone
import uuid

from app.database import Database
from .common import (
    COLLECTION_PRIMA_NOTA_CASSA, COLLECTION_PRIMA_NOTA_BANCA, logger,
    CATEGORIE_ESCLUSE, ESCLUSIONI_PRIMA_NOTA, aggrega_saldo_prima_nota,
)
from .sync import determina_tipo_movimento_fattura

# Collection estratto conto bancario (non esportata da .common, la definisco qui)
COLLECTION_ESTRATTO_CONTO = "estratto_conto_movimenti"


class SpostaMovimentoRequest(BaseModel):
    movimento_id: str
    da: str
    a: str


async def fix_tipo_movimento_fatture() -> Dict:
    """Corregge il tipo movimento per tutti i movimenti collegati a fatture."""
    db = Database.get_db()
    
    fixed_cassa = 0
    fixed_banca = 0
    errors = []
    
    for collection, fixed_counter in [(COLLECTION_PRIMA_NOTA_CASSA, "cassa"), (COLLECTION_PRIMA_NOTA_BANCA, "banca")]:
        movimenti = await db[collection].find(
            {"fattura_id": {"$exists": True, "$ne": None}},
            {"_id": 0}
        ).to_list(10000)
        
        for mov in movimenti:
            try:
                fattura_id = mov.get("fattura_id")
                if not fattura_id:
                    continue
                
                fattura = await db["invoices"].find_one(
                    {"$or": [{"id": fattura_id}, {"invoice_key": fattura_id}]},
                    {"_id": 0}
                )
                
                if not fattura:
                    continue
                
                tipo_corretto, categoria_corretta, _ = determina_tipo_movimento_fattura(fattura)
                
                if mov.get("tipo") != tipo_corretto or mov.get("categoria") != categoria_corretta:
                    await db[collection].update_one(
                        {"id": mov["id"]},
                        {"$set": {
                            "tipo": tipo_corretto,
                            "categoria": categoria_corretta,
                            "tipo_documento": fattura.get("tipo_documento"),
                            "fixed_at": datetime.now(timezone.utc).isoformat()
                        }}
                    )
                    if fixed_counter == "cassa":
                        fixed_cassa += 1
                    else:
                        fixed_banca += 1
                    logger.info(f"Fixed {fixed_counter} {mov['id']}: {mov.get('tipo')} -> {tipo_corretto}")
                    
            except Exception as e:
                errors.append(f"{fixed_counter} {mov.get('id')}: {str(e)}")
    
    return {
        "success": True,
        "message": f"Corretti {fixed_cassa} movimenti cassa e {fixed_banca} movimenti banca",
        "fixed_cassa": fixed_cassa,
        "fixed_banca": fixed_banca,
        "errors": errors[:20]
    }


async def recalculate_all_balances(anno: Optional[int] = Query(None)) -> Dict:
    """Ricalcola i saldi di Prima Nota Cassa e Banca."""
    db = Database.get_db()
    
    # §6.4: stessa funzione/engine di cassa/banca/stats (filtri ed esclusioni uniformi).
    query = {
        "status": {"$nin": ["deleted", "archived"]},
        **ESCLUSIONI_PRIMA_NOTA,
    }
    if anno:
        query["data"] = {"$regex": f"^{anno}"}

    s_cassa = await aggrega_saldo_prima_nota(db, COLLECTION_PRIMA_NOTA_CASSA, query, anno=None)
    s_banca = await aggrega_saldo_prima_nota(db, COLLECTION_PRIMA_NOTA_BANCA, query, anno=None)
    cassa = {"entrate": s_cassa["totale_entrate"], "uscite": s_cassa["totale_uscite"],
             "count": await db[COLLECTION_PRIMA_NOTA_CASSA].count_documents(query)}
    banca = {"entrate": s_banca["totale_entrate"], "uscite": s_banca["totale_uscite"],
             "count": await db[COLLECTION_PRIMA_NOTA_BANCA].count_documents(query)}

    saldo_cassa = s_cassa["saldo_anno"]
    saldo_banca = s_banca["saldo_anno"]
    
    return {
        "anno": anno or "tutti",
        "cassa": {
            "entrate": round(cassa.get("entrate", 0), 2),
            "uscite": round(cassa.get("uscite", 0), 2),
            "saldo": round(saldo_cassa, 2),
            "movimenti": cassa.get("count", 0)
        },
        "banca": {
            "entrate": round(banca.get("entrate", 0), 2),
            "uscite": round(banca.get("uscite", 0), 2),
            "saldo": round(saldo_banca, 2),
            "movimenti": banca.get("count", 0)
        },
        "totale": {
            "saldo": round(saldo_cassa + saldo_banca, 2),
            "entrate": round(cassa.get("entrate", 0) + banca.get("entrate", 0), 2),
            "uscite": round(cassa.get("uscite", 0) + banca.get("uscite", 0), 2)
        }
    }


async def cleanup_orphan_movements(anno: Optional[int] = Query(None), _admin: Dict = Depends(get_current_admin_user)) -> Dict:
    """Pulisce i movimenti Prima Nota orfani (fattura inesistente)."""
    db = Database.get_db()
    
    query = {"fattura_id": {"$exists": True, "$ne": None}}
    if anno:
        query["data"] = {"$regex": f"^{anno}"}
    
    orphan_cassa = 0
    orphan_banca = 0
    
    for collection, counter_name in [(COLLECTION_PRIMA_NOTA_CASSA, "cassa"), (COLLECTION_PRIMA_NOTA_BANCA, "banca")]:
        movimenti = await db[collection].find(query, {"_id": 0, "id": 1, "fattura_id": 1}).to_list(10000)
        for mov in movimenti:
            fattura_id = mov.get("fattura_id")
            if fattura_id:
                fattura = await db["invoices"].find_one(
                    {"$or": [{"id": fattura_id}, {"invoice_key": fattura_id}]},
                    {"_id": 1}
                )
                if not fattura:
                    await db[collection].delete_one({"id": mov["id"]})
                    if counter_name == "cassa":
                        orphan_cassa += 1
                    else:
                        orphan_banca += 1
    
    return {
        "success": True,
        "message": f"Eliminati {orphan_cassa} movimenti cassa orfani e {orphan_banca} movimenti banca orfani",
        "orphan_cassa_deleted": orphan_cassa,
        "orphan_banca_deleted": orphan_banca,
        "anno_filtro": anno
    }


async def regenerate_from_invoices(anno: int = Query(...)) -> Dict:
    """Rigenera i movimenti Prima Nota dall'archivio fatture per un anno."""
    db = Database.get_db()
    
    query_delete = {
        "data": {"$regex": f"^{anno}"},
        "source": {"$in": ["fattura_pagata", "fatture_import", "xml_upload"]}
    }
    
    deleted_cassa = await db[COLLECTION_PRIMA_NOTA_CASSA].delete_many(query_delete)
    deleted_banca = await db[COLLECTION_PRIMA_NOTA_BANCA].delete_many(query_delete)
    
    fatture = await db["invoices"].find(
        {"invoice_date": {"$regex": f"^{anno}"}},
        {"_id": 0}
    ).to_list(10000)
    
    created_cassa = 0
    created_banca = 0
    errors = []
    
    for fattura in fatture:
        try:
            metodo = fattura.get("metodo_pagamento", "bonifico")
            tipo_movimento, categoria, desc_prefisso = determina_tipo_movimento_fattura(fattura)
            
            data_fattura = fattura.get("invoice_date") or fattura.get("data_fattura")
            importo = float(fattura.get("total_amount", 0) or fattura.get("importo_totale", 0) or 0)
            numero_fattura = fattura.get("invoice_number") or fattura.get("numero_fattura") or "N/A"
            fornitore = fattura.get("supplier_name") or fattura.get("cedente_denominazione") or "Fornitore"
            fornitore_piva = fattura.get("supplier_vat") or fattura.get("cedente_piva") or ""
            
            if importo <= 0:
                continue
            
            movimento = {
                "id": str(uuid.uuid4()),
                "data": data_fattura,
                "tipo": tipo_movimento,
                "importo": importo,
                "descrizione": f"{desc_prefisso} {numero_fattura} - {fornitore[:40]}",
                "categoria": categoria,
                "riferimento": numero_fattura,
                "fornitore_piva": fornitore_piva,
                "fattura_id": fattura.get("id"),
                "tipo_documento": fattura.get("tipo_documento"),
                "source": "fatture_import",
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            if metodo in ["cassa", "contanti"]:
                await db[COLLECTION_PRIMA_NOTA_CASSA].insert_one(movimento.copy())
                created_cassa += 1
            else:
                await db[COLLECTION_PRIMA_NOTA_BANCA].insert_one(movimento.copy())
                created_banca += 1
                
        except Exception as e:
            errors.append(f"Fattura {fattura.get('invoice_number', 'N/A')}: {str(e)}")
    
    return {
        "success": True,
        "anno": anno,
        "fatture_elaborate": len(fatture),
        "movimenti_cassa_creati": created_cassa,
        "movimenti_banca_creati": created_banca,
        "movimenti_cassa_eliminati": deleted_cassa.deleted_count,
        "movimenti_banca_eliminati": deleted_banca.deleted_count,
        "errors": errors[:20]
    }


async def fix_versamenti_duplicati(anno: Optional[int] = Query(None)) -> Dict:
    """Rimuove i versamenti duplicati con importo errato."""
    db = Database.get_db()
    
    query = {"categoria": {"$in": ["Versamento", "Versamento Banca"]}}
    if anno:
        query["data"] = {"$regex": f"^{anno}"}
    
    versamenti_cassa = await db[COLLECTION_PRIMA_NOTA_CASSA].find(query, {"_id": 0}).to_list(10000)
    
    datetime_format = []
    date_format = []
    
    for v in versamenti_cassa:
        data = v.get("data", "")
        if " " in data:
            datetime_format.append(v)
        else:
            date_format.append(v)
    
    removed = 0
    for v in date_format:
        data_solo = v.get("data", "")[:10]
        corresponding = [d for d in datetime_format if d.get("data", "")[:10] == data_solo]
        
        if corresponding:
            await db[COLLECTION_PRIMA_NOTA_CASSA].delete_one({"id": v["id"]})
            removed += 1
    
    for v in datetime_format:
        data = v.get("data", "")
        if " " in data:
            await db[COLLECTION_PRIMA_NOTA_CASSA].update_one(
                {"id": v["id"]},
                {"$set": {"data": data[:10]}}
            )
    
    return {
        "success": True,
        "anno": anno,
        "versamenti_datetime": len(datetime_format),
        "versamenti_date": len(date_format),
        "duplicati_rimossi": removed,
        "message": f"Rimossi {removed} versamenti duplicati con importo errato"
    }


# Regola utente 16/07/2026: in contabilità devono restare SOLO i dati
# dall'anno operativo in poi (2026) — i movimenti/fatture/corrispettivi di
# anni vecchi (2021-2022, residui di backfill e import storici) falsavano
# riporti e saldi. Collection ripulite e campi data usati per stabilire
# l'anno del documento (in ordine di priorità; un documento senza nessuna
# data riconoscibile NON viene mai eliminato).
COLLEZIONI_PULIZIA_PRE_ANNO = {
    "prima_nota_cassa": ["data"],
    "prima_nota_banca": ["data"],
    "prima_nota_salari": ["data"],
    "corrispettivi": ["data"],
    "invoices": ["invoice_date", "data_fattura", "data_ricezione"],
    "fatture_emesse": ["invoice_date", "data_emissione"],
    "estratto_conto_movimenti": ["data_contabile", "data"],
    "movimenti_contabili": ["data"],
    "partite_aperte": ["data_documento", "data"],
}


def _estrai_anno(valore) -> Optional[int]:
    """Anno da una data stringa ISO (YYYY-...) o italiana (GG/MM/AAAA)."""
    s = str(valore or "")
    if len(s) >= 4 and s[:4].isdigit():
        return int(s[:4])
    if "/" in s:
        coda = s.split("/")[-1][:4]
        if len(coda) == 4 and coda.isdigit():
            return int(coda)
    return None


async def pulizia_dati_pre_anno(
    anno_da_mantenere: int = Query(2026, description="Primo anno da MANTENERE"),
    dry_run: bool = Query(True, description="Solo conteggio, non elimina"),
    _admin: Dict = Depends(get_current_admin_user),
) -> Dict:
    """Elimina da tutte le collection operative i documenti con data
    anteriore ad anno_da_mantenere. Con dry_run=true (default) restituisce
    solo i conteggi per collection/anno, senza toccare nulla."""
    db = Database.get_db()
    report = {}
    totale_eliminati = 0

    for collection, campi_data in COLLEZIONI_PULIZIA_PRE_ANNO.items():
        proiezione = {"_id": 0, "id": 1, **{c: 1 for c in campi_data}}
        docs = await db[collection].find({}, proiezione).to_list(200000)
        da_eliminare = []
        per_anno: Dict[int, int] = {}
        for d in docs:
            anno_doc = None
            for campo in campi_data:
                anno_doc = _estrai_anno(d.get(campo))
                if anno_doc is not None:
                    break
            if anno_doc is not None and anno_doc < anno_da_mantenere and d.get("id"):
                da_eliminare.append(d["id"])
                per_anno[anno_doc] = per_anno.get(anno_doc, 0) + 1

        eliminati = 0
        if da_eliminare and not dry_run:
            for i in range(0, len(da_eliminare), 500):
                r = await db[collection].delete_many({"id": {"$in": da_eliminare[i:i + 500]}})
                eliminati += r.deleted_count
        report[collection] = {
            "trovati_pre_anno": len(da_eliminare),
            "per_anno": {str(k): v for k, v in sorted(per_anno.items())},
            "eliminati": eliminati if not dry_run else 0,
        }
        totale_eliminati += eliminati

    return {
        "dry_run": dry_run,
        "anno_da_mantenere": anno_da_mantenere,
        "collections": report,
        "totale_eliminati": totale_eliminati,
    }


# Unificazione categorie (richiesta utente 17/07/2026, screenshot del filtro
# con 8 nomi diversi): un solo nome per concetto. Regole di rinomina, in
# ordine di applicazione: (collection, filtro, nuova categoria).
REGOLE_UNIFICA_CATEGORIE = [
    # Pagamenti fatture fornitori → "Fatture" (il nome già usato dal 90%)
    ("prima_nota_cassa", {"categoria": {"$in": ["Pagamento fornitore", "Fornitori", "fornitori"]}}, "Fatture"),
    ("prima_nota_banca", {"categoria": {"$in": ["Pagamento fornitore", "Fornitori", "fornitori"]}}, "Fatture"),
    # Contanti da cassa a banca → "Versamento Banca"
    ("prima_nota_cassa", {"categoria": "Versamento", "tipo": "uscita"}, "Versamento Banca"),
    ("prima_nota_banca", {"categoria": "Versamento", "tipo": "entrata"}, "Versamento Banca"),
    ("prima_nota_banca", {"categoria": "trasferimento_interno", "tipo": "entrata"}, "Versamento Banca"),
    # Contanti da banca a cassa → "Prelevamento Banca" (prelievi)
    ("prima_nota_cassa", {"categoria": {"$in": ["trasferimento_interno", "Prelievo"]}, "tipo": "entrata"}, "Prelevamento Banca"),
    ("prima_nota_banca", {"categoria": {"$in": ["trasferimento_interno", "Prelievo"]}, "tipo": "uscita"}, "Prelevamento Banca"),
]


# Fonti AUTOMATICHE dei movimenti fattura: solo queste possono essere
# rimesse in discussione dalla riparazione per metodo — le registrazioni
# fatte A MANO dall'utente (conferma dal tab Provvisori, pagamento manuale)
# e quelle agganciate a un addebito REALE dell'estratto conto
# (riconciliazione_ec: il denaro è uscito davvero dal conto) non si toccano.
SOURCES_FATTURE_AUTO = [
    "auto_conferma", "sync_fatture", "backfill_auto_da_fornitore",
    "auto_metodo", "fix_relazioni", "auto_registrazione_metodo_fornitore",
    # sfuggite al primo giro (18/07, caso TOP SPINA 4853/01): altre
    # scritture automatiche di vecchie pipeline
    "auto_import", "sync_fatture_banca", "auto_confirm_provvisoria",
]


async def ripristina_provvisori_metodo_errato(
    dry_run: bool = Query(True, description="Solo conteggio, non modifica"),
    anno: int = Query(2026),
    banca_non_riconciliate: bool = Query(False, description=(
        "REGOLA utente 18/07/2026: una fattura 'banca' e' pagata SOLO se "
        "riconciliata con estratto conto/PayPal/carta. Con true, TUTTE le "
        "uscite fattura banca auto MAI riconciliate tornano provvisorie.")),
    _admin: Dict = Depends(get_current_admin_user),
) -> Dict:
    """Richiesta utente 17/07/2026: "abbiamo fornitori che si pagano per
    cassa e li ha messi in banca — tutti quelli devi mettere nei provvisori".

    Per ogni movimento fattura creato AUTOMATICAMENTE, confronta il lato
    (cassa/banca) con il metodo del fornitore in anagrafica
    (classifica_metodo_fornitore, la stessa regola di tutto il resto):
    - fornitore CASSA ma movimento in BANCA → lato sbagliato
    - fornitore BANCA ma movimento in CASSA → lato sbagliato
    - fornitore MISTO/senza metodo → non doveva essere registrato da solo
    In tutti i casi il movimento viene marcato deleted (soft, recuperabile)
    e la fattura torna NON pagata: ricompare nei Provvisori con il
    suggerimento giusto, e decide l'utente."""
    from .sync import classifica_metodo_fornitore

    db = Database.get_db()

    metodo_per_piva: Dict[str, str] = {}
    async for s in db["fornitori"].find(
        {"metodo_pagamento": {"$exists": True, "$ne": ""}},
        {"_id": 0, "partita_iva": 1, "piva": 1, "vat_number": 1, "metodo_pagamento": 1},
    ):
        for k in (s.get("partita_iva"), s.get("piva"), s.get("vat_number")):
            if k:
                metodo_per_piva[str(k).strip()] = s.get("metodo_pagamento", "")

    report = {"banca": [], "cassa": []}
    corretti = 0

    for collection, lato in ((COLLECTION_PRIMA_NOTA_BANCA, "banca"), (COLLECTION_PRIMA_NOTA_CASSA, "cassa")):
        movimenti = await db[collection].find(
            {
                "tipo": "uscita",
                # anche le righe legacy con fattura_id vuoto ma riferimento
                # FATT-<id> (vecchio sync_fatture): la fattura si ricava dal
                # riferimento — prima sfuggivano alla riparazione (caso ABC
                # 19/03, riga superstite segnalata dall'utente 18/07).
                "$or": [
                    {"fattura_id": {"$nin": [None, ""]}},
                    {"riferimento": {"$regex": "^FATT-"}},
                ],
                "source": {"$in": SOURCES_FATTURE_AUTO},
                "status": {"$nin": ["deleted", "archived"]},
                "data": {"$regex": f"^{anno}"},
            },
            {"_id": 0, "id": 1, "fattura_id": 1, "riferimento": 1, "importo": 1, "data": 1,
             "descrizione": 1, "source": 1, "riconciliato": 1, "estratto_conto_id": 1},
        ).to_list(20000)

        for mov in movimenti:
            fid = mov.get("fattura_id") or (mov.get("riferimento") or "")[5:]
            mov["fattura_id"] = fid
            fattura = await db["invoices"].find_one(
                {"id": fid},
                {"_id": 0, "supplier_vat": 1, "cedente_piva": 1, "invoice_number": 1, "supplier_name": 1},
            )
            if not fattura:
                # Movimento ORFANO: la fattura collegata non esiste più in
                # archivio — un pagamento automatico senza documento non ha
                # ragione di restare nei saldi (caso FLA 4-FE, 02/01/2026).
                report[lato].append({
                    "fattura": "(fattura inesistente)",
                    "fornitore": (mov.get("descrizione") or "")[:40],
                    "importo": mov.get("importo"),
                    "data": mov.get("data"),
                    "metodo_fornitore": "-",
                    "destinazione_giusta": "eliminato (orfano)",
                })
                corretti += 1
                if not dry_run:
                    await db[collection].update_one(
                        {"id": mov["id"]},
                        {"$set": {"status": "deleted",
                                  "deleted_reason": "movimento_auto_orfano_senza_fattura"}},
                    )
                continue
            piva = str(fattura.get("supplier_vat") or fattura.get("cedente_piva") or "").strip()
            destinazione = classifica_metodo_fornitore(metodo_per_piva.get(piva, ""))
            senza_riconciliazione = (
                banca_non_riconciliate and lato == "banca"
                and not mov.get("riconciliato") and not mov.get("estratto_conto_id")
            )
            if destinazione == lato and not senza_riconciliazione:
                continue  # lato giusto (e riconciliata, se richiesto): non si tocca
            if destinazione == lato and senza_riconciliazione:
                destinazione = "provvisoria (in attesa di riconciliazione)"

            report[lato].append({
                "fattura": fattura.get("invoice_number"),
                "fornitore": (fattura.get("supplier_name") or "")[:40],
                "importo": mov.get("importo"),
                "data": mov.get("data"),
                "metodo_fornitore": metodo_per_piva.get(piva, "(nessuno)"),
                "destinazione_giusta": destinazione,
            })
            corretti += 1
            if dry_run:
                continue

            await db[collection].update_one(
                {"id": mov["id"]},
                {"$set": {"status": "deleted",
                          "deleted_reason": "lato_errato_vs_metodo_fornitore"}},
            )
            await db["invoices"].update_one(
                {"id": mov["fattura_id"]},
                {"$set": {"pagato": False, "stato_pagamento": "da_pagare",
                          "prima_nota_id": None, "prima_nota_tipo": None},
                 "$unset": {"registrata_auto_da_metodo_fornitore": ""}},
            )

    # ── Un addebito reale = UNA riga (caso TOP SPINA 05/01, triplo conteggio) ──
    # 1) Due o più righe banca agganciate alla STESSA riga di estratto conto:
    #    lo stesso denaro uscito una volta sola contato più volte. Resta la
    #    più vecchia; le altre tornano provvisorie (il loro pagamento reale
    #    non è stato trovato).
    doppioni_stesso_addebito = 0
    righe_ec = await db[COLLECTION_PRIMA_NOTA_BANCA].find(
        {"tipo": "uscita", "estratto_conto_id": {"$nin": [None, ""]},
         "status": {"$nin": ["deleted", "archived"]}, "data": {"$regex": f"^{anno}"}},
        {"_id": 0, "id": 1, "estratto_conto_id": 1, "fattura_id": 1, "created_at": 1},
    ).to_list(20000)
    per_ec: Dict[str, list] = {}
    for r in righe_ec:
        per_ec.setdefault(r["estratto_conto_id"], []).append(r)
    for gruppo in per_ec.values():
        if len(gruppo) <= 1:
            continue
        gruppo.sort(key=lambda x: x.get("created_at") or "9999")
        for extra in gruppo[1:]:
            doppioni_stesso_addebito += 1
            if dry_run:
                continue
            await db[COLLECTION_PRIMA_NOTA_BANCA].update_one(
                {"id": extra["id"]},
                {"$set": {"status": "deleted",
                          "deleted_reason": "stesso_addebito_estratto_conto_duplicato"}})
            if extra.get("fattura_id"):
                await db["invoices"].update_one(
                    {"id": extra["fattura_id"]},
                    {"$set": {"pagato": False, "stato_pagamento": "da_pagare",
                              "prima_nota_id": None, "prima_nota_tipo": None}})

    # 2) Riga "Assegno n. X" dell'auto-match quando ESISTE già una riga
    #    fattura con lo stesso numero assegno: doppione, si elimina la riga
    #    assegno (resta quella collegata alla fattura).
    import re as _re2
    righe_assegno_duplicate = 0
    asg_rows = await db[COLLECTION_PRIMA_NOTA_BANCA].find(
        {"tipo": "uscita", "source": "assegno_auto_match",
         "status": {"$nin": ["deleted", "archived"]}, "data": {"$regex": f"^{anno}"}},
        {"_id": 0, "id": 1, "descrizione": 1},
    ).to_list(5000)
    for r in asg_rows:
        mnum = _re2.search(r"Assegno n\.\s*0*(\d{6,})", r.get("descrizione") or "")
        if not mnum:
            continue
        num = mnum.group(1)
        gemella = await db[COLLECTION_PRIMA_NOTA_BANCA].find_one({
            "id": {"$ne": r["id"]},
            "numero_assegno": {"$regex": f"0*{num}$"},
            "status": {"$nin": ["deleted", "archived"]},
        })
        if gemella:
            righe_assegno_duplicate += 1
            if not dry_run:
                await db[COLLECTION_PRIMA_NOTA_BANCA].update_one(
                    {"id": r["id"]},
                    {"$set": {"status": "deleted",
                              "deleted_reason": "riga_assegno_duplicata_vs_fattura"}})

    return {
        "dry_run": dry_run,
        "anno": anno,
        "da_correggere" if dry_run else "corretti": corretti,
        "banca_verso_provvisori": len(report["banca"]),
        "cassa_verso_provvisori": len(report["cassa"]),
        "doppioni_stesso_addebito": doppioni_stesso_addebito,
        "righe_assegno_duplicate": righe_assegno_duplicate,
        "dettaglio": {k: v[:50] for k, v in report.items()},
    }


async def collega_corrispettivi_prima_nota(
    dry_run: bool = Query(True, description="Solo conteggio, non collega"),
    _admin: Dict = Depends(get_current_admin_user),
) -> Dict:
    """Ricollega al documento i movimenti corrispettivo con corrispettivo_id
    vuoto (retaggio dei vecchi documenti senza id: il movimento nasceva con
    il link a None e il bottone 'Corrisp.' non compariva — segnalato
    dall'utente 18/07/2026, righe fino al 12/05). Collega SOLO quando per
    quella data esiste UN corrispettivo univoco."""
    db = Database.get_db()

    corr_per_data: Dict[str, list] = {}
    for c in await db["corrispettivi"].find({}, {"_id": 0, "id": 1, "data": 1}).to_list(10000):
        if c.get("id") and c.get("data"):
            corr_per_data.setdefault(str(c["data"])[:10], []).append(c["id"])

    filtro_senza_link = {
        "$or": [{"corrispettivo_id": None}, {"corrispettivo_id": ""},
                {"corrispettivo_id": {"$exists": False}}],
        "status": {"$nin": ["deleted", "archived"]},
    }
    target = [
        ("prima_nota_cassa", {"categoria": {"$in": ["Corrispettivi", "POS Verso Banca"]}}),
        ("prima_nota_banca", {"categoria": "Corrispettivi POS"}),
    ]
    collegati = ambigui = senza_documento = 0
    for collection, filtro_cat in target:
        movs = await db[collection].find(
            {**filtro_senza_link, **filtro_cat},
            {"_id": 0, "id": 1, "data": 1},
        ).to_list(10000)
        for m in movs:
            ids = corr_per_data.get((m.get("data") or "")[:10], [])
            if len(ids) == 1:
                collegati += 1
                if not dry_run:
                    await db[collection].update_one(
                        {"id": m["id"]}, {"$set": {"corrispettivo_id": ids[0]}})
            elif len(ids) > 1:
                ambigui += 1  # due matricole nello stesso giorno: non si indovina
            else:
                senza_documento += 1
    return {
        "dry_run": dry_run,
        "collegati": collegati,
        "ambigui": ambigui,
        "senza_documento": senza_documento,
    }


async def arricchisci_pagamenti_banca(
    dry_run: bool = Query(True, description="Solo conteggio, non scrive"),
    _admin: Dict = Depends(get_current_admin_user),
) -> Dict:
    """Richiesta utente 18/07/2026 (caso TOP SPINA 4853/01): per ogni riga
    di Prima Nota Banca agganciata a un movimento reale dell'estratto conto,
    specifica COME è stato pagato leggendo la causale bancaria — bonifico,
    assegno (con numero), addebito diretto SDD, PayPal — e, se assegno,
    riporta il dato anche in Gestione Assegni (stato incassato)."""
    import re as _re
    import uuid as _uuid

    db = Database.get_db()
    movs = await db[COLLECTION_PRIMA_NOTA_BANCA].find(
        {"tipo": "uscita", "estratto_conto_id": {"$nin": [None, ""]},
         "status": {"$nin": ["deleted", "archived"]}},
        {"_id": 0, "id": 1, "estratto_conto_id": 1, "descrizione": 1,
         "importo": 1, "data": 1, "fattura_id": 1, "fornitore": 1, "pagato_con": 1},
    ).to_list(20000)

    aggiornati = 0
    assegni_creati = 0
    assegni_aggiornati = 0
    per_metodo: Dict[str, int] = {}
    now = datetime.now(timezone.utc).isoformat()

    for m in movs:
        ec = await db["estratto_conto_movimenti"].find_one(
            {"id": m["estratto_conto_id"]},
            {"_id": 0, "descrizione": 1, "descrizione_originale": 1})
        if not ec:
            continue
        causale = (ec.get("descrizione_originale") or ec.get("descrizione") or "").upper()
        metodo = None
        numero = None
        if "ASSEGNO" in causale:
            metodo = "assegno"
            mnum = (_re.search(r"NUM[.:]?\s*0*(\d{6,})", causale)
                    or _re.search(r"ASSEGNO\D{0,20}0*(\d{7,})", causale))
            if mnum:
                numero = mnum.group(1)
        elif any(k in causale for k in ("BONIF", "VS.DISP", "DISPOSIZIONE")):
            metodo = "bonifico"
        elif "PAYPAL" in causale:
            metodo = "paypal"
        elif "SDD" in causale or "ADDEBITO" in causale or "ADD." in causale:
            metodo = "addebito diretto"
        if not metodo:
            continue

        per_metodo[metodo] = per_metodo.get(metodo, 0) + 1
        etichetta = f"assegno n. {numero}" if (metodo == "assegno" and numero) else metodo
        gia = (m.get("pagato_con") == metodo)
        if not gia:
            aggiornati += 1
        if dry_run:
            continue

        upd: Dict[str, Any] = {"pagato_con": metodo}
        if numero:
            upd["numero_assegno"] = numero
        descr = m.get("descrizione") or ""
        if etichetta not in descr:
            upd["descrizione"] = f"{descr} · {etichetta}"
        await db[COLLECTION_PRIMA_NOTA_BANCA].update_one({"id": m["id"]}, {"$set": upd})

        if metodo == "assegno" and numero:
            esistente = await db["assegni"].find_one(
                {"$or": [{"numero": numero}, {"numero": {"$regex": f"{numero}$"}}]})
            if esistente:
                if esistente.get("stato") != "incassato":
                    await db["assegni"].update_one(
                        {"id": esistente["id"]},
                        {"$set": {"stato": "incassato",
                                  "importo": esistente.get("importo") or m.get("importo"),
                                  "updated_at": now}})
                    assegni_aggiornati += 1
            else:
                await db["assegni"].insert_one({
                    "id": str(_uuid.uuid4()),
                    "numero": numero,
                    "stato": "incassato",
                    "importo": m.get("importo"),
                    "beneficiario": m.get("fornitore"),
                    "causale": (ec.get("descrizione_originale") or "")[:150],
                    "data_emissione": None,
                    "data_scadenza": None,
                    "data_fattura": None,
                    "numero_fattura": None,
                    "fattura_collegata": m.get("fattura_id"),
                    "fatture_collegate": [m["fattura_id"]] if m.get("fattura_id") else [],
                    "fornitore_piva": None,
                    "note": f"Creato dall'estratto conto (addebito del {m.get('data')})",
                    "created_at": now,
                    "updated_at": now,
                })
                assegni_creati += 1

    return {
        "dry_run": dry_run,
        "righe_con_estratto_conto": len(movs),
        "aggiornate": aggiornati,
        "per_metodo": per_metodo,
        "assegni_creati": assegni_creati,
        "assegni_aggiornati": assegni_aggiornati,
    }


async def unifica_categorie(
    dry_run: bool = Query(True, description="Solo conteggio, non rinomina"),
    _admin: Dict = Depends(get_current_admin_user),
) -> Dict:
    """Rinomina le categorie storiche di Prima Nota nei tre nomi canonici:
    "Fatture" (pagamenti fatture fornitori), "Versamento Banca" (contanti
    cassa→banca), "Prelevamento Banca" (contanti banca→cassa). Idempotente:
    rieseguirla non cambia più nulla."""
    db = Database.get_db()
    report = []
    totale = 0
    for collection, filtro, nuova in REGOLE_UNIFICA_CATEGORIE:
        if dry_run:
            n = await db[collection].count_documents(filtro)
        else:
            r = await db[collection].update_many(filtro, {"$set": {"categoria": nuova}})
            n = r.modified_count
        if n:
            report.append({
                "collection": collection, "filtro": str(filtro),
                "nuova_categoria": nuova, "movimenti": n,
            })
        totale += n
    return {"dry_run": dry_run, "totale_movimenti": totale, "rinomine": report}


async def fix_date_formato_italiano() -> Dict:
    """Normalizza in ISO (YYYY-MM-DD) le date salvate come GG/MM/AAAA in
    prima_nota_cassa e prima_nota_banca.

    Bug trovato in verifica live 16/07/2026: 11 movimenti banca legacy
    (source "riconciliazione_ec", writer non più esistente) hanno la data in
    formato italiano. Tutti i saldi confrontano le date come STRINGHE:
    "04/02/2026" < "2024-01-01", quindi quei movimenti finivano nel riporto
    "anni precedenti" di ogni anno (−17.254€ fantasma nel saldo iniziale)
    invece che nell'anno vero. Il fix normalizza la data e riallinea anno/mese.
    """
    import re as _re
    db = Database.get_db()

    pattern = _re.compile(r"^(\d{2})/(\d{2})/(\d{4})")
    corretti = {"prima_nota_cassa": 0, "prima_nota_banca": 0}
    dettaglio = []

    for collection in (COLLECTION_PRIMA_NOTA_CASSA, COLLECTION_PRIMA_NOTA_BANCA):
        docs = await db[collection].find(
            {"data": {"$regex": r"^\d{2}/\d{2}/\d{4}"}},
            {"_id": 0, "id": 1, "data": 1},
        ).to_list(10000)
        for d in docs:
            m = pattern.match(d["data"])
            if not m:
                continue
            gg, mm, aaaa = m.groups()
            data_iso = f"{aaaa}-{mm}-{gg}"
            await db[collection].update_one(
                {"id": d["id"]},
                {"$set": {
                    "data": data_iso,
                    "anno": int(aaaa),
                    "mese": int(mm),
                    "data_originale_malformata": d["data"],
                }},
            )
            corretti[collection] += 1
            dettaglio.append({"collection": collection, "id": d["id"],
                              "da": d["data"], "a": data_iso})

    return {
        "success": True,
        "corretti": corretti,
        "totale": sum(corretti.values()),
        "dettaglio": dettaglio[:50],
    }


async def fix_categories_and_duplicates(anno: Optional[int] = Query(None)) -> Dict:
    """Corregge le categorie errate e rimuove i duplicati."""
    db = Database.get_db()
    
    query = {}
    if anno:
        query["data"] = {"$regex": f"^{anno}"}
    
    fixed_categories = 0
    removed_duplicates = 0
    
    movimenti_cassa = await db[COLLECTION_PRIMA_NOTA_CASSA].find(query, {"_id": 0}).to_list(20000)
    
    category_mappings = [
        (["altro"], ["pos"], "POS"),
        (["tasse", "altro"], ["corrispettivo"], "Corrispettivi"),
        (["altro"], ["versamento"], "Versamento"),
    ]
    
    for mov in movimenti_cassa:
        categoria = (mov.get("categoria") or "").lower()
        descrizione = (mov.get("descrizione") or "").lower()
        new_categoria = None
        
        for cat_matches, desc_keywords, new_cat in category_mappings:
            if any(c in categoria for c in cat_matches) and any(k in descrizione for k in desc_keywords):
                new_categoria = new_cat
                break
        
        if new_categoria:
            await db[COLLECTION_PRIMA_NOTA_CASSA].update_one(
                {"id": mov["id"]},
                {"$set": {"categoria": new_categoria}}
            )
            fixed_categories += 1
    
    seen = {}
    for mov in movimenti_cassa:
        key = f"{mov.get('data')}|{mov.get('importo')}|{mov.get('descrizione', '')[:50]}"
        if key in seen:
            await db[COLLECTION_PRIMA_NOTA_CASSA].delete_one({"id": mov["id"]})
            removed_duplicates += 1
        else:
            seen[key] = mov["id"]
    
    return {
        "success": True,
        "anno": anno,
        "fixed_categories": fixed_categories,
        "removed_duplicates": removed_duplicates,
        "movimenti_analizzati": len(movimenti_cassa)
    }


async def sposta_movimento(req: SpostaMovimentoRequest) -> Dict:
    """Sposta un movimento da cassa a banca o viceversa."""
    db = Database.get_db()
    movimento_id = req.movimento_id
    da = req.da
    a = req.a

    if da not in ["cassa", "banca"] or a not in ["cassa", "banca"]:
        raise HTTPException(status_code=400, detail="da/a devono essere 'cassa' o 'banca'")

    if da == a:
        raise HTTPException(status_code=400, detail="Origine e destinazione uguali")

    source_coll = COLLECTION_PRIMA_NOTA_CASSA if da == "cassa" else COLLECTION_PRIMA_NOTA_BANCA
    dest_coll = COLLECTION_PRIMA_NOTA_CASSA if a == "cassa" else COLLECTION_PRIMA_NOTA_BANCA

    # Cerca nella collection diretta
    mov = await db[source_coll].find_one({"id": movimento_id})

    # Se non trovato in prima_nota_banca, cerca anche in estratto_conto_movimenti
    # (la sezione Banca carica i dati dall'estratto conto)
    if not mov and da == "banca":
        mov = await db["estratto_conto_movimenti"].find_one({"id": movimento_id})
        if mov:
            # Il movimento è nell'estratto conto: viene COPIATO in cassa e la
            # riga originale MARCATA come spostata — mai eliminata. L'estratto
            # conto è il documento bancario originale: cancellarlo perderebbe
            # per sempre l'origine documentale (audit 16/07/2026; prima qui
            # c'era una delete_one).
            mov.pop("_id", None)
            mov["moved_from"] = "banca_estratto_conto"
            mov["moved_at"] = datetime.now(timezone.utc).isoformat()
            mov["source"] = mov.get("source", "estratto_conto")
            # Assicura che sia un'uscita (addebito) o entrata (accredito) coerente
            await db[dest_coll].insert_one(mov)
            await db["estratto_conto_movimenti"].update_one(
                {"id": movimento_id},
                {"$set": {
                    "escluso_da_vista_banca": True,
                    "spostato_in": a,
                    "spostato_at": datetime.now(timezone.utc).isoformat(),
                }},
            )


            return {
                "success": True,
                "message": f"Movimento spostato da estratto conto banca a {a}",
                "movimento_id": movimento_id
            }

    if not mov:
        raise HTTPException(status_code=404, detail=f"Movimento {movimento_id} non trovato in {da}")

    mov.pop("_id", None)
    mov["moved_from"] = da
    mov["moved_at"] = datetime.now(timezone.utc).isoformat()

    await db[dest_coll].insert_one(mov)
    await db[source_coll].delete_one({"id": movimento_id})

    # Aggiorna la FATTURA collegata: metodo e riferimenti prima nota devono
    # seguire lo spostamento (prima restavano puntati alla collection vecchia)
    fattura_aggiornata = False
    if mov.get("fattura_id"):
        metodo_label = "contanti" if a == "cassa" else "bonifico"
        upd = {
            "prima_nota_tipo": a,
            "metodo_pagamento": metodo_label,
            "payment_method": metodo_label,
            "prima_nota_cassa_id": movimento_id if a == "cassa" else None,
            "prima_nota_banca_id": movimento_id if a == "banca" else None,
        }
        r = await db["invoices"].update_one({"id": mov["fattura_id"]}, {"$set": upd})
        fattura_aggiornata = r.modified_count > 0

    # NIENTE evento "trasferimento.creato" qui (rimosso 17/07/2026):
    # spostare un movimento tra Cassa e Banca è una RICLASSIFICAZIONE,
    # non un trasferimento di denaro. L'evento faceva scattare
    # on_trasferimento_crea_lato_opposto che creava entrate FANTASMA
    # ("Prelevamento da banca" in cassa / "Versamento contanti" in banca)
    # a ogni spostamento di fattura, gonfiando i saldi di entrambi i lati.

    return {
        "success": True,
        "message": f"Movimento spostato da {da} a {a}",
        "movimento_id": movimento_id,
        "fattura_aggiornata": fattura_aggiornata,
    }


async def verifica_metodo_fattura(fattura_id: str) -> Dict:
    """Verifica il metodo pagamento di una fattura e fornisce info debug."""
    db = Database.get_db()
    
    fattura = await db["invoices"].find_one(
        {"$or": [{"id": fattura_id}, {"invoice_key": fattura_id}]},
        {"_id": 0}
    )
    
    if not fattura:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    
    tipo_movimento, categoria, _ = determina_tipo_movimento_fattura(fattura)
    
    fornitore_piva = fattura.get("supplier_vat") or fattura.get("cedente_piva")
    fornitore_info = None
    if fornitore_piva:
        fornitore_info = await db["fornitori"].find_one(
            {"partita_iva": fornitore_piva},
            {"_id": 0, "nome": 1, "metodo_pagamento": 1}
        )
    
    return {
        "fattura_id": fattura_id,
        "tipo_documento": fattura.get("tipo_documento"),
        "metodo_pagamento_fattura": fattura.get("metodo_pagamento"),
        "tipo_movimento_calcolato": tipo_movimento,
        "categoria_calcolata": categoria,
        "fornitore": {
            "partita_iva": fornitore_piva,
            "nome": fornitore_info.get("nome") if fornitore_info else None,
            "metodo_pagamento_anagrafica": fornitore_info.get("metodo_pagamento") if fornitore_info else None
        }
    }


async def verifica_entrate_corrispettivi(anno: int = Query(...)) -> Dict:
    """Verifica entrate corrispettivi in Prima Nota Cassa."""
    db = Database.get_db()
    
    date_start = f"{anno}-01-01"
    date_end = f"{anno}-12-31"
    
    entrate_corr = await db[COLLECTION_PRIMA_NOTA_CASSA].find(
        {
            "data": {"$gte": date_start, "$lte": date_end},
            "categoria": "Corrispettivi",
            "tipo": "entrata"
        },
        {"_id": 0}
    ).to_list(10000)
    
    corrispettivi = await db["corrispettivi"].find(
        {"data": {"$gte": date_start, "$lte": date_end}},
        {"_id": 0}
    ).to_list(10000)
    
    totale_pn = sum(e.get("importo", 0) for e in entrate_corr)
    totale_corr = sum(c.get("totale", 0) for c in corrispettivi)
    
    return {
        "anno": anno,
        "prima_nota": {
            "count": len(entrate_corr),
            "totale": round(totale_pn, 2)
        },
        "corrispettivi": {
            "count": len(corrispettivi),
            "totale": round(totale_corr, 2)
        },
        "differenza": round(totale_pn - totale_corr, 2),
        "status": "OK" if abs(totale_pn - totale_corr) < 1 else "DISCREPANZA"
    }


async def fix_corrispettivi_importo(anno: int = Query(...)) -> Dict:
    """Corregge l'importo dei corrispettivi in Prima Nota Cassa."""
    db = Database.get_db()
    
    date_start = f"{anno}-01-01"
    date_end = f"{anno}-12-31"
    
    entrate = await db[COLLECTION_PRIMA_NOTA_CASSA].find(
        {
            "data": {"$gte": date_start, "$lte": date_end},
            "categoria": "Corrispettivi"
        },
        {"_id": 0}
    ).to_list(10000)
    
    fixed = 0
    for e in entrate:
        corr_id = e.get("corrispettivo_id") or e.get("riferimento", "").replace("CORR-", "")
        if not corr_id:
            continue
        
        corr = await db["corrispettivi"].find_one({"id": corr_id}, {"_id": 0})
        if not corr:
            continue
        
        totale_corretto = float(corr.get("totale", 0) or 0)
        importo_attuale = float(e.get("importo", 0))
        
        if abs(totale_corretto - importo_attuale) > 0.01:
            await db[COLLECTION_PRIMA_NOTA_CASSA].update_one(
                {"id": e["id"]},
                {"$set": {
                    "importo": totale_corretto,
                    "importo_originale": importo_attuale,
                    "fixed_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            fixed += 1
    
    return {
        "success": True,
        "anno": anno,
        "entrate_analizzate": len(entrate),
        "corrette": fixed
    }


async def migrazione_pulisci_bancari_da_cassa(_admin: Dict[str, Any] = Depends(get_current_admin_user)) -> Dict[str, Any]:
    """
    MIGRAZIONE ONE-SHOT: Elimina tutti i movimenti bancari dalla prima_nota_cassa.
    
    La Prima Nota Cassa deve contenere SOLO movimenti di denaro CONTANTE:
    - ENTRATE: Corrispettivi giornalieri, incassi contanti, finanziamenti soci in contanti
    - USCITE: Versamenti in banca, fatture pagate in contanti, piccole spese contanti
    
    NON deve contenere:
    - Bonifici, SDD, RID, pagamenti POS bancari, F24, stipendi, 
    - Pagamenti fornitori via banca, commissioni bancarie
    """
    db = Database.get_db()
    
    # Keywords che identificano movimenti BANCARI
    BANCARI_KEYWORDS = [
        'INC.POS CARTE CREDIT', 'INCAS. TRAMITE P.O.S', 'INC.POS',
        'BONIFICO', 'BONIF.', 'BON.DA', 'BONIF. VS.',
        'SEPA', 'SDD', 'RID', 'ADDEBITO DIRETTO',
        'ACCREDITO', 'GIROCONTO',
        'NUMIA', 'NEXI', 'WORLDLINE', 'SUMUP',
        'PRELIEVO ATM', 'PRELIEVO BANCOMAT',
        'Pagamento Fatt.', 'PAGAMENTO FATT.',
        'STIPENDI', 'EMOLUMENTI',
        'F24', 'DELEGA UNICA', 'MOD.F24',
        'CANONE MENSILE', 'COMMISSIONI', 'COMPETENZE E SPESE',
        'IMPOSTA BOLLO',
        'PDV 37',  # terminale POS bancario Ceraldi
    ]
    
    tutti = await db[COLLECTION_PRIMA_NOTA_CASSA].find(
        {"status": {"$nin": ["deleted", "archived"]}},
        {"_id": 1, "descrizione": 1, "categoria": 1, "source": 1, "importo": 1, "data": 1, "tipo": 1}
    ).to_list(100000)
    if len(tutti) >= 100000:
        logger.warning("manutenzione prima nota cassa: raggiunto il tetto di 100000 documenti, possibile troncamento")

    ids_da_eliminare = []
    campione_eliminati = []
    
    for m in tutti:
        desc = (m.get('descrizione') or '')
        desc_upper = desc.upper()
        cat = m.get('categoria', '') or ''
        source = m.get('source', '') or ''
        
        # Corrispettivi: SEMPRE legittimi
        if cat == 'Corrispettivi' or source == 'corrispettivi_sync':
            continue
        
        # Movimenti manuali senza keywords bancari: legittimi
        if source in ('', 'manual', 'user') or source is None:
            if not any(kw.upper() in desc_upper for kw in BANCARI_KEYWORDS):
                continue
        
        # POS manuali (categoria POS senza source csv): legittimi
        if cat == 'POS' and source in ('', 'manual', 'user', None):
            continue
            
        # Versamenti manuali: legittimi  
        if cat in ('Versamento', 'Finanziamento', 'Finanziamento soci') and source in ('', 'manual', 'user', None):
            continue
        
        # CSV import: ELIMINA se ha keywords bancari
        if source == 'csv_import':
            if any(kw.upper() in desc_upper for kw in BANCARI_KEYWORDS):
                ids_da_eliminare.append(m['_id'])
                if len(campione_eliminati) < 10:
                    campione_eliminati.append({
                        "data": m.get("data"), "descrizione": desc[:60], 
                        "importo": m.get("importo"), "source": source, "motivo": "csv_bancario"
                    })
                continue
            else:
                # CSV non bancario: potrebbe essere legittimo, lo teniamo
                continue
        
        # sync_fatture con categoria fornitori/Fatture: ELIMINA (pagato per banca, non contanti)
        if source == 'sync_fatture' and cat in ('fornitori', 'Fatture', 'fornitore'):
            ids_da_eliminare.append(m['_id'])
            if len(campione_eliminati) < 10:
                campione_eliminati.append({
                    "data": m.get("data"), "descrizione": desc[:60],
                    "importo": m.get("importo"), "source": source, "motivo": "fattura_bancaria"
                })
            continue
        
        # Qualsiasi altra source con keywords bancari: ELIMINA
        if any(kw.upper() in desc_upper for kw in BANCARI_KEYWORDS):
            ids_da_eliminare.append(m['_id'])
            if len(campione_eliminati) < 10:
                campione_eliminati.append({
                    "data": m.get("data"), "descrizione": desc[:60],
                    "importo": m.get("importo"), "source": source, "motivo": "keyword_bancario"
                })
    
    deleted_count = 0
    if ids_da_eliminare:
        result = await db[COLLECTION_PRIMA_NOTA_CASSA].delete_many({"_id": {"$in": ids_da_eliminare}})
        deleted_count = result.deleted_count
    
    remaining = await db[COLLECTION_PRIMA_NOTA_CASSA].count_documents(
        {"status": {"$nin": ["deleted", "archived"]}}
    )
    
    logger.info(f"MIGRAZIONE CASSA: Eliminati {deleted_count} movimenti bancari, rimasti {remaining}")
    
    return {
        "success": True,
        "message": f"Migrazione completata: eliminati {deleted_count} movimenti bancari da Prima Nota Cassa",
        "movimenti_eliminati": deleted_count,
        "movimenti_rimasti": remaining,
        "campione_eliminati": campione_eliminati
    }


async def dedup_fatture_prima_nota(
    applica: bool = Query(False, description="Se False esegue solo dry-run, se True elimina realmente"),
    anno: Optional[int] = Query(None, description="Limita al singolo anno")
) -> Dict[str, Any]:
    """Elimina i duplicati di fatture in Prima Nota Cassa e Banca.

    Due movimenti sono duplicati se hanno:
      - stesso fattura_id (se presente), OPPURE
      - stesso riferimento (es. FATT-xxx), OPPURE
      - stesso numero_fattura + stesso importo + stessa data
    Viene tenuto il movimento più VECCHIO (created_at minimo),
    gli altri vengono marchiati deleted (soft delete, recuperabili).

    USO: chiamare prima con ?applica=false per vedere cosa farebbe,
    poi ?applica=true per eseguire.
    """
    db = Database.get_db()

    report: Dict[str, Any] = {"cassa": {}, "banca": {}, "applica": applica}

    for collection_name in [COLLECTION_PRIMA_NOTA_CASSA, COLLECTION_PRIMA_NOTA_BANCA]:
        label = "cassa" if "cassa" in collection_name else "banca"

        query: Dict[str, Any] = {"status": {"$nin": ["deleted", "archived"]}}
        if anno:
            query["data"] = {"$gte": f"{anno}-01-01", "$lte": f"{anno}-12-31"}

        movimenti = await db[collection_name].find(query, {"_id": 0}).to_list(50000)
        if len(movimenti) >= 50000:
            logger.warning("manutenzione prima nota %s: raggiunto il tetto di 50000 documenti, possibile troncamento", label)

        # Raggruppamento per chiave di dedup
        gruppi: Dict[str, list] = {}
        for m in movimenti:
            # Considera solo movimenti che sembrano collegati a fatture
            fid = m.get("fattura_id")
            rif = m.get("riferimento") or ""
            num = m.get("numero_fattura") or ""

            chiave = None
            if fid:
                chiave = f"fid:{fid}"
            elif rif and rif.startswith("FATT-"):
                # STESSA chiave del ramo fattura_id: "FATT-<id>" e
                # fattura_id=<id> sono la stessa fattura (il vecchio
                # sync_fatture scriveva solo il riferimento — caso GB FOOD
                # 02/01/2026 doppia, segnalato dall'utente 18/07).
                chiave = f"fid:{rif[5:]}"
            elif num:
                # fallback: numero + importo + data (protegge da omonimie)
                chiave = f"num:{num}|imp:{m.get('importo')}|d:{m.get('data')}"
            else:
                continue  # non fattura, ignoro (le anonime sono gestite sotto)

            gruppi.setdefault(chiave, []).append(m)

        # Righe ANONIME (senza fattura_id/riferimento/numero, es. vecchio
        # sync_fatture: "Fattura  - GB FOOD SRL"): sono duplicati se esiste
        # una riga IDENTIFICATA con stessa data, stesso importo e lo stesso
        # fornitore citato nella descrizione (caso GB FOOD 02/01/2026,
        # segnalato dall'utente 18/07: la stessa fattura appariva due volte).
        identificate: Dict[tuple, list] = {}
        for m in movimenti:
            if m.get("fattura_id") or (m.get("riferimento") or "").startswith("FATT-") or m.get("numero_fattura"):
                k = (m.get("data"), round(float(m.get("importo") or 0), 2))
                identificate.setdefault(k, []).append((m.get("descrizione") or "").upper())
        anonime_dup = []
        for m in movimenti:
            if m.get("fattura_id") or (m.get("riferimento") or "").startswith("FATT-") or m.get("numero_fattura"):
                continue
            if m.get("categoria") != "Fatture" and "FATT" not in (m.get("descrizione") or "").upper():
                continue
            nome = (m.get("descrizione") or "").split(" - ")[-1].strip().upper()
            if len(nome) < 4:
                continue
            k = (m.get("data"), round(float(m.get("importo") or 0), 2))
            if any(nome in d for d in identificate.get(k, [])):
                anonime_dup.append(m)

        duplicati_trovati = []
        ids_da_eliminare = []
        for chiave, mov_list in gruppi.items():
            if len(mov_list) <= 1:
                continue
            # Ordina per created_at crescente: il primo resta, gli altri vanno eliminati
            mov_list.sort(key=lambda x: x.get("created_at") or "9999")
            tenuto = mov_list[0]
            da_eliminare = mov_list[1:]
            duplicati_trovati.append({
                "chiave": chiave,
                "tenuto_id": tenuto.get("id"),
                "tenuto_importo": tenuto.get("importo"),
                "tenuto_data": tenuto.get("data"),
                "eliminati_count": len(da_eliminare),
                "eliminati_ids": [d.get("id") for d in da_eliminare],
            })
            ids_da_eliminare.extend(d.get("id") for d in da_eliminare if d.get("id"))

        for m in anonime_dup:
            duplicati_trovati.append({
                "chiave": f"anonima:{m.get('data')}|{m.get('importo')}",
                "tenuto_id": "(la riga identificata con fattura)",
                "tenuto_importo": m.get("importo"),
                "tenuto_data": m.get("data"),
                "eliminati_count": 1,
                "eliminati_ids": [m.get("id")],
            })
            if m.get("id"):
                ids_da_eliminare.append(m["id"])

        # Soft delete (reversibile)
        deleted = 0
        if applica and ids_da_eliminare:
            result = await db[collection_name].update_many(
                {"id": {"$in": ids_da_eliminare}},
                {"$set": {
                    "status": "deleted",
                    "deleted_at": datetime.now(timezone.utc).isoformat(),
                    "deleted_reason": "dedup_fatture_prima_nota",
                }}
            )
            deleted = result.modified_count

        report[label] = {
            "gruppi_duplicati": len(duplicati_trovati),
            "movimenti_da_eliminare": len(ids_da_eliminare),
            "eliminati_effettivi": deleted,
            "campione": duplicati_trovati[:20],
        }

    report["nota"] = (
        "DRY-RUN (niente è stato toccato). Rilancia con ?applica=true per eseguire."
        if not applica else
        "Duplicati marchiati come deleted (soft delete, recuperabili da DB)."
    )
    return report


async def diagnostica_corrispettivi_vs_cassa(
    anno: int = Query(..., description="Anno da analizzare")
) -> Dict[str, Any]:
    """Confronta corrispettivi nella sorgente con quelli presenti in Prima Nota Cassa.

    Restituisce:
      - corrispettivi presenti nella sorgente ma MANCANTI in cassa
      - corrispettivi con importo=0 su tutti i campi noti (non sincronizzabili)
      - eventuali duplicati (stesso corrispettivo_id inserito più volte)
    """
    db = Database.get_db()

    sorgente = await db["corrispettivi"].find({"anno": anno}, {"_id": 0}).to_list(10000)
    cassa = await db[COLLECTION_PRIMA_NOTA_CASSA].find(
        {"source": "corrispettivi_sync", "corrispettivo_id": {"$ne": None},
         "status": {"$nin": ["deleted", "archived"]}},
        {"_id": 0, "corrispettivo_id": 1, "importo": 1, "data": 1, "id": 1},
    ).to_list(10000)

    cassa_by_corr: Dict[str, list] = {}
    for m in cassa:
        cassa_by_corr.setdefault(m["corrispettivo_id"], []).append(m)

    mancanti = []
    non_sincronizzabili = []  # totale = 0 su tutti i campi
    duplicati = []

    for c in sorgente:
        cid = c.get("id")
        totale = float(
            c.get("totale", 0) or c.get("totale_complessivo", 0)
            or c.get("importo", 0) or c.get("totale_giornaliero", 0) or 0
        )
        contanti = float(c.get("pagato_contanti", 0) or 0)
        pos = float(c.get("pagato_pos", 0) or c.get("pagato_elettronico", 0) or 0)
        if totale <= 0 and (contanti + pos) <= 0:
            non_sincronizzabili.append({
                "id": cid, "data": c.get("data"),
                "totale": c.get("totale"), "totale_complessivo": c.get("totale_complessivo"),
                "importo": c.get("importo"), "pagato_contanti": c.get("pagato_contanti"),
                "pagato_pos": c.get("pagato_pos"),
            })
            continue
        mov_in_cassa = cassa_by_corr.get(cid, [])
        if not mov_in_cassa:
            mancanti.append({
                "id": cid, "data": c.get("data"),
                "totale_calcolato": totale or (contanti + pos),
            })
        elif len(mov_in_cassa) > 1:
            duplicati.append({
                "corrispettivo_id": cid,
                "data": c.get("data"),
                "count_in_cassa": len(mov_in_cassa),
                "ids_movimenti": [m.get("id") for m in mov_in_cassa],
            })

    return {
        "anno": anno,
        "corrispettivi_sorgente": len(sorgente),
        "corrispettivi_in_cassa": len(cassa_by_corr),
        "mancanti_in_cassa": len(mancanti),
        "non_sincronizzabili_importo_zero": len(non_sincronizzabili),
        "duplicati_in_cassa": len(duplicati),
        "mancanti_dettaglio": mancanti[:100],
        "non_sincronizzabili_dettaglio": non_sincronizzabili[:50],
        "duplicati_dettaglio": duplicati[:50],
        "azione_consigliata_duplicati": "POST /api/prima-nota/dedup-fatture?applica=true (per fatture) o cleanup manuale per corrispettivi",
        "azione_consigliata_mancanti": "POST /api/prima-nota/cassa/sync-corrispettivi?anno={anno}",
    }


async def lista_movimenti_ec_non_in_prima_nota(
    anno: int = Query(..., description="Anno da analizzare"),
    tipo: Optional[str] = Query(None, description="Filtra per tipo: 'entrata' o 'uscita'"),
    limit: int = Query(500, description="Max risultati"),
) -> Dict[str, Any]:
    """Elenca i movimenti dell'Estratto Conto bancario che NON hanno
    corrispondenza in Prima Nota Banca.

    Un movimento è considerato "mancante" se uno dei due casi:
      1. ha flag `riconciliato` == False/None, OPPURE
      2. non c'è nessun movimento in prima_nota_banca con stesso
         importo e data (±3 giorni di tolleranza) non soft-deleted

    Il secondo controllo è un safety net nel caso il flag di
    riconciliazione non fosse stato aggiornato correttamente.
    """
    db = Database.get_db()

    # Movimenti EC non riconciliati dell'anno
    ec_query: Dict[str, Any] = {
        "data": {"$gte": f"{anno}-01-01", "$lte": f"{anno}-12-31"},
        "$or": [
            {"riconciliato": {"$ne": True}},
            {"riconciliato": {"$exists": False}},
        ],
    }
    if tipo in ("entrata", "uscita"):
        ec_query["tipo"] = tipo

    ec_movimenti = await db[COLLECTION_ESTRATTO_CONTO].find(
        ec_query, {"_id": 0}
    ).sort("data", -1).limit(limit).to_list(limit)

    # Per il safety-net, carico anche i movimenti di prima nota banca dell'anno
    pn_query: Dict[str, Any] = {
        "data": {"$gte": f"{anno}-01-01", "$lte": f"{anno}-12-31"},
        "status": {"$nin": ["deleted", "archived"]},
    }
    pn_movimenti = await db[COLLECTION_PRIMA_NOTA_BANCA].find(
        pn_query, {"_id": 0, "importo": 1, "data": 1, "tipo": 1, "riferimento": 1,
                   "fattura_id": 1, "estratto_conto_ref": 1}
    ).to_list(10000)

    # Set di EC già referenziati da qualche movimento PN (attraverso estratto_conto_ref)
    ec_refs_in_pn = {m.get("estratto_conto_ref") for m in pn_movimenti if m.get("estratto_conto_ref")}

    # Indice per match importo+data (per safety net)
    def _keys_for_safety(m):
        d = m.get("data", "")[:10]
        imp = round(float(m.get("importo", 0) or 0), 2)
        t = m.get("tipo", "")
        # chiave con tolleranza ±1 giorno
        try:
            from datetime import datetime as _dt, timedelta as _td
            dt = _dt.fromisoformat(d)
            return [
                f"{imp}|{t}|{(dt + _td(days=off)).date().isoformat()}"
                for off in (-1, 0, 1)
            ]
        except Exception:
            return [f"{imp}|{t}|{d}"]

    pn_index = set()
    for m in pn_movimenti:
        for k in _keys_for_safety(m):
            pn_index.add(k)

    mancanti = []
    for m in ec_movimenti:
        if m.get("id") in ec_refs_in_pn:
            continue  # già riferenziato da prima nota, saltiamo
        # Controllo match su importo+data: se c'è un candidato PN lo segnalo come "sospetto"
        keys = _keys_for_safety(m)
        sospetto = any(k in pn_index for k in keys)
        mancanti.append({
            "id": m.get("id"),
            "data": m.get("data"),
            "tipo": m.get("tipo"),
            "importo": round(float(m.get("importo", 0) or 0), 2),
            "descrizione": m.get("descrizione", ""),
            "categoria": m.get("categoria"),
            "riconciliato": bool(m.get("riconciliato")),
            # True = c'è forse già un record in Prima Nota con stessi dati ma non
            # collegato. Probabilmente serve solo un match, non un nuovo insert.
            "possibile_match_esistente": sospetto,
        })

    return {
        "anno": anno,
        "tipo_filtro": tipo,
        "totale_mancanti": len(mancanti),
        "totale_entrate": sum(1 for x in mancanti if x["tipo"] == "entrata"),
        "totale_uscite": sum(1 for x in mancanti if x["tipo"] == "uscita"),
        "importo_totale_entrate": round(
            sum(x["importo"] for x in mancanti if x["tipo"] == "entrata"), 2
        ),
        "importo_totale_uscite": round(
            sum(x["importo"] for x in mancanti if x["tipo"] == "uscita"), 2
        ),
        "movimenti": mancanti,
    }


async def importa_movimento_ec_in_prima_nota(
    data: Dict[str, Any] = Body(...)
) -> Dict[str, Any]:
    """Crea un movimento in Prima Nota Banca a partire da un movimento EC.

    Body:
      - ec_id: id del movimento estratto_conto_movimenti da importare
      - categoria (opzionale): categoria da assegnare al movimento PN
      - descrizione (opzionale): sovrascrive la descrizione EC

    Effetti:
      - Inserisce un record in prima_nota_banca con source='import_da_ec'
      - Segna il movimento EC con riconciliato=True e estratto_conto_ref impostato
      - Idempotente: se esiste già un PN con estratto_conto_ref=ec_id, non crea duplicati
    """
    db = Database.get_db()
    ec_id = data.get("ec_id")
    if not ec_id:
        raise HTTPException(status_code=400, detail="ec_id richiesto")

    ec = await db[COLLECTION_ESTRATTO_CONTO].find_one({"id": ec_id}, {"_id": 0})
    if not ec:
        raise HTTPException(status_code=404, detail="Movimento estratto conto non trovato")

    # Idempotenza
    existing = await db[COLLECTION_PRIMA_NOTA_BANCA].find_one({
        "estratto_conto_ref": ec_id,
        "status": {"$nin": ["deleted", "archived"]},
    })
    if existing:
        return {
            "success": True,
            "message": "Movimento già importato in precedenza",
            "prima_nota_id": existing.get("id"),
            "duplicato": True,
        }

    now = datetime.now(timezone.utc).isoformat()
    pn_id = str(uuid.uuid4())
    movimento = {
        "id": pn_id,
        "data": ec.get("data"),
        "tipo": ec.get("tipo", "uscita"),
        "importo": round(float(ec.get("importo", 0) or 0), 2),
        "descrizione": data.get("descrizione") or ec.get("descrizione", ""),
        "categoria": data.get("categoria") or ec.get("categoria") or "Da categorizzare",
        "riferimento": f"EC-{ec_id[:8]}",
        "source": "import_da_ec",
        "estratto_conto_ref": ec_id,
        "created_at": now,
    }
    await db[COLLECTION_PRIMA_NOTA_BANCA].insert_one(movimento.copy())

    # Segno il movimento EC come riconciliato
    await db[COLLECTION_ESTRATTO_CONTO].update_one(
        {"id": ec_id},
        {"$set": {"riconciliato": True, "prima_nota_id": pn_id, "riconciliato_at": now}}
    )

    return {
        "success": True,
        "message": "Movimento importato in Prima Nota Banca",
        "prima_nota_id": pn_id,
        "ec_id": ec_id,
        "duplicato": False,
    }


async def diagnostica_metodi_discordanti(anno: int = Query(...)) -> Dict:
    """Fatture registrate in un registro DIVERSO dal metodo attuale del
    fornitore ("doppio sistema" segnalato dall'utente il 10/07: Varriale
    Cassa in anagrafica ma fatture in Banca).

    Succede quando la fattura è stata confermata PRIMA che il metodo del
    fornitore venisse corretto in anagrafica. La diagnostica confronta ogni
    movimento collegato a fattura col metodo CANONICO attuale (motore unico)
    e riporta i discordanti; lo spostamento resta un'azione dell'utente
    (POST /sposta-scrittura per ogni voce).
    Fornitori misto o senza metodo: esclusi (nessuna destinazione certa).
    """
    from app.engines.prima_nota_engine import normalizza_metodo_pagamento

    db = Database.get_db()

    # Metodo canonico attuale per P.IVA (tutte le chiavi storiche; un
    # doppione senza metodo non sovrascrive il record buono)
    metodo_per_piva: Dict[str, str] = {}
    async for s in db["fornitori"].find(
        {}, {"_id": 0, "partita_iva": 1, "piva": 1, "vat_number": 1,
             "metodo_pagamento": 1, "metodo_pagamento_predefinito": 1}
    ):
        metodo = (
            normalizza_metodo_pagamento(s.get("metodo_pagamento_predefinito"))
            or normalizza_metodo_pagamento(s.get("metodo_pagamento"))
            or ""
        )
        for k in (s.get("partita_iva"), s.get("piva"), s.get("vat_number")):
            k = (str(k) if k else "").strip()
            if k and (metodo or k not in metodo_per_piva):
                metodo_per_piva[k] = metodo

    discordanti = []
    per_registro = {"cassa": COLLECTION_PRIMA_NOTA_CASSA, "banca": COLLECTION_PRIMA_NOTA_BANCA}
    for registro, coll in per_registro.items():
        async for mov in db[coll].find(
            {"fattura_id": {"$nin": [None, ""]},
             "data": {"$regex": f"^{anno}"},
             "status": {"$nin": ["deleted", "archived"]}},
            {"_id": 0, "id": 1, "data": 1, "importo": 1, "descrizione": 1,
             "numero_fattura": 1, "fornitore_piva": 1, "fattura_id": 1},
        ):
            piva = (mov.get("fornitore_piva") or "").strip()
            if not piva:
                continue
            atteso = metodo_per_piva.get(piva, "")
            if atteso in ("cassa", "banca") and atteso != registro:
                discordanti.append({
                    "movimento_id": mov["id"],
                    "registro_attuale": registro,
                    "registro_atteso": atteso,
                    "data": mov.get("data"),
                    "importo": mov.get("importo"),
                    "numero_fattura": mov.get("numero_fattura"),
                    "descrizione": (mov.get("descrizione") or "")[:80],
                    "fornitore_piva": piva,
                    "fattura_id": mov.get("fattura_id"),
                })

    discordanti.sort(key=lambda d: d.get("data") or "", reverse=True)
    return {
        "anno": anno,
        "totale_discordanti": len(discordanti),
        "discordanti": discordanti[:200],
        "azione": "POST /api/prima-nota/sposta-scrittura {movimento_id, destinazione} per ogni voce",
    }
