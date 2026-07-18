"""
Suppliers bulk operations endpoints.
Operazioni massive su fornitori.
"""
from fastapi import APIRouter, Body
from typing import Dict, Any
from datetime import datetime, timezone
import uuid
import httpx
import re
import asyncio

from app.database import Database, Collections
from app.middleware.performance import cache
from .common import logger

router = APIRouter()


@router.post("/aggiorna-tutti-bulk")
async def aggiorna_fornitori_bulk() -> Dict[str, Any]:
    """
    Aggiorna TUTTI i fornitori con dati incompleti cercando P.IVA su fonti esterne.
    Usa: VIES, OpenCorporates, Database locale.
    """
    db = Database.get_db()
    
    fornitori = await db[Collections.SUPPLIERS].find({
        "partita_iva": {"$exists": True, "$nin": ["", None]},
        "$or": [
            {"ragione_sociale": {"$in": [None, ""]}},
            {"comune": {"$in": [None, ""]}},
            {"indirizzo": {"$in": [None, ""]}},
        ]
    }, {"_id": 0, "id": 1, "partita_iva": 1, "ragione_sociale": 1}).to_list(500)
    
    risultato = {
        "totale_processati": 0,
        "aggiornati": 0,
        "non_trovati": 0,
        "errori": 0,
        "dettaglio": []
    }
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        for fornitore in fornitori:
            piva = re.sub(r'[^0-9]', '', str(fornitore.get("partita_iva", "")))
            if len(piva) != 11:
                continue
                
            risultato["totale_processati"] += 1
            
            try:
                dati_trovati = {}
                source = None
                
                # === FONTE 1: VIES ===
                try:
                    vies_url = "https://ec.europa.eu/taxation_customs/vies/rest-api/check-vat-number"
                    vies_resp = await client.post(vies_url, json={"countryCode": "IT", "vatNumber": piva})
                    
                    if vies_resp.status_code == 200:
                        vies_data = vies_resp.json()
                        if vies_data.get("valid"):
                            name = vies_data.get("name", "")
                            addr = vies_data.get("address", "")
                            if name and name != "---":
                                dati_trovati["ragione_sociale"] = name.strip().title()
                                source = "VIES"
                            if addr and addr != "---":
                                dati_trovati["indirizzo"] = addr.strip()
                                addr_match = re.search(r'(\d{5})\s+([A-Za-z\s]+?)(?:\s+([A-Z]{2}))?$', addr)
                                if addr_match:
                                    dati_trovati["cap"] = addr_match.group(1)
                                    dati_trovati["comune"] = addr_match.group(2).strip().title()
                                    if addr_match.group(3):
                                        dati_trovati["provincia"] = addr_match.group(3)
                except Exception:
                    pass
                
                # === FONTE 2: OpenCorporates ===
                if not dati_trovati.get("ragione_sociale"):
                    try:
                        oc_url = f"https://api.opencorporates.com/v0.4/companies/search?q={piva}&jurisdiction_code=it"
                        oc_resp = await client.get(oc_url)
                        if oc_resp.status_code == 200:
                            oc_data = oc_resp.json()
                            companies = oc_data.get("results", {}).get("companies", [])
                            if companies:
                                comp = companies[0].get("company", {})
                                if comp.get("name"):
                                    dati_trovati["ragione_sociale"] = comp["name"].title()
                                    source = source or "OpenCorporates"
                                addr = comp.get("registered_address_in_full", "")
                                if addr and not dati_trovati.get("indirizzo"):
                                    dati_trovati["indirizzo"] = addr
                    except Exception:
                        pass
                
                # === FONTE 3: Database locale (fatture) ===
                if not dati_trovati.get("ragione_sociale"):
                    invoice = await db["invoices"].find_one(
                        {"$or": [{"supplier_vat": piva}, {"cedente_piva": piva}]},
                        {"cedente_denominazione": 1, "supplier_name": 1}
                    )
                    if invoice:
                        name = invoice.get("cedente_denominazione") or invoice.get("supplier_name")
                        if name:
                            dati_trovati["ragione_sociale"] = name.strip().title()
                            source = source or "Fatture"
                
                if dati_trovati:
                    dati_trovati["updated_at"] = datetime.now(timezone.utc).isoformat()
                    dati_trovati["dati_completati_da"] = source
                    
                    await db[Collections.SUPPLIERS].update_one(
                        {"id": fornitore["id"]},
                        {"$set": dati_trovati}
                    )
                    risultato["aggiornati"] += 1
                    risultato["dettaglio"].append({
                        "piva": piva,
                        "nome": dati_trovati.get("ragione_sociale", "N/A"),
                        "source": source,
                        "status": "aggiornato"
                    })
                else:
                    risultato["non_trovati"] += 1
                    
                await asyncio.sleep(0.3)
                
            except Exception as e:
                risultato["errori"] += 1
                logger.warning(f"Errore bulk update {piva}: {e}")
    
    return {
        "success": True,
        "message": f"Aggiornati {risultato['aggiornati']} fornitori su {risultato['totale_processati']}",
        **risultato
    }


@router.post("/aggiorna-metodi-bulk")
async def aggiorna_metodi_pagamento_bulk(
    data: Dict[str, Any] = Body(...)
) -> Dict[str, Any]:
    """
    Aggiorna in blocco i metodi di pagamento dei fornitori.
    
    Input:
    {
        "fornitori": [{"partita_iva": "...", "metodo_pagamento": "..."}],
        "default_per_mancanti": "bonifico"  // opzionale
    }
    """
    db = Database.get_db()
    
    risultato = {
        "aggiornati": 0,
        "errori": [],
        "gia_impostati": 0
    }
    
    fornitori_list = data.get("fornitori", [])
    default_mancanti = data.get("default_per_mancanti")
    
    for f in fornitori_list:
        piva = f.get("partita_iva")
        metodo = f.get("metodo_pagamento", "").lower().strip()
        
        if not piva or not metodo:
            continue
        
        if metodo in ["cassa", "cash"]:
            metodo = "contanti"
        elif metodo in ["banca", "bank", "bon"]:
            metodo = "bonifico"
        
        try:
            result = await db[Collections.SUPPLIERS].update_one(
                {"partita_iva": piva},
                {"$set": {
                    "metodo_pagamento": metodo,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            if result.modified_count > 0:
                risultato["aggiornati"] += 1
            elif result.matched_count > 0:
                risultato["gia_impostati"] += 1
        except Exception as e:
            risultato["errori"].append(f"{piva}: {str(e)}")
    
    if default_mancanti:
        metodo_default = default_mancanti.lower().strip()
        if metodo_default in ["cassa", "cash"]:
            metodo_default = "contanti"
        elif metodo_default in ["banca", "bank", "bon"]:
            metodo_default = "bonifico"
        
        result = await db[Collections.SUPPLIERS].update_many(
            {"$or": [
                {"metodo_pagamento": {"$exists": False}},
                {"metodo_pagamento": None},
                {"metodo_pagamento": ""},
                {"metodo_pagamento": "N/D"}
            ]},
            {"$set": {
                "metodo_pagamento": metodo_default,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        risultato["aggiornati"] += result.modified_count
        risultato["default_applicato"] = metodo_default
    
    try:
        await cache.delete("suppliers_list_default")
    except Exception:
        pass
    
    return risultato


@router.post("/correggi-nomi-mancanti")
async def correggi_nomi_fornitori_mancanti() -> Dict[str, Any]:
    """
    Corregge i fornitori senza nome cercando il nome dalle fatture.
    """
    db = Database.get_db()
    
    risultato = {
        "corretti": 0,
        "non_trovati": [],
        "gia_ok": 0,
        "errori": []
    }
    
    cursor = db[Collections.SUPPLIERS].find({
        "$or": [
            {"denominazione": {"$in": [None, ""]}},
            {"denominazione": {"$exists": False}},
            {"ragione_sociale": {"$in": [None, ""]}},
            {"ragione_sociale": {"$exists": False}}
        ]
    }, {"_id": 0})
    
    fornitori_senza_nome = await cursor.to_list(500)
    
    fornitori_senza_nome = [
        f for f in fornitori_senza_nome 
        if not (f.get("denominazione") or "").strip() and not (f.get("ragione_sociale") or "").strip()
    ]
    
    for fornitore in fornitori_senza_nome:
        piva = fornitore.get("partita_iva")
        cf = fornitore.get("codice_fiscale")
        
        if not piva and not cf:
            continue
        
        query = {}
        if piva:
            query = {"$or": [{"cedente_piva": piva}, {"supplier_vat": piva}]}
        elif cf:
            query = {"cedente_cf": cf}
        
        fattura = await db["invoices"].find_one(
            query,
            {"_id": 0, "cedente_denominazione": 1, "supplier_name": 1}
        )
        
        if fattura:
            nome = fattura.get("cedente_denominazione") or fattura.get("supplier_name")
            if nome and nome.strip():
                await db[Collections.SUPPLIERS].update_one(
                    {"partita_iva": piva} if piva else {"codice_fiscale": cf},
                    {"$set": {
                        "denominazione": nome.strip(),
                        "ragione_sociale": nome.strip(),
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
                risultato["corretti"] += 1
            else:
                risultato["non_trovati"].append({"piva": piva, "cf": cf})
        else:
            risultato["non_trovati"].append({"piva": piva, "cf": cf})
    
    try:
        await cache.delete("suppliers_list_default")
    except Exception:
        pass
    
    risultato["totale_senza_nome"] = len(fornitori_senza_nome)
    return risultato


@router.post("/sincronizza-da-fatture")
async def sincronizza_fornitori_da_fatture() -> Dict[str, Any]:
    """
    Sincronizza tutti i fornitori dalle fatture XML al database.
    """
    db = Database.get_db()
    
    risultato = {
        "nuovi": 0,
        "aggiornati": 0,
        "gia_completi": 0,
        "errori": []
    }
    
    pipeline = [
        {"$match": {"$or": [
            {"supplier_vat": {"$exists": True, "$nin": [None, ""]}},
            {"fornitore.partita_iva": {"$exists": True, "$nin": [None, ""]}}
        ]}},
        {"$project": {
            "piva": {"$ifNull": ["$supplier_vat", "$fornitore.partita_iva"]},
            "nome": {"$ifNull": ["$supplier_name", {"$ifNull": ["$fornitore.denominazione", ""]}]},
            "fornitore": 1
        }},
        {"$group": {
            "_id": "$piva",
            "denominazione": {"$first": "$nome"},
            "fornitore_data": {"$first": "$fornitore"},
            "count": {"$sum": 1}
        }}
    ]
    
    fornitori_fatture = await db["invoices"].aggregate(pipeline).to_list(1000)
    
    for f in fornitori_fatture:
        piva = f.get("_id")
        if not piva:
            continue
        
        nome = f.get("denominazione") or f.get("supplier_name") or ""
        if not nome.strip():
            continue
        
        esistente = await db[Collections.SUPPLIERS].find_one(
            {"partita_iva": piva},
            {"_id": 0, "denominazione": 1, "ragione_sociale": 1, "metodo_pagamento": 1}
        )
        
        if esistente:
            nome_esistente = esistente.get("denominazione") or esistente.get("ragione_sociale") or ""
            if nome_esistente.strip():
                risultato["gia_completi"] += 1
                continue
            
            await db[Collections.SUPPLIERS].update_one(
                {"partita_iva": piva},
                {"$set": {
                    "denominazione": nome.strip(),
                    "ragione_sociale": nome.strip(),
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            risultato["aggiornati"] += 1
        else:
            nuovo = {
                "id": str(uuid.uuid4()),
                "partita_iva": piva,
                "codice_fiscale": f.get("codice_fiscale") or piva,
                "denominazione": nome.strip(),
                "ragione_sociale": nome.strip(),
                "indirizzo": f.get("indirizzo") or "",
                "cap": f.get("cap") or "",
                "comune": f.get("comune") or "",
                "provincia": f.get("provincia") or "",
                "nazione": f.get("nazione") or "IT",
                "pec": f.get("pec") or "",
                "metodo_pagamento": "bonifico",
                "attivo": True,
                "esclude_magazzino": True,
                "source": "sincronizzazione_fatture",
                "fatture_count": f.get("count", 0),
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await db[Collections.SUPPLIERS].insert_one(nuovo.copy())
            risultato["nuovi"] += 1
    
    try:
        await cache.delete("suppliers_list_default")
    except Exception:
        pass
    
    return risultato


async def elimina_fornitori_senza_fatture(dry_run: bool = True) -> Dict[str, Any]:
    """Richiesta utente 18/07/2026: "se non ci sono fatture associate al
    fornitore, elimina tutti direttamente". Per ogni fornitore conta le
    fatture in archivio (per P.IVA, in tutte le sue varianti di campo, o
    per nome esatto se senza P.IVA): chi ha ZERO fatture viene eliminato —
    copre anche le voci "Fornitore sconosciuto" senza documenti."""
    from fastapi import Query  # firma uniforme con gli altri endpoint admin

    db = Database.get_db()
    fornitori = await db[Collections.SUPPLIERS].find(
        {}, {"_id": 0, "id": 1, "partita_iva": 1, "piva": 1, "vat_number": 1,
             "ragione_sociale": 1, "denominazione": 1, "nome": 1},
    ).to_list(5000)

    eliminati = []
    conservati = 0
    for f in fornitori:
        chiavi = [str(k).strip() for k in (f.get("partita_iva"), f.get("piva"), f.get("vat_number")) if k]
        nome = f.get("ragione_sociale") or f.get("denominazione") or f.get("nome") or ""
        # solo fatture VIVE: le soft-deleted non tengono in vita un fornitore
        vive = {"status": {"$nin": ["deleted", "archived"]}}
        if chiavi:
            query = {**vive, "$or": [{"supplier_vat": {"$in": chiavi}}, {"cedente_piva": {"$in": chiavi}}]}
        elif nome:
            query = {**vive, "supplier_name": nome}
        else:
            query = None  # né P.IVA né nome: nessuna fattura può riferirlo
        count = await db[Collections.INVOICES].count_documents(query) if query else 0
        if count:
            conservati += 1
            continue
        eliminati.append(nome or f.get("id"))
        if not dry_run and f.get("id"):
            await db[Collections.SUPPLIERS].delete_one({"id": f["id"]})

    return {
        "dry_run": dry_run,
        "fornitori_totali": len(fornitori),
        "con_fatture": conservati,
        "senza_fatture_eliminati" if not dry_run else "senza_fatture_da_eliminare": len(eliminati),
        "elenco": sorted(eliminati)[:100],
    }


def _estrai_cedente_da_xml(xml_raw) -> Dict[str, Any]:
    """Nome, IBAN, email del CEDENTE letti direttamente dall'XML (regex,
    regge anche i .p7m sporchi). Usato quando i campi normalizzati della
    fattura dicono solo 'Fornitore Sconosciuto'."""
    testo = xml_raw if isinstance(xml_raw, str) else str(xml_raw or "")
    out: Dict[str, Any] = {}
    blocco = re.search(r"<CedentePrestatore>(.*?)</CedentePrestatore>", testo, re.S)
    b = blocco.group(1) if blocco else testo

    m = re.search(r"<Denominazione>\s*([^<]+?)\s*</Denominazione>", b)
    if m:
        out["nome"] = m.group(1).strip()
    else:
        nome = re.search(r"<Nome>\s*([^<]+?)\s*</Nome>", b)
        cogn = re.search(r"<Cognome>\s*([^<]+?)\s*</Cognome>", b)
        if nome and cogn:
            out["nome"] = f"{nome.group(1).strip()} {cogn.group(1).strip()}"
    m = re.search(r"<Email>\s*([^<]+?)\s*</Email>", b)
    if m:
        out["email"] = m.group(1).strip()
    # l'IBAN sta nei DatiPagamento, fuori dal blocco cedente
    m = re.search(r"<IBAN>\s*([A-Z0-9 ]{15,34})\s*</IBAN>", testo)
    if m:
        out["iban"] = m.group(1).replace(" ", "")
    return out


async def ripara_fornitori_sconosciuti() -> Dict[str, Any]:
    """Richiesta utente 18/07/2026: corregge i 'Fornitore Sconosciuto'
    leggendo il vero cedente dall'XML delle loro fatture, e popola
    l'anagrafica (nome, IBAN, email) per TUTTI i fornitori a cui manca —
    'dalle fatture devi estrarre e popolare i dati del fornitore anche
    con l'IBAN che trovi'."""
    db = Database.get_db()

    fornitori = await db[Collections.SUPPLIERS].find({}, {"_id": 0}).to_list(5000)
    corretti_nome = iban_aggiunti = email_aggiunte = fatture_corrette = 0
    dettaglio = []
    errori = []

    for f in fornitori:
      try:
        chiavi = [str(k).strip() for k in (f.get("partita_iva"), f.get("piva"), f.get("vat_number")) if k]
        if not chiavi or not f.get("id"):
            continue
        nome_attuale = (f.get("ragione_sociale") or f.get("denominazione") or f.get("nome") or "").strip()
        manca_nome = (not nome_attuale) or ("sconosciut" in nome_attuale.lower())
        manca_iban = not (f.get("iban") or f.get("iban_lista"))
        manca_email = not f.get("email")
        if not (manca_nome or manca_iban or manca_email):
            continue

        fatture = await db[Collections.INVOICES].find(
            {"$or": [{"supplier_vat": {"$in": chiavi}}, {"cedente_piva": {"$in": chiavi}}],
             "status": {"$nin": ["deleted", "archived"]},
             "xml_raw": {"$exists": True}},
            {"_id": 0, "id": 1, "xml_raw": 1, "supplier_name": 1},
        ).to_list(5)

        dati: Dict[str, Any] = {}
        for fatt in fatture:
            estratti = _estrai_cedente_da_xml(fatt.get("xml_raw"))
            for k, v in estratti.items():
                dati.setdefault(k, v)
            # corregge anche la FATTURA che diceva 'Fornitore Sconosciuto'
            if estratti.get("nome") and "sconosciut" in (fatt.get("supplier_name") or "").lower():
                await db[Collections.INVOICES].update_one(
                    {"id": fatt["id"]},
                    {"$set": {"supplier_name": estratti["nome"],
                              "cedente_denominazione": estratti["nome"]}})
                fatture_corrette += 1

        upd: Dict[str, Any] = {}
        if manca_nome and dati.get("nome"):
            upd["ragione_sociale"] = upd["denominazione"] = upd["nome"] = dati["nome"]
            corretti_nome += 1
            dettaglio.append({"piva": chiavi[0], "nome": dati["nome"]})
        if manca_iban and dati.get("iban"):
            upd["iban"] = dati["iban"]
            iban_aggiunti += 1
        if manca_email and dati.get("email"):
            upd["email"] = dati["email"]
            email_aggiunte += 1
        if upd:
            upd["updated_at"] = datetime.now(timezone.utc).isoformat()
            await db[Collections.SUPPLIERS].update_one({"id": f["id"]}, {"$set": upd})
      except Exception as e:
        # un fornitore rotto non deve far saltare TUTTA la riparazione
        logger.exception(f"ripara-sconosciuti: errore su fornitore {f.get('id')}")
        errori.append({"fornitore_id": f.get("id"),
                       "piva": f.get("partita_iva") or f.get("piva"),
                       "errore": f"{type(e).__name__}: {e}"[:200]})

    try:
        await cache.delete("suppliers_list_default")
    except Exception:
        pass
    return {
        "nomi_corretti": corretti_nome,
        "iban_aggiunti": iban_aggiunti,
        "email_aggiunte": email_aggiunte,
        "fatture_corrette": fatture_corrette,
        "dettaglio_nomi": dettaglio[:30],
        "errori": errori[:20],
    }
