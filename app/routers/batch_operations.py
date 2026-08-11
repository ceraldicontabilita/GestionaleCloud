"""
Router per operazioni BATCH - N operazioni con 1 chiamata API.

Endpoints:
- POST /api/batch/riconcilia
- POST /api/batch/paga
- POST /api/batch/categorizza
- POST /api/batch/auto-riconcilia-tutto
"""
from fastapi import APIRouter, Body, HTTPException
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel
import logging

from app.database import Database

logger = logging.getLogger(__name__)
router = APIRouter()


def filtro_uscite_da_riconciliare() -> Dict[str, Any]:
    """Filtro Mongo per i movimenti di USCITA non ancora riconciliati in
    `estratto_conto_movimenti`. Copre entrambe le convenzioni di segno presenti
    nei dati: importo positivo con `tipo="uscita"` (import canonico) e importo
    negativo (import legacy). Prima si filtrava solo `importo < 0` e il job non
    trovava mai le uscite salvate come positive → zero candidati. Vedi P0.2."""
    return {
        "riconciliato": {"$nin": ["riconciliato", "parziale", True]},
        "$or": [
            {"tipo": "uscita"},
            {"importo": {"$lt": 0}},
        ],
    }


class RiconciliazioneItem(BaseModel):
    movimento_id: str
    tipo_match: str  # fattura, f24, cedolino
    match_id: str


class PagamentoItem(BaseModel):
    fattura_id: str
    importo: Optional[float] = None
    metodo: str = "bonifico"


class CategorizzaItem(BaseModel):
    fattura_id: str
    centro_costo_id: str


@router.post("/riconcilia")
async def batch_riconcilia(items: List[RiconciliazioneItem] = Body(...)) -> Dict[str, Any]:
    """Riconcilia N movimenti in 1 chiamata."""
    db = Database.get_db()
    successi = 0
    errori = []
    
    for item in items:
        try:
            # Aggiorna movimento
            await db["estratto_conto_movimenti"].update_one(
                {"id": item.movimento_id},
                {"$set": {
                    "riconciliato": "riconciliato",
                    f"{item.tipo_match}_id": item.match_id,
                    "riconciliazione_timestamp": datetime.now(timezone.utc).isoformat()
                }}
            )
            
            # Aggiorna documento collegato
            collection = {"fattura": "invoices", "f24": "f24_unificato", "cedolino": "cedolini"}.get(item.tipo_match)
            if collection:
                status_field = "stato_pagamento" if item.tipo_match == "cedolino" else "status"
                await db[collection].update_one(
                    {"id": item.match_id},
                    {"$set": {status_field: "pagato", "movimento_banca_id": item.movimento_id}}
                )
            
            # Chiudi scadenza
            await db["scadenzario"].update_one(
                {"$or": [{"fattura_id": item.match_id}, {"f24_id": item.match_id}, {"cedolino_id": item.match_id}]},
                {"$set": {"stato": "pagato"}}
            )
            
            successi += 1
        except Exception as e:
            logger.error(f"Errore riconciliazione {item.movimento_id}: {e}")
            errori.append({"movimento_id": item.movimento_id, "errore": str(e)})
    
    return {"success": True, "totale": len(items), "successi": successi, "errori": errori}


@router.post("/paga")
async def batch_paga(items: List[PagamentoItem] = Body(...)) -> Dict[str, Any]:
    """Paga N fatture. Raggruppa per IBAN per bonifici cumulativi."""
    db = Database.get_db()
    
    fatture_ids = [item.fattura_id for item in items]
    fatture = await db["invoices"].find({"id": {"$in": fatture_ids}}).to_list(5000)
    fatture_map = {f["id"]: f for f in fatture}
    
    # Raggruppa per IBAN
    per_iban = {}
    for item in items:
        fattura = fatture_map.get(item.fattura_id)
        if not fattura:
            continue
        iban = fattura.get("iban_fornitore") or "NO_IBAN"
        if iban not in per_iban:
            per_iban[iban] = {"fornitore": fattura.get("supplier_name"), "fatture": [], "totale": 0}
        importo = item.importo or float(fattura.get("total_amount", 0))
        per_iban[iban]["fatture"].append({"id": item.fattura_id, "importo": importo})
        per_iban[iban]["totale"] += importo
    
    bonifici = []
    for iban, gruppo in per_iban.items():
        bonifico = {
            "id": f"bon-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{iban[-4:]}",
            "iban": iban,
            "beneficiario": gruppo["fornitore"],
            "importo": gruppo["totale"],
            "fatture_ids": [f["id"] for f in gruppo["fatture"]],
            "stato": "da_eseguire",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db["bonifici_generati"].insert_one(bonifico.copy())
        bonifici.append(bonifico)
        
        for f in gruppo["fatture"]:
            await db["invoices"].update_one(
                {"id": f["id"]},
                {"$set": {"status": "in_pagamento", "bonifico_id": bonifico["id"]}}
            )
    
    return {"success": True, "bonifici_generati": len(bonifici), "totale": sum(b["importo"] for b in bonifici), "dettagli": bonifici}


@router.post("/categorizza")
async def batch_categorizza(items: List[CategorizzaItem] = Body(...)) -> Dict[str, Any]:
    """Categorizza N fatture con centro di costo in 1 chiamata."""
    db = Database.get_db()
    successi = 0
    errori = []
    
    # Carica centri costo per validazione
    centri_costo = await db["centri_costo"].find({}).to_list(5000)
    centri_map = {str(c.get("_id")): c.get("nome") for c in centri_costo}
    centri_map.update({c.get("id"): c.get("nome") for c in centri_costo if c.get("id")})
    
    for item in items:
        try:
            centro_nome = centri_map.get(item.centro_costo_id, item.centro_costo_id)
            
            await db["invoices"].update_one(
                {"id": item.fattura_id},
                {"$set": {
                    "centro_costo_id": item.centro_costo_id,
                    "centro_costo_nome": centro_nome,
                    "categorizzazione_timestamp": datetime.now(timezone.utc).isoformat()
                }}
            )
            successi += 1
        except Exception as e:
            logger.error(f"Errore categorizzazione {item.fattura_id}: {e}")
            errori.append({"fattura_id": item.fattura_id, "errore": str(e)})
    
    return {"success": True, "totale": len(items), "successi": successi, "errori": errori}


@router.post("/chiudi-scadenze")
async def batch_chiudi_scadenze(
    scadenza_ids: List[str] = Body(...),
    nota: str = Body("")
) -> Dict[str, Any]:
    """Chiude N scadenze come pagate."""
    db = Database.get_db()
    
    result = await db["scadenzario"].update_many(
        {"id": {"$in": scadenza_ids}},
        {"$set": {
            "stato": "pagato",
            "data_chiusura": datetime.now(timezone.utc).isoformat(),
            "nota_chiusura": nota
        }}
    )
    
    return {"success": True, "modificati": result.modified_count}


async def auto_riconcilia_tutto(
    min_confidence: int = Body(90),
    dry_run: bool = Body(True),
    conferma: bool = Body(False),
) -> Dict[str, Any]:
    """Propone match; scrive solo con numero, centesimi e fornitore certi."""
    if not dry_run and not conferma:
        raise HTTPException(
            status_code=409,
            detail="Automazione bloccata: eseguire prima la preview e confermare esplicitamente",
        )
    db = Database.get_db()
    
    movimenti = await db["estratto_conto_movimenti"].find(
        filtro_uscite_da_riconciliare()
    ).to_list(500)
    
    proposte = []
    applicati = 0
    
    for mov in movimenti:
        importo = abs(float(mov.get("importo", 0)))
        if importo < 1:
            continue
        
        # Preselezione stretta; la decisione finale usa la regola canonica.
        fatture = await db["invoices"].find({
            "status": {"$in": ["da_pagare", "pending", "in_scadenza", "scaduto"]},
            "total_amount": {"$gte": importo - 0.004, "$lte": importo + 0.004}
        }).to_list(50)
        from app.services.riconciliazione_bancaria import _evidenza_forte_fattura_banca
        descrizione = " ".join(str(mov.get(k) or "") for k in (
            "descrizione", "descrizione_originale", "causale", "beneficiario"
        ))
        sicure = [
            (f, _evidenza_forte_fattura_banca(f, descrizione, importo))
            for f in fatture
        ]
        sicure = [(f, evidenza) for f, evidenza in sicure if evidenza["auto_ammesso"]]
        for f, evidenza in sicure:
            proposte.append({
                    "movimento_id": mov.get("id"),
                    "movimento_desc": mov.get("descrizione", "")[:50],
                    "movimento_importo": importo,
                    "fattura_id": f.get("id"),
                    "fattura_fornitore": f.get("supplier_name"),
                    "fattura_importo": f.get("total_amount"),
                    "score": 100,
                    "evidenze": evidenza,
                    "ambiguo": len(sicure) != 1,
                })

        if len(sicure) == 1 and min_confidence <= 100 and not dry_run:
            f, _ = sicure[0]
            await db["estratto_conto_movimenti"].update_one(
                {"id": mov.get("id")},
                {"$set": {
                    "riconciliato": "riconciliato",
                    "fattura_id": f.get("id"),
                    "riconciliazione_auto": True,
                    "riconciliazione_score": 100,
                    "riconciliazione_timestamp": datetime.now(timezone.utc).isoformat()
                }}
            )
            await db["invoices"].update_one(
                {"id": f.get("id")},
                {"$set": {"status": "pagato", "movimento_banca_id": mov.get("id")}}
            )
            await db["scadenzario"].update_one(
                {"fattura_id": f.get("id")},
                {"$set": {"stato": "pagato"}}
            )
            applicati += 1

            try:
                from app.services.event_bus import propagate_event, EventTypes
                await propagate_event(EventTypes.FATTURA_PAGATA, {
                    "fattura_id": f.get("id"),
                    "metodo_pagamento": "banca",
                    "data_pagamento": mov.get("data") or datetime.now(timezone.utc).isoformat()[:10],
                    "movimento_id": mov.get("id"),
                    "importo": importo,
                }, db, source_module="batch_auto_riconcilia")
            except Exception:
                logger.exception("Errore propagazione fattura.pagata (auto-riconcilia)")
    
    return {
        "success": True,
        "movimenti_analizzati": len(movimenti),
        "riconciliazioni_trovate": len(proposte),
        "applicate": applicati,
        "dry_run": dry_run,
        "dettagli": proposte if dry_run else proposte[:10]  # Limita output se non dry_run
    }


@router.post("/processa-fatture-pendenti")
async def processa_fatture_pendenti(
    limite: int = Body(100),
    azioni: List[str] = Body(["classifica", "scadenza"])
) -> Dict[str, Any]:
    """
    Processa tutte le fatture in attesa:
    - classifica: Assegna centro costo basato su keywords fornitore
    - scadenza: Crea scadenza se manca
    """
    db = Database.get_db()
    
    fatture = await db["invoices"].find({
        "status": {"$in": ["in_attesa_conferma", "da_verificare", "pending"]}
    }).limit(limite).to_list(5000)
    
    risultati = {
        "fatture_processate": 0,
        "classificate": 0,
        "scadenze_create": 0,
        "errori": []
    }
    
    # Carica keywords fornitori per classificazione. Bug corretto 15/07/2026
    # (audit funzionale): leggeva dalla collection "fornitori_learning", che
    # non esiste — nessuno scrive mai lì. Il nome corretto, scritto da
    # handlers/fornitore.py e letto da tutto il resto del codice, è
    # "fornitori_keywords": prima questa azione batch non classificava mai
    # nulla (keywords_map sempre vuota).
    keywords_fornitori = await db["fornitori_keywords"].find({}).to_list(5000)
    keywords_map = {}
    for kw in keywords_fornitori:
        for word in kw.get("keywords", []):
            keywords_map[word.lower()] = kw.get("centro_costo_suggerito")
    
    for f in fatture:
        try:
            updates = {}
            
            # Classificazione
            if "classifica" in azioni and not f.get("centro_costo_id"):
                fornitore = (f.get("supplier_name") or "").lower()
                for keyword, centro in keywords_map.items():
                    if keyword in fornitore:
                        updates["centro_costo_id"] = centro
                        risultati["classificate"] += 1
                        break
            
            # Creazione scadenza
            if "scadenza" in azioni:
                scadenza_esistente = await db["scadenzario"].find_one({"fattura_id": f.get("id")})
                if not scadenza_esistente:
                    scadenza = {
                        "id": f"scad-{f.get('id')}",
                        "tipo": "fattura_passiva",
                        "fattura_id": f.get("id"),
                        "fornitore": f.get("supplier_name"),
                        "importo": f.get("total_amount"),
                        "data_scadenza": f.get("payment_due_date") or f.get("invoice_date"),
                        "stato": "da_pagare",
                        "created_at": datetime.now(timezone.utc).isoformat()
                    }
                    await db["scadenzario"].insert_one(scadenza)
                    risultati["scadenze_create"] += 1
            
            if updates:
                await db["invoices"].update_one({"id": f.get("id")}, {"$set": updates})
            
            risultati["fatture_processate"] += 1
            
        except Exception as e:
            risultati["errori"].append({"fattura_id": f.get("id"), "errore": str(e)})
    
    return {"success": True, **risultati}
