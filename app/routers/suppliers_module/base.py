"""
Suppliers base CRUD operations.
List, get, update, delete suppliers.
"""
from fastapi import APIRouter, HTTPException, Query, Body, Depends
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, timezone
import uuid
import httpx
import re

from app.database import Database, Collections
from app.utils.dependencies import get_current_admin_user
from app.middleware.performance import cache
from .common import (
    PAYMENT_METHODS, PAYMENT_TERMS, SUPPLIERS_CACHE_KEY, SUPPLIERS_CACHE_TTL,
    logger
)
from app.services.magazzino_fornitore import (
    MOTIVO_MODIFICA_SCHEDA, anteprima as anteprima_magazzino, applica as applica_magazzino,
    allinea_da_lotti, carica_decisioni, vista_scheda,
)
from app.services.piva_validazione import vista_piva
from app.services.metodo_fornitore_dal import applica as applica_metodo_dal, stato as stato_metodo_dal
from app.services.payment_allocation_validator import allocation_summary, is_credit_note
from app.services.fattura_attiva import FILTRO_FATTURA_ATTIVA, importo_documento_con_segno
from app.services.stato_pagamento_fattura import e_annullata, e_pagata
from app.constants.tipi_documento import TIPI_NOTA_CREDITO
from app.services.payment_evidence_projection import project_payment_evidence_many

router = APIRouter()


def _normalized_supplier_key(value: Any) -> str:
    """Chiave fiscale comparabile tra schema storico e schema privato."""
    normalized = re.sub(r"[^A-Z0-9]", "", str(value or "").upper())
    if normalized.startswith("IT") and normalized[2:].isdigit():
        return normalized[2:]
    return normalized


_INVOICE_AMOUNT_FIELDS = (
    "importo_totale", "total_amount", "totale_documento", "totale",
    "importo_documento", "importo",
)


def _invoice_amount(invoice: Dict[str, Any]) -> float:
    """Legge il totale documento dagli schemi di import supportati.

    Le fatture XML, gli import storici e le fatture create dalla UI non hanno
    sempre lo stesso nome di campo. Un contatore puo' quindi dire "1 fattura"
    mentre il totale risulta falsamente zero. Questa funzione non ricostruisce
    importi: usa soltanto un totale effettivamente presente sul documento.
    """
    raw = next((invoice.get(field) for field in _INVOICE_AMOUNT_FIELDS
                if invoice.get(field) not in (None, "")), 0)
    if isinstance(raw, str):
        value = raw.strip().replace(" ", "")
        if "," in value:
            value = value.replace(".", "").replace(",", ".")
        raw = value
    try:
        return float(raw or 0)
    except (TypeError, ValueError):
        return 0.0


def _legacy_supplier_view(supplier: Dict[str, Any]) -> Dict[str, Any]:
    """Espone anche i fornitori del nuovo DB alla UI storica senza riscriverli."""
    if not supplier.get("vat") and not supplier.get("match_key"):
        return supplier
    explicit_vat = supplier.get("vat")
    match_key = _normalized_supplier_key(supplier.get("match_key"))
    # Alcuni archivi usano match_key come P.IVA, altri come nome normalizzato.
    # Solo undici cifre costituiscono qui una P.IVA italiana utilizzabile.
    piva = _normalized_supplier_key(explicit_vat)
    if not piva and len(match_key) == 11 and match_key.isdigit():
        piva = match_key
    name = supplier.get("name") or supplier.get("ragione_sociale") or ""
    return {
        **supplier,
        "id": supplier.get("id") or supplier.get("match_key") or piva,
        "partita_iva": supplier.get("partita_iva") or piva or "",
        "piva": supplier.get("piva") or piva or "",
        "ragione_sociale": supplier.get("ragione_sociale") or name,
        "denominazione": supplier.get("denominazione") or name,
        "nome": name,
        "metodo_pagamento": (
            supplier.get("metodo_pagamento")
            or supplier.get("default_payment_method")
            or ""
        ),
        "comune": supplier.get("comune") or supplier.get("locality") or "",
        # Solo la scelta scritta. Il vecchio ripiego `not inventory_enabled`
        # (campo che nessuno dei 198 fornitori ha) faceva risultare escluso chi
        # non era mai stato deciso; lo stato effettivo lo calcola
        # `magazzino_fornitore.vista_scheda` (ERP, poi Lotti, poi «non deciso»).
        "esclude_magazzino": supplier.get("esclude_magazzino") is True,
        "esclude_cassa_banca": supplier.get(
            "esclude_cassa_banca", bool(supplier.get("cessato", False))
        ),
        "attivo": supplier.get("attivo", True),
    }


async def _sincronizza_esclusione_cassa_banca(
    db, supplier: Dict[str, Any], escluso: bool
) -> Dict[str, int]:
    """Propaga la scelta finanziaria senza toccare i dati fiscali.

    Le fatture restano nella collection ``invoices`` con imponibile, IVA,
    righe e XML originali. Quando si attiva l'esclusione rimuoviamo soltanto
    i movimenti derivati automaticamente dal metodo del fornitore; movimenti
    bancari reali, riconciliati o inseriti manualmente non vengono cancellati.
    """
    valori_piva = {
        str(v).strip()
        for v in (
            supplier.get("partita_iva"),
            supplier.get("piva"),
            supplier.get("vat_number"),
        )
        if v
    }
    if not valori_piva:
        return {"fatture_aggiornate": 0, "movimenti_auto_rimossi": 0}

    invoice_filter = {"$or": [
        {"supplier_vat": {"$in": list(valori_piva)}},
        {"cedente_piva": {"$in": list(valori_piva)}},
        {"fornitore_partita_iva": {"$in": list(valori_piva)}},
    ]}
    fiscal_update = {
        "esclusa_da_cassa_banca": bool(escluso),
        "registrazione_fiscale_mantenuta": True,
        "stato_finanziario": "esclusa_cassa_banca" if escluso else "da_registrare",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    fatture_result = await db[Collections.INVOICES].update_many(
        invoice_filter, {"$set": fiscal_update}
    )

    rimossi = 0
    if escluso:
        fonti_automatiche = ["auto_metodo_fornitore", "auto_confirm_provvisoria"]
        ids_movimenti = []
        ids_fatture = []
        for collection in ("prima_nota_cassa", "prima_nota_banca"):
            movimenti = await db[collection].find(
                {
                    "fornitore_piva": {"$in": list(valori_piva)},
                    "source": {"$in": fonti_automatiche},
                    "riconciliato": {"$ne": True},
                },
                {"_id": 0, "id": 1, "fattura_id": 1},
            ).to_list(5000)
            ids_movimenti.extend(m.get("id") for m in movimenti if m.get("id"))
            ids_fatture.extend(m.get("fattura_id") for m in movimenti if m.get("fattura_id"))
            eliminati = await db[collection].delete_many({
                "fornitore_piva": {"$in": list(valori_piva)},
                "source": {"$in": fonti_automatiche},
                "riconciliato": {"$ne": True},
            })
            rimossi += eliminati.deleted_count

        await db[Collections.INVOICES].update_many(
            {"$and": [
                invoice_filter,
                {"$or": [
                    {"id": {"$in": ids_fatture}},
                    {"prima_nota_id": {"$in": ids_movimenti}},
                    {"registrata_auto_da_metodo_fornitore": True},
                ]},
            ]},
            {
                "$set": {
                    "esclusa_da_cassa_banca": True,
                    "registrazione_fiscale_mantenuta": True,
                    "stato_finanziario": "esclusa_cassa_banca",
                    "pagato": False,
                    "paid": False,
                },
                "$unset": {
                    "prima_nota_id": "",
                    "prima_nota_tipo": "",
                    "prima_nota_cassa_id": "",
                    "prima_nota_banca_id": "",
                    "registrata_auto_da_metodo_fornitore": "",
                    "stato_pagamento": "",
                    "data_pagamento": "",
                },
            },
        )

    return {
        "fatture_aggiornate": getattr(fatture_result, "modified_count", 0),
        "movimenti_auto_rimossi": rimossi,
    }


@router.get("/search-piva/{partita_iva}")
async def search_by_piva(partita_iva: str) -> Dict[str, Any]:
    """
    Cerca informazioni aziendali partendo dalla Partita IVA.
    Utilizza: VIES, RegistroAziende, Database locale.
    """
    piva = re.sub(r'[^0-9]', '', partita_iva)
    
    if len(piva) != 11:
        raise HTTPException(status_code=400, detail="Partita IVA deve essere di 11 cifre")
    
    result = {
        "found": False,
        "partita_iva": piva,
        "ragione_sociale": None,
        "indirizzo": None,
        "cap": None,
        "comune": None,
        "provincia": None,
        "nazione": "IT",
        "pec": None,
        "source": None
    }
    
    db = Database.get_db()
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            # VIES
            try:
                vies_url = "https://ec.europa.eu/taxation_customs/vies/rest-api/check-vat-number"
                vies_resp = await client.post(vies_url, json={"countryCode": "IT", "vatNumber": piva})
                
                if vies_resp.status_code == 200:
                    vies_data = vies_resp.json()
                    if vies_data.get("valid"):
                        result["found"] = True
                        result["source"] = "VIES"
                        name = vies_data.get("name", "")
                        if name and name != "---":
                            result["ragione_sociale"] = name.strip().title()
                        addr = vies_data.get("address", "")
                        if addr and addr != "---":
                            result["indirizzo"] = addr.strip()
                            addr_match = re.search(r'(\d{5})\s+([A-Za-z\s]+?)(?:\s+([A-Z]{2}))?$', addr)
                            if addr_match:
                                result["cap"] = addr_match.group(1)
                                result["comune"] = addr_match.group(2).strip().title()
                                if addr_match.group(3):
                                    result["provincia"] = addr_match.group(3)
            except Exception as e:
                logger.warning(f"VIES lookup failed: {e}")
            
            # Database locale
            if not result["ragione_sociale"]:
                invoice = await db["invoices"].find_one(
                    {"$or": [{"supplier_vat": piva}, {"cedente_piva": piva}]},
                    {"cedente_denominazione": 1, "supplier_name": 1, "supplier_address": 1}
                )
                if invoice:
                    name = invoice.get("cedente_denominazione") or invoice.get("supplier_name")
                    if name:
                        result["ragione_sociale"] = name
                        result["found"] = True
                        result["source"] = result["source"] or "Database locale"
            
            if not result["ragione_sociale"]:
                supplier = await db[Collections.SUPPLIERS].find_one(
                    {"partita_iva": piva},
                    {"_id": 0}
                )
                if supplier:
                    result["ragione_sociale"] = supplier.get("ragione_sociale") or supplier.get("denominazione")
                    result["indirizzo"] = result["indirizzo"] or supplier.get("indirizzo")
                    result["cap"] = result["cap"] or supplier.get("cap")
                    result["comune"] = result["comune"] or supplier.get("comune")
                    result["provincia"] = result["provincia"] or supplier.get("provincia")
                    result["pec"] = result["pec"] or supplier.get("pec")
                    if result["ragione_sociale"]:
                        result["found"] = True
                        result["source"] = result["source"] or "Database locale"
            
            if not result["found"]:
                result["message"] = "Partita IVA non trovata nelle fonti pubbliche"
            
            return result
                
        except httpx.TimeoutException as exc:
            raise HTTPException(status_code=504, detail="Timeout nella ricerca") from exc
        except Exception as e:
            logger.error(f"Errore ricerca PIVA: {e}")
            raise HTTPException(status_code=500, detail=f"Errore nella ricerca: {str(e)}") from e


@router.get("")
async def list_suppliers(
    skip: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=1000),
    search: Optional[str] = Query(None),
    metodo_pagamento: Optional[str] = Query(None),
    attivo: Optional[bool] = Query(None),
    esclude_magazzino: Optional[bool] = Query(None, description="True=fornitori esclusi da magazzino, False=fornitori che popolano magazzino"),
    stato_anagrafica: Optional[str] = Query(None, description="'nuovo' (prima fattura < giorni_nuovo gg) | 'storico' (prima fattura >= giorni_nuovo gg)"),
    giorni_nuovo: int = Query(90, ge=1, le=3650, description="Soglia giorni per definire 'nuovo'"),
    prodotto: Optional[str] = Query(None, description="Cerca fornitori che hanno un prodotto in magazzino con nome/descrizione che matcha"),
    use_cache: bool = Query(True)
) -> List[Dict[str, Any]]:
    """Lista fornitori con filtri e statistiche fatture."""
    
    db = Database.get_db()
    
    # Filtri avanzati disabilitano la cache
    advanced_filters_active = (
        esclude_magazzino is not None or stato_anagrafica or prodotto
    )
    
    cache_key = f"{SUPPLIERS_CACHE_KEY}:all"
    if use_cache and not search and not metodo_pagamento and attivo is None and not advanced_filters_active:
        cached_data = await cache.get(cache_key)
        if cached_data is not None:
            return cached_data[skip:skip+limit]
    
    suppliers_map = {}
    
    suppliers_query = {}
    compatible_filters = []
    if attivo is not None:
        if attivo:
            compatible_filters.append({"$or": [{"attivo": True}, {"attivo": {"$exists": False}}]})
        else:
            compatible_filters.append({"attivo": False})
    if search and search.strip():
        import re as _re
        search_lower = _re.escape(search.strip())
        compatible_filters.append({"$or": [
            {"denominazione": {"$regex": search_lower, "$options": "i"}},
            {"ragione_sociale": {"$regex": search_lower, "$options": "i"}},
            {"partita_iva": {"$regex": search_lower, "$options": "i"}},
            {"name": {"$regex": search_lower, "$options": "i"}},
            {"vat": {"$regex": search_lower, "$options": "i"}},
            {"match_key": {"$regex": search_lower, "$options": "i"}},
        ]})
    if metodo_pagamento:
        compatible_filters.append({"$or": [
            {"metodo_pagamento": metodo_pagamento},
            {"default_payment_method": metodo_pagamento},
        ]})
    if compatible_filters:
        suppliers_query["$and"] = compatible_filters
    
    # Pre-filtro per 'prodotto': trova le P.IVA dei fornitori che hanno il prodotto in magazzino
    piva_con_prodotto: Optional[set] = None
    if prodotto and prodotto.strip():
        import re as _re
        prod_regex = _re.escape(prodotto.strip())
        prodotti_match = await db[Collections.WAREHOUSE_PRODUCTS].find(
            {"$or": [
                {"nome": {"$regex": prod_regex, "$options": "i"}},
                {"descrizione": {"$regex": prod_regex, "$options": "i"}}
            ]},
            {"_id": 0, "fornitore_piva": 1}
        ).to_list(5000)
        piva_con_prodotto = {p["fornitore_piva"] for p in prodotti_match if p.get("fornitore_piva")}
        if not piva_con_prodotto:
            return []  # Nessun fornitore matcha
        suppliers_query.setdefault("$and", []).append({"$or": [
            {"partita_iva": {"$in": list(piva_con_prodotto)}},
            {"vat": {"$in": list(piva_con_prodotto)}},
            {"match_key": {"$in": list(piva_con_prodotto)}},
        ]})
    
    # Un fornitore unificato in un altro (`merged_into`) non e' piu' in elenco.
    suppliers_query["merged_into"] = {"$exists": False}
    saved_suppliers = await db[Collections.SUPPLIERS].find(suppliers_query, {"_id": 0}).to_list(1000)
    
    for raw_supplier in saved_suppliers:
        supplier = _legacy_supplier_view(raw_supplier)
        # P.IVA anche nei campi legacy: i fornitori storici usano 'piva'/'vat_number'
        piva = supplier.get("partita_iva") or supplier.get("piva") or supplier.get("vat_number")
        # L'archivio storico contiene anche anagrafiche documentate dal nome e
        # dall'ID sorgente ma prive di P.IVA. Non vanno nascoste e non va
        # inventata una P.IVA per renderle visibili: usiamo l'ID soltanto come
        # chiave tecnica della vista. L'aggancio fiscale resta possibile solo
        # quando esiste davvero una P.IVA.
        identity = _normalized_supplier_key(piva)
        if not identity:
            source_id = supplier.get("id") or raw_supplier.get("id")
            name = (
                supplier.get("ragione_sociale")
                or supplier.get("denominazione")
                or supplier.get("name")
            )
            identity = f"id:{source_id}" if source_id else f"nome:{_normalized_supplier_key(name)}"
        if identity and identity not in {"id:", "nome:"}:
            suppliers_map[identity] = {
                **supplier,
                "fatture_count": supplier.get("fatture_count", 0),
                "fatture_totale": 0,
                "fatture_non_pagate": 0,
                "source": "database"
            }

    # Indice alias: lo stesso fornitore raggiungibile da TUTTE le sue P.IVA
    # (partita_iva / piva / vat_number), per agganciare le statistiche fatture
    # qualunque sia il campo usato nel documento fattura.
    alias_index: Dict[str, Dict[str, Any]] = {}
    for rec in suppliers_map.values():
        for k in ("partita_iva", "piva", "vat_number"):
            v = (rec.get(k) or "").strip() if isinstance(rec.get(k), str) else rec.get(k)
            if v:
                alias_index[_normalized_supplier_key(v)] = rec

    # Statistiche fatture SEMPRE: prima con una ricerca attiva i contatori
    # 'Con Fatture'/'Fatture' sulle card crollavano a 0 (dati stantii)
    need_stats = True
    if need_stats:
        # NB: coalesce su TUTTI i campi P.IVA delle fatture — supplier_vat
        # (schema inglese), cedente_piva (schema italiano), fornitore_partita_iva.
        # Prima cedente_piva mancava: i fornitori con sole fatture in schema
        # italiano risultavano "0 fatture / mai fatturato".
        try:
            # Solo i campi dei contatori. Il documento fattura intero (XML
            # compreso) faceva restare la pagina su «Caricamento» per decine
            # di secondi. Il tetto è alto abbastanza da non tagliare l'archivio
            # 2026; i campi non letti non viaggiano.
            # Solo le fatture attive: ogni fattura 2026 esiste anche come
            # copia `archived`, e senza filtro contatori e saldi raddoppiano.
            invoice_rows = await db["invoices"].find(
                {"$and": [dict(FILTRO_FATTURA_ATTIVA), {"$or": [
                    {"supplier_vat": {"$exists": True, "$nin": [None, ""]}},
                    {"cedente_piva": {"$exists": True, "$nin": [None, ""]}},
                    {"fornitore_partita_iva": {"$exists": True, "$nin": [None, ""]}},
                ]}]},
                {
                    "_id": 0,
                    "supplier_vat": 1,
                    "cedente_piva": 1,
                    "fornitore_partita_iva": 1,
                    "importo_totale": 1,
                    "total_amount": 1,
                    "totale_documento": 1,
                    "totale": 1,
                    "importo_documento": 1,
                    "importo": 1,
                    "stato_pagamento": 1,
                    "stato": 1,
                    "payment_status": 1,
                    "pagato": 1,
                    "paid": 1,
                    "tipo_documento": 1,
                    "document_type": 1,
                    "document_role": 1,
                    "esclusa_da_cassa_banca": 1,
                    "data_documento": 1,
                    "invoice_date": 1,
                },
            ).to_list(200000)
            grouped_stats: Dict[str, Dict[str, Any]] = {}
            for invoice in invoice_rows:
                piva = (invoice.get("supplier_vat") or invoice.get("cedente_piva")
                        or invoice.get("fornitore_partita_iva"))
                key = _normalized_supplier_key(piva)
                if not key:
                    continue
                # Nota di credito in negativo; «pagata» dal solo criterio
                # canonico, che legge tutti e cinque i campi di stato.
                amount = importo_documento_con_segno(invoice, _invoice_amount(invoice))
                paid = e_pagata(invoice)
                annullata = e_annullata(invoice)
                excluded = invoice.get("esclusa_da_cassa_banca") is True
                date_value = invoice.get("data_documento") or invoice.get("invoice_date")
                stat = grouped_stats.setdefault(key, {
                    "_id": piva, "fatture_count": 0, "fatture_totale": 0.0,
                    "fatture_pagate": 0.0, "fatture_non_pagate": 0.0,
                    "fatture_non_pagate_count": 0,
                    "fatture_escluse_cassa_banca": 0.0,
                    "prima_fattura_data": None, "ultima_fattura_data": None,
                })
                stat["fatture_count"] += 1
                stat["fatture_totale"] += amount
                if paid:
                    stat["fatture_pagate"] += amount
                elif not excluded and not annullata:
                    stat["fatture_non_pagate"] += amount
                    stat["fatture_non_pagate_count"] += 1
                if excluded:
                    stat["fatture_escluse_cassa_banca"] += amount
                if date_value:
                    date_text = str(date_value)
                    if not stat["prima_fattura_data"] or date_text < stat["prima_fattura_data"]:
                        stat["prima_fattura_data"] = date_text
                    if not stat["ultima_fattura_data"] or date_text > stat["ultima_fattura_data"]:
                        stat["ultima_fattura_data"] = date_text

            invoice_stats = list(grouped_stats.values())

            for stat in invoice_stats:
                piva = stat.get("_id")
                rec = alias_index.get(_normalized_supplier_key(piva)) if piva else None
                if rec is not None:
                    rec["fatture_count"] = rec.get("fatture_count", 0) + stat.get("fatture_count", 0) \
                        if rec.get("source") == "merged" else stat.get("fatture_count", 0)
                    rec["fatture_totale"] = rec.get("fatture_totale", 0) + stat.get("fatture_totale", 0)
                    rec["fatture_pagate"] = rec.get("fatture_pagate", 0) + stat.get("fatture_pagate", 0)
                    rec["fatture_non_pagate"] = rec.get("fatture_non_pagate", 0) + stat.get("fatture_non_pagate", 0)
                    rec["fatture_non_pagate_count"] = (
                        rec.get("fatture_non_pagate_count", 0) + stat.get("fatture_non_pagate_count", 0)
                    )
                    rec["fatture_escluse_cassa_banca"] = (
                        rec.get("fatture_escluse_cassa_banca", 0)
                        + stat.get("fatture_escluse_cassa_banca", 0)
                    )
                    prima = stat.get("prima_fattura_data")
                    if prima and (not rec.get("prima_fattura_data") or prima < rec["prima_fattura_data"]):
                        rec["prima_fattura_data"] = prima
                    ultima = stat.get("ultima_fattura_data")
                    if ultima and (not rec.get("ultima_fattura_data") or ultima > rec["ultima_fattura_data"]):
                        rec["ultima_fattura_data"] = ultima
                    rec["source"] = "merged"
        except Exception as e:
            logger.warning(f"Error loading invoice stats: {e}")

        # Il secondo giro su `fatture_passive` e' stato tolto il 19/09/2026:
        # quella collezione non esiste nel database, quindi sommava sempre
        # zero. Le fatture fornitore stanno in `invoices`, lette sopra — e
        # sommare due archivi per gli stessi saldi e' il modo piu' rapido per
        # contare una fattura due volte il giorno in cui uno dei due si
        # popola davvero.

    suppliers = list(suppliers_map.values())

    # Nel magazzino / fuori: stato effettivo (anagrafica ERP, poi decisione di
    # Lotti, poi «non deciso» = incluso) con motivo, data e chi l'ha deciso.
    decisioni_magazzino = await carica_decisioni(db)
    for s_ in suppliers:
        s_.update(vista_scheda(s_, decisioni_magazzino))
        s_.update(vista_piva(s_))
    if esclude_magazzino is not None:
        suppliers = [s_ for s_ in suppliers
                     if bool(s_.get("esclude_magazzino")) == esclude_magazzino]

    # Filtro stato_anagrafica (post-aggregation perché richiede prima_fattura_data)
    if stato_anagrafica:
        soglia_date = (datetime.now(timezone.utc) - timedelta(days=giorni_nuovo)).date().isoformat()
        
        def _match_stato(s):
            prima = s.get("prima_fattura_data")
            if not prima:
                return False
            # Normalizza stringhe (potrebbe essere "2024-03-15T00:00:00" o "2024-03-15")
            prima_str = prima[:10] if isinstance(prima, str) else str(prima)[:10]
            if stato_anagrafica == "nuovo":
                return prima_str >= soglia_date
            if stato_anagrafica == "storico":
                return prima_str < soglia_date
            return True
        
        suppliers = [s for s in suppliers if _match_stato(s)]
    
    suppliers.sort(key=lambda x: (x.get("ragione_sociale") or x.get("supplier_name") or "zzz").lower())
    
    if use_cache and not search and not metodo_pagamento and attivo is None and not advanced_filters_active:
        await cache.set(cache_key, suppliers, SUPPLIERS_CACHE_TTL)
    
    return suppliers[skip:skip+limit]


@router.get("/stats")
async def get_suppliers_stats() -> Dict[str, Any]:
    """Statistiche fornitori aggregate."""
    db = Database.get_db()
    
    total = await db[Collections.SUPPLIERS].count_documents({})
    active = await db[Collections.SUPPLIERS].count_documents({"attivo": True})
    
    pipeline = [
        {"$group": {"_id": "$metodo_pagamento", "count": {"$sum": 1}}}
    ]
    by_method = await db[Collections.SUPPLIERS].aggregate(pipeline).to_list(100)
    
    return {
        "totale": total,
        "attivi": active,
        "inattivi": total - active,
        "per_metodo_pagamento": {item["_id"] or "non_definito": item["count"] for item in by_method}
    }


@router.get("/scadenze")
async def get_payment_deadlines(days_ahead: int = Query(30, ge=1, le=365)) -> Dict[str, Any]:
    """Ritorna le fatture in scadenza nei prossimi N giorni."""
    db = Database.get_db()
    
    today = datetime.now(timezone.utc)
    deadline = today + timedelta(days=days_ahead)
    
    pipeline = [
        {
            "$match": {
                "pagato": {"$ne": True},
                "esclusa_da_cassa_banca": {"$ne": True},
                "data_scadenza": {"$gte": today.isoformat(), "$lte": deadline.isoformat()}
            }
        },
        {"$sort": {"data_scadenza": 1}},
        {"$project": {"_id": 0}}
    ]
    
    invoices = await db[Collections.INVOICES].aggregate(pipeline).to_list(1000)
    
    by_supplier = {}
    for inv in invoices:
        piva = inv.get("cedente_piva", "sconosciuto")
        if piva not in by_supplier:
            by_supplier[piva] = {"fornitore": inv.get("cedente_denominazione", ""), "fatture": [], "totale": 0}
        by_supplier[piva]["fatture"].append(inv)
        by_supplier[piva]["totale"] += inv.get("importo_totale", 0)
    
    critical_deadline = today + timedelta(days=7)
    critical = [inv for inv in invoices if inv.get("data_scadenza", "") <= critical_deadline.isoformat()]
    
    return {
        "totale_fatture": len(invoices),
        "totale_importo": sum(inv.get("importo_totale", 0) for inv in invoices),
        "critiche_7gg": len(critical),
        "per_fornitore": by_supplier,
        "fatture": invoices
    }


@router.get("/filtered")
async def list_suppliers_filtered(
    skip: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=1000),
    search: Optional[str] = Query(None, description="Ricerca per nome/ragione sociale/P.IVA"),
    esclude_magazzino: Optional[bool] = Query(None, description="True=esclusi da magazzino | False=popolano magazzino | None=tutti"),
    stato_anagrafica: Optional[str] = Query(None, pattern="^(nuovo|storico)$", description="nuovo | storico"),
    giorni_nuovo: int = Query(90, ge=1, le=3650),
    prodotto: Optional[str] = Query(None, description="Cerca fornitori che vendono questo prodotto (match su nome/descrizione magazzino)"),
    attivo: Optional[bool] = Query(None),
    metodo_pagamento: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """
    Endpoint dedicato con filtri avanzati per l'anagrafica fornitori.
    Restituisce anche i contatori delle varie categorie per popolare i badge UI.
    """
    # Riuso la logica di list_suppliers passando i filtri
    items = await list_suppliers(
        skip=skip,
        limit=limit,
        search=search,
        metodo_pagamento=metodo_pagamento,
        attivo=attivo,
        esclude_magazzino=esclude_magazzino,
        stato_anagrafica=stato_anagrafica,
        giorni_nuovo=giorni_nuovo,
        prodotto=prodotto,
        # La lista standard e' gia materializzata e invalidata ad ogni
        # modifica. Evitiamo di rileggere e riaggregare tutte le fatture a
        # ogni apertura della pagina; ricerca e filtri avanzati continuano a
        # bypassare automaticamente la cache in list_suppliers.
        use_cache=True
    )
    
    # Contatori COERENTI col filtro attivo: i badge devono descrivere il
    # risultato mostrato, non i totali globali (prima non cambiavano mai).
    total_all = len(items)
    total_popolano_magazzino = sum(1 for s in items if not s.get("esclude_magazzino"))
    total_esclusi_magazzino = sum(1 for s in items if s.get("esclude_magazzino"))
    total_attivi = sum(1 for s in items if s.get("attivo") is True)
    
    return {
        "items": items,
        "count": len(items),
        "filters_applied": {
            "search": search,
            "esclude_magazzino": esclude_magazzino,
            "stato_anagrafica": stato_anagrafica,
            "giorni_nuovo": giorni_nuovo,
            "prodotto": prodotto,
            "attivo": attivo,
            "metodo_pagamento": metodo_pagamento
        },
        "totali": {
            "totale_fornitori": total_all,
            "popolano_magazzino": total_popolano_magazzino,
            "esclusi_magazzino": total_esclusi_magazzino,
            "attivi": total_attivi
        },
        "pagination": {"skip": skip, "limit": limit}
    }


@router.get("/duplicati")
async def get_fornitori_duplicati(
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Gruppi di fornitori sospetti duplicati (stessa P.IVA/CF o nome simile)."""
    from app.services.fornitori_dedupe import trova_duplicati
    return await trova_duplicati()


@router.get("/duplicati/da-decidere")
async def get_fornitori_da_decidere(
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Sola lettura: i doppioni che il giro automatico non fonde, con candidati e motivo."""
    from app.services.fornitori_dedupe import da_decidere
    return await da_decidere()


@router.post("/duplicati/merge")
async def merge_fornitori_duplicati(
    target_id: str = Body(...),
    duplicate_id: str = Body(...),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Unifica duplicate_id dentro target_id (soft: il perdente resta, marcato `unificato`).

    Due P.IVA valide diverse sono rifiutate.
    """
    from app.services.fornitori_dedupe import merge_fornitori, _invalida_cache
    if not target_id or not duplicate_id:
        raise HTTPException(status_code=400, detail="target_id e duplicate_id sono obbligatori")
    try:
        esito = await merge_fornitori(target_id, duplicate_id, motivo="scelta del titolare")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await _invalida_cache()
    return esito


@router.post("/duplicati/auto-merge")
async def auto_merge_fornitori_duplicati(
    dry_run: bool = Query(True, description="True = solo anteprima, nessuna scrittura"),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Lo stesso giro dello scheduler: certi e probabili con un solo candidato."""
    from app.services.fornitori_dedupe import auto_merge_tutti
    return await auto_merge_tutti(dry_run=dry_run)


@router.get("/{supplier_id}")
async def get_supplier(supplier_id: str) -> Dict[str, Any]:
    """Dettaglio singolo fornitore."""
    db = Database.get_db()
    
    supplier = await db[Collections.SUPPLIERS].find_one(
        _filtro_fornitore(supplier_id),
        {"_id": 0}
    )
    
    if not supplier:
        raise HTTPException(status_code=404, detail="Fornitore non trovato")
    
    piva = supplier.get("partita_iva")
    if piva:
        invoices = await db[Collections.INVOICES].find(
            {"cedente_piva": piva},
            {"_id": 0}
        ).sort("data_fattura", -1).limit(20).to_list(20)
        supplier["fatture_recenti"] = invoices

    supplier.update(vista_scheda(supplier, await carica_decisioni(db)))
    supplier.update(vista_piva(supplier))
    return supplier


@router.post("")
async def create_supplier(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Crea un nuovo fornitore dal modale 'Nuovo Fornitore'.

    Endpoint mancante: il frontend faceva POST /api/suppliers ma esisteva
    solo la GET → 405 e impossibile creare fornitori dalla UI.
    """
    db = Database.get_db()

    nome = (data.get("ragione_sociale") or data.get("denominazione") or data.get("nome") or "").strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Ragione sociale obbligatoria")
    piva = (data.get("partita_iva") or data.get("piva") or "").strip()

    if piva:
        esistente = await db[Collections.SUPPLIERS].find_one(
            {"$or": [{"partita_iva": piva}, {"piva": piva}, {"vat_number": piva}]},
            {"_id": 0, "id": 1, "ragione_sociale": 1})
        if esistente:
            raise HTTPException(
                status_code=409,
                detail=f"Esiste già un fornitore con P.IVA {piva}: {esistente.get('ragione_sociale') or ''}")

    metodo = data.get("metodo_pagamento") or ""
    if metodo and metodo not in PAYMENT_METHODS:
        raise HTTPException(status_code=400, detail="Metodo pagamento non valido")

    now = datetime.now(timezone.utc).isoformat()
    nuovo = {
        "id": str(uuid.uuid4()),
        "ragione_sociale": nome,
        "denominazione": nome,
        "nome": nome,
        "partita_iva": piva,
        "piva": piva,
        "codice_fiscale": data.get("codice_fiscale") or piva,
        "indirizzo": data.get("indirizzo") or "",
        "cap": data.get("cap") or "",
        "comune": data.get("comune") or "",
        "provincia": data.get("provincia") or "",
        "nazione": data.get("nazione") or "IT",
        "email": data.get("email") or "",
        "telefono": data.get("telefono") or "",
        "iban": data.get("iban") or "",
        "metodo_pagamento": metodo,
        "metodo_pagamento_dal": now[:10] if metodo else None,
        "note": data.get("note") or "",
        "attivo": True,
        # niente `esclude_magazzino: False` d'ufficio: sarebbe una decisione che
        # nessuno ha preso (e nasconderebbe quella eventualmente gia' in Lotti)
        **({"esclude_magazzino": bool(data["esclude_magazzino"])}
           if isinstance(data.get("esclude_magazzino"), bool) else {}),
        "cessato": bool(data.get("cessato", False)),
        "esclude_cassa_banca": bool(
            data.get("esclude_cassa_banca", False) or data.get("cessato", False)
        ),
        "source": "manuale",
        "created_at": now,
        "updated_at": now,
    }
    await db[Collections.SUPPLIERS].insert_one({**nuovo})
    await cache.clear_pattern(SUPPLIERS_CACHE_KEY)
    return {"success": True, "supplier": nuovo, "id": nuovo["id"]}


@router.put("/{supplier_id}")
async def update_supplier(supplier_id: str, data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Aggiorna dati fornitore incluso metodo pagamento."""
    db = Database.get_db()
    
    data.pop("id", None)
    data.pop("partita_iva", None)
    data.pop("created_at", None)

    # Nel magazzino / fuori: mai scritto dal PUT generico. Se cambia davvero
    # passa dall'unico servizio (storico, proiezione su Lotti, fatture da prendere).
    cambio_magazzino = data.pop("esclude_magazzino", None)
    for _campo in ("magazzino_motivo", "magazzino_motivo_testo", "magazzino_deciso_il",
                   "magazzino_deciso_da", "storico_magazzino"):
        data.pop(_campo, None)
    if "esclude_cassa_banca" in data:
        data["esclude_cassa_banca"] = bool(data["esclude_cassa_banca"])
    if data.get("cessato") is True:
        # Un fornitore cessato resta fiscalmente valido, ma non deve generare
        # nuovi movimenti automatici in Cassa o Banca.
        data["esclude_cassa_banca"] = True
    
    metodo_configurato = False
    if "metodo_pagamento" in data:
        if data["metodo_pagamento"] not in PAYMENT_METHODS:
            raise HTTPException(status_code=400, detail="Metodo pagamento non valido")
        metodo_configurato = data["metodo_pagamento"] is not None and data["metodo_pagamento"] != ""

    # «Metodo valido dal»: data ISO scritta dal titolare (la UI la mostra gg/mm/aaaa).
    if data.get("metodo_pagamento_dal") in ("", None):
        data.pop("metodo_pagamento_dal", None)
    elif not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(data["metodo_pagamento_dal"])):
        raise HTTPException(status_code=400, detail="Data «metodo valido dal» non valida (aaaa-mm-gg)")
    else:
        try:
            datetime.strptime(str(data["metodo_pagamento_dal"]), "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Data «metodo valido dal» non valida")
    
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    supplier = await db[Collections.SUPPLIERS].find_one(
        _filtro_fornitore(supplier_id),
        {"partita_iva": 1, "piva": 1, "vat_number": 1, "id": 1,
         "denominazione": 1, "ragione_sociale": 1,
         "metodo_pagamento": 1, "metodo_pagamento_dal": 1,
         "esclude_cassa_banca": 1, "cessato": 1}
    )

    if not supplier:
        raise HTTPException(status_code=404, detail="Fornitore non trovato")

    # La data «dal» si stampa solo quando il metodo cambia davvero: prima ogni
    # salvataggio della scheda la riportava a oggi (BIG FOOD: «cassa dal
    # 30/09/2026» invece che dal 01/01/2025) e il metodo non valeva mai per il passato.
    metodo_cambiato = False
    if metodo_configurato:
        metodo_cambiato = (
            data["metodo_pagamento"] != supplier.get("metodo_pagamento")
            or ("metodo_pagamento_dal" in data
                and data["metodo_pagamento_dal"] != supplier.get("metodo_pagamento_dal"))
        )
        if "metodo_pagamento_dal" not in data and (
                metodo_cambiato or not supplier.get("metodo_pagamento_dal")):
            data["metodo_pagamento_dal"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    supplier_update: Dict[str, Any] = {"$set": data}
    if metodo_configurato and metodo_cambiato:
        # Una sola scrittura sul foglio Fornitori: prima il metodo e poi lo
        # storico venivano persistiti con due round-trip distinti.
        supplier_update["$push"] = {"storico_metodi_pagamento": {
            "metodo": data["metodo_pagamento"],
            "dal": data.get("metodo_pagamento_dal", datetime.now(timezone.utc).strftime("%Y-%m-%d")),
            "registrato_il": datetime.now(timezone.utc).isoformat(),
        }}

    result = await db[Collections.SUPPLIERS].update_one(
        _filtro_fornitore(supplier_id),
        supplier_update
    )
    
    # Se metodo cambiato, salva nello storico
    if metodo_configurato:
        from app.utils.iva_calculator import save_supplier_payment_method

        supplier_vat = (
            supplier.get("partita_iva") or supplier.get("piva")
            or supplier.get("vat_number") or ""
        )
        await save_supplier_payment_method(
            db,
            supplier_vat,
            supplier.get("denominazione") or supplier.get("ragione_sociale", ""),
            data["metodo_pagamento"],
            username="gestionale-fornitori",
        )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Fornitore non trovato")

    # La cache contiene anche metodo e flag magazzino: senza invalidazione la
    # modifica confermata poteva ricomparire col vecchio valore al refresh.
    await cache.clear_pattern(SUPPLIERS_CACHE_KEY)

    esclusione_sync = {"fatture_aggiornate": 0, "movimenti_auto_rimossi": 0}
    if "esclude_cassa_banca" in data:
        esclusione_sync = await _sincronizza_esclusione_cassa_banca(
            db, supplier, bool(data["esclude_cassa_banca"])
        )
    
    alerts_risolti = 0
    if metodo_configurato and supplier.get("partita_iva"):
        alert_result = await db["alerts"].update_many(
            {
                "tipo": "fornitore_senza_metodo_pagamento",
                "fornitore_piva": supplier["partita_iva"],
                "risolto": False
            },
            {"$set": {
                "risolto": True,
                "risolto_il": datetime.now(timezone.utc).isoformat(),
                "note_risoluzione": f"Metodo pagamento configurato: {data.get('metodo_pagamento')}"
            }}
        )
        alerts_risolti = alert_result.modified_count
    
    # ── RIPROCESSO PRIMA NOTA al cambio metodo:
    # "ogni volta che cambio il metodo deve riprocessare la prima nota per
    # spostare eventualmente le operazioni". In background le scritture
    # automatiche sul lato errato tornano provvisorie e vengono subito
    # reinstradate nel lato Cassa/Banca indicato dal nuovo metodo.
    if metodo_configurato:
        import asyncio as _asyncio

        async def _riprocessa_prima_nota():
            try:
                from app.routers.prima_nota_module.manutenzione import (
                    ripristina_provvisori_metodo_errato,
                )
                anno_corrente = datetime.now(timezone.utc).year
                esito = await ripristina_provvisori_metodo_errato(
                    dry_run=False, anno=anno_corrente, banca_non_riconciliate=False)
                # Qui seguiva il reinstradamento automatico in Cassa/Banca sul
                # solo metodo dell'anagrafica. E' stato tolto perche' confermava
                # un pagamento senza prova. Dal 15/09/2026 rispondeva 409, e il
                # 409 finiva dritto nell'except qui sotto: nessun errore in
                # pagina, nessuna riga scritta, nessuno che se ne accorgeva.
                # Resta il ripristino dei provvisori sul lato sbagliato, che
                # non afferma nessun pagamento.
                if esito.get("corretti"):
                    logger.info(
                        "Riprocesso prima nota dopo cambio metodo fornitore %s: %s corretti",
                        supplier_id, esito.get("corretti"))
            except Exception as e:
                logger.warning("Riprocesso prima nota dopo cambio metodo fallito: %s", e)

        _asyncio.create_task(_riprocessa_prima_nota())

    if isinstance(cambio_magazzino, bool):
        attuale = await db[Collections.SUPPLIERS].find_one(
            _filtro_fornitore(supplier_id), {"_id": 0})
        stato_ora, _ = (await carica_decisioni(db)).stato(
            (attuale or {}).get("partita_iva") or (attuale or {}).get("piva"),
            (attuale or {}).get("ragione_sociale") or (attuale or {}).get("denominazione"))
        if attuale and bool(stato_ora) != cambio_magazzino:
            await applica_magazzino(db, attuale, cambio_magazzino, MOTIVO_MODIFICA_SCHEDA,
                                    "", "scheda fornitore")
            await cache.clear_pattern(SUPPLIERS_CACHE_KEY)

    # ── EVENTO: pubblica sul bus unico (learning machine + risoluzione alert) ──
    try:
        from app.services.event_bus import propagate_event, EventTypes
        fornitore_aggiornato = await db[Collections.SUPPLIERS].find_one(
            _filtro_fornitore(supplier_id),
            {"_id": 0, "id": 1, "ragione_sociale": 1, "partita_iva": 1, "iban": 1, "metodo_pagamento": 1}
        )
        if fornitore_aggiornato:
            await propagate_event(EventTypes.FORNITORE_UPDATED, {
                "fornitore_id":    fornitore_aggiornato.get("id"),
                "ragione_sociale": fornitore_aggiornato.get("ragione_sociale", ""),
                "partita_iva":     fornitore_aggiornato.get("partita_iva", ""),
                "iban":            fornitore_aggiornato.get("iban", ""),
                "metodo_pagamento": fornitore_aggiornato.get("metodo_pagamento", ""),
            }, db, source_module="suppliers_update")
    except Exception as _ev:
        logger.debug(f"[SuppliersModule] Event Bus fornitore.updated: {_ev}")

    updated_supplier = await db[Collections.SUPPLIERS].find_one(
        _filtro_fornitore(supplier_id), {"_id": 0}
    )

    vista_aggiornata = _legacy_supplier_view(updated_supplier or {})
    vista_aggiornata.update(vista_scheda(vista_aggiornata, await carica_decisioni(db)))
    return {
        "message": "Fornitore aggiornato con successo",
        "supplier": vista_aggiornata,
        "alerts_risolti": alerts_risolti,
        **esclusione_sync,
    }


def _utente(admin: Dict[str, Any]) -> str:
    return str(admin.get("username") or admin.get("email") or admin.get("sub") or "admin")


async def _fornitore_o_404(db, supplier_id: str) -> Dict[str, Any]:
    fornitore = await db[Collections.SUPPLIERS].find_one(_filtro_fornitore(supplier_id), {"_id": 0})
    if not fornitore:
        raise HTTPException(status_code=404, detail="Fornitore non trovato")
    return fornitore


@router.get("/{supplier_id}/magazzino/anteprima")
async def anteprima_magazzino_fornitore(
    supplier_id: str,
    escludi: bool = Query(..., description="True = escludi dal magazzino, False = includi"),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Cosa cambia se il fornitore esce dal magazzino o ci rientra, coi conteggi
    veri e senza scrivere niente: da guardare PRIMA di confermare."""
    db = Database.get_db()
    return await anteprima_magazzino(db, await _fornitore_o_404(db, supplier_id), escludi)


@router.put("/{supplier_id}/magazzino")
async def imposta_magazzino_fornitore(
    supplier_id: str,
    data: Dict[str, Any] = Body(...),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Nel magazzino / fuori dal magazzino, a un tocco, con motivo scelto.

    Body: {escludi: bool, motivo: <chip>, motivo_testo?: str (solo con «altro»)}.
    Non cancella niente: le fatture restano contabili, i lotti gia' creati
    restano; includere accoda le fatture ancora da prendere in Lotti."""
    escludi = data.get("escludi")
    if not isinstance(escludi, bool):
        raise HTTPException(status_code=400, detail="escludi deve essere true o false")
    db = Database.get_db()
    fornitore = await _fornitore_o_404(db, supplier_id)
    try:
        esito = await applica_magazzino(
            db, fornitore, escludi, data.get("motivo"), data.get("motivo_testo") or "",
            _utente(_admin))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await cache.clear_pattern(SUPPLIERS_CACHE_KEY)
    aggiornato = _legacy_supplier_view(await _fornitore_o_404(db, supplier_id))
    aggiornato.update(vista_scheda(aggiornato, await carica_decisioni(db)))
    return {"success": True, **esito, "supplier": aggiornato}


@router.post("/{supplier_id}/applica-metodo-dal")
async def applica_metodo_fornitore_dal(
    supplier_id: str,
    dry_run: bool = Query(True, description="True = solo elenco e residui (difetto)"),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Il metodo Cassa del fornitore vale per le sue fatture dal «metodo valido dal».

    `dry_run` mostra le fatture che chiuderebbe, i residui, e quelle che non
    tocca (banca o assegno con prova, note di credito, rate, parziali). Senza
    `dry_run` parte in background con gli stessi motori della conferma in Cassa;
    il secondo giro non trova piu' niente da chiudere."""
    db = Database.get_db()
    fornitore = await _fornitore_o_404(db, supplier_id)
    esito = await applica_metodo_dal(db, fornitore, dry_run=dry_run)
    if not dry_run:
        await cache.clear_pattern(SUPPLIERS_CACHE_KEY)
    return esito


@router.get("/{supplier_id}/applica-metodo-dal/stato")
async def stato_metodo_fornitore_dal(
    supplier_id: str, _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    db = Database.get_db()
    return await stato_metodo_dal(db, await _fornitore_o_404(db, supplier_id))


@router.post("/magazzino/allinea")
async def allinea_magazzino_da_lotti(
    dry_run: bool = Query(True, description="True = solo anteprima (difetto)"),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Migrazione: dove l'anagrafica non ha deciso e Lotti si', vale Lotti."""
    db = Database.get_db()
    esito = await allinea_da_lotti(db, dry_run=dry_run)
    if not dry_run:
        await cache.clear_pattern(SUPPLIERS_CACHE_KEY)
    return esito


@router.post("/{supplier_id}/toggle-active")
async def toggle_supplier_active(supplier_id: str) -> Dict[str, Any]:
    """Attiva/disattiva fornitore con sync cross-system."""
    db = Database.get_db()

    supplier = await db[Collections.SUPPLIERS].find_one(
        _filtro_fornitore(supplier_id)
    )

    if not supplier:
        raise HTTPException(status_code=404, detail="Fornitore non trovato")

    new_status = not supplier.get("attivo", True)

    # Check fatture non pagate quando si disattiva
    fatture_non_pagate = 0
    if not new_status:
        piva = supplier.get("partita_iva", "")
        nome = supplier.get("denominazione") or supplier.get("ragione_sociale") or ""
        fatture_non_pagate = await db["invoices"].count_documents({
            "$or": [{"supplier_vat": piva}, {"cedente_denominazione": {"$regex": f"^{nome[:20]}", "$options": "i"}}],
            "status": {"$nin": ["paid", "pagata", "pagato"]}
        }) if (piva or nome) else 0

    await db[Collections.SUPPLIERS].update_one(
        {"_id": supplier["_id"]},
        {"$set": {"attivo": new_status, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )

    # Sync con l'app esterna collegata allo stesso DB: imposta "escluso"
    # in base ad attivo (campo letto dall'altra app — NON rimuovere).
    nome_fornitore = supplier.get("denominazione") or supplier.get("ragione_sociale") or ""
    if nome_fornitore:
        await db[Collections.SUPPLIERS].update_many(
            {"nome": {"$regex": f"^{nome_fornitore[:30]}", "$options": "i"}},
            {"$set": {"escluso": not new_status}}
        )

    await cache.clear_pattern(SUPPLIERS_CACHE_KEY)

    result = {
        "message": f"Fornitore {'attivato' if new_status else 'disattivato'}",
        "attivo": new_status,
    }
    if fatture_non_pagate > 0:
        result["warning"] = f"Attenzione: {fatture_non_pagate} fatture non pagate per questo fornitore"
        result["fatture_non_pagate"] = fatture_non_pagate

    return result


@router.delete("/{supplier_id}")
async def delete_supplier(supplier_id: str, force: bool = Query(False)) -> Dict[str, str]:
    """Elimina fornitore. Se force=False e ci sono fatture collegate, blocca."""
    db = Database.get_db()
    
    supplier = await db[Collections.SUPPLIERS].find_one(
        _filtro_fornitore(supplier_id)
    )
    
    if not supplier:
        raise HTTPException(status_code=404, detail="Fornitore non trovato")
    
    piva = supplier.get("partita_iva")
    if piva and not force:
        fatture_count = await db[Collections.INVOICES].count_documents({"cedente_piva": piva})
        if fatture_count > 0:
            raise HTTPException(
                status_code=400, 
                detail=f"Fornitore ha {fatture_count} fatture collegate. Usa force=true per eliminare comunque."
            )
    
    await db[Collections.SUPPLIERS].delete_one({"_id": supplier["_id"]})
    await cache.clear_pattern(SUPPLIERS_CACHE_KEY)

    # Pulisce sistema relazionale: annulla partite aperte residue + risolve alert
    # Solo se force=True (senza force l'operazione è già stata bloccata sopra se
    # ci sono fatture collegate). In ogni caso ripulisce le entità relazionali
    # orfane che puntano al fornitore cancellato.
    try:
        now = datetime.now(timezone.utc).isoformat()
        supplier_id_value = supplier.get("id") or supplier_id
        # Partite aperte collegate al fornitore come controparte
        r_pa = await db["partite_aperte"].update_many(
            {
                "controparte_id": supplier_id_value,
                "stato": {"$in": ["aperta", "parziale"]},
            },
            {"$set": {"stato": "annullata", "annullata_at": now,
                      "motivo_annullamento": f"Fornitore {supplier_id_value} eliminato"}}
        )
        # Alert aperti sull'entità fornitore
        r_al = await db["alerts"].update_many(
            {"entita_id": supplier_id_value, "stato": "aperto"},
            {"$set": {
                "stato": "risolto", "risolto": True,
                "resolved_at": now, "resolved_by": "cascade_delete_fornitore",
                "note_risoluzione": f"Fornitore {supplier_id_value} eliminato",
            }}
        )
        logger.info(
            f"Cascade fornitore {supplier_id_value}: partite={r_pa.modified_count}, "
            f"alerts={r_al.modified_count}"
        )
    except Exception:
        logger.exception(f"Errore pulizia relazionale per fornitore {supplier_id}")

    return {"message": "Fornitore eliminato"}


def _filtro_fornitore(supplier_id: str) -> dict:
    """Filtro repository tollerante per trovare un fornitore da un identificatore.

    L'identificatore può essere l'id applicativo oppure la P.IVA; i documenti
    legacy però tengono la P.IVA in 'piva' o 'vat_number' (e alcuni non hanno
    proprio il campo 'id'). Il lookup rigido {id, partita_iva} faceva
    rispondere 404 "Fornitore non trovato" al cambio metodo dalla lista
    "Fatture senza metodo" (segnalato dall'utente il 10/07).
    """
    condizioni = [{"id": supplier_id}]
    # 180 fornitori su 188 hanno l'id salvato come NUMERO (61), mentre dalla
    # pagina arriva come testo ("61"): il confronto testo/numero non trovava
    # nulla e ogni cambio metodo rispondeva 404 «Fornitore non trovato».
    testo = str(supplier_id or "").strip()
    if testo.isdigit():
        condizioni.append({"id": int(testo)})
    for v in _varianti_piva(supplier_id):
        condizioni += [{"partita_iva": v}, {"piva": v}, {"vat_number": v}, {"vat": v}]
    return {"$or": condizioni}


def _varianti_piva(piva: str) -> list:
    """Varianti con cui la stessa P.IVA può comparire sulle fatture.

    Le fatture elettroniche portano IdPaese+IdCodice: a seconda del canale
    di import la P.IVA può essere salvata con o senza prefisso 'IT' (o con
    spazi). Il confronto esatto faceva rispondere 'Nessuna fattura trovata'
    all'Estratto Fatture anche quando il contatore della lista ne vedeva
    (caso CASTAGNA SRL segnalato dall'utente il 10/07).
    """
    base = (piva or "").strip().upper().replace(" ", "")
    varianti = {base}
    if base.startswith("IT"):
        varianti.add(base[2:])
    else:
        varianti.add(f"IT{base}")
    return [v for v in varianti if v]


@router.get("/{supplier_id}/fatturato")
async def get_supplier_fatturato(
    supplier_id: str,
    anno: int = Query(..., ge=2015, le=2030)
) -> Dict[str, Any]:
    """Calcola il fatturato totale di un fornitore per un anno.

    Prima cercava le fatture sui campi "data_fattura"/"data" e "cedente_piva"/
    "supplier_vat": nessuno di questi è il nome reale usato dalla collection
    invoices (vedi get_fatture_fornitore sopra, l'endpoint dell'Estratto
    Fatture, che funziona correttamente) — il risultato era sempre 0€/0
    fatture anche quando l'Estratto Fatture per lo stesso fornitore/anno
    mostrava dati. Riallineato agli stessi campi/fallback.
    """
    db = Database.get_db()

    supplier = await db[Collections.SUPPLIERS].find_one(
        _filtro_fornitore(supplier_id),
        {"_id": 0}
    )

    if not supplier:
        raise HTTPException(status_code=404, detail="Fornitore non trovato")

    piva = supplier.get("partita_iva") or supplier.get("piva")
    nome_fornitore = supplier.get("ragione_sociale") or supplier.get("nome") or supplier.get("denominazione", "")
    if not piva:
        return {
            "fornitore": nome_fornitore,
            "anno": anno,
            "totale_fatturato": 0,
            "numero_fatture": 0
        }

    varianti = _varianti_piva(piva)
    query = {
        "$and": [
            dict(FILTRO_FATTURA_ATTIVA),
            {"$or": [
                {"fornitore_partita_iva": {"$in": varianti}},
                {"supplier_vat": {"$in": varianti}},
                {"cedente_piva": {"$in": varianti}},
            ]},
            {"$or": [
                {"data_documento": {"$regex": f"^{anno}"}},
                {"invoice_date": {"$regex": f"^{anno}"}},
            ]},
        ]
    }

    fatture = await db[Collections.INVOICES].find(query, {"_id": 0}).to_list(5000)

    mesi_nomi = ["", "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
                 "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]

    per_mese = {}
    totale_fatturato = 0.0
    fatture_pagate = 0
    fatture_non_pagate = 0
    importo_pagato = 0.0
    importo_non_pagato = 0.0

    for f in fatture:
        # Nota di credito in negativo: riduce il fatturato, non lo gonfia.
        importo = importo_documento_con_segno(f, _invoice_amount(f))
        data = str(f.get("invoice_date") or f.get("data_documento") or "")
        mese_num = int(data[5:7]) if len(data) >= 7 and data[5:7].isdigit() else None

        totale_fatturato += importo
        if e_pagata(f):
            fatture_pagate += 1
            importo_pagato += importo
        elif not e_annullata(f):
            fatture_non_pagate += 1
            importo_non_pagato += importo

        if mese_num and 1 <= mese_num <= 12:
            bucket = per_mese.setdefault(mese_num, {"totale": 0.0, "numero_fatture": 0})
            bucket["totale"] += importo
            bucket["numero_fatture"] += 1

    dettaglio_mensile = [
        {"mese": m, "mese_nome": mesi_nomi[m], "totale": round(v["totale"], 2), "numero_fatture": v["numero_fatture"]}
        for m, v in sorted(per_mese.items())
    ]

    return {
        "fornitore": nome_fornitore,
        "partita_iva": piva,
        "anno": anno,
        "totale_fatturato": round(totale_fatturato, 2),
        "numero_fatture": len(fatture),
        "fatture_pagate": fatture_pagate,
        "fatture_non_pagate": fatture_non_pagate,
        "importo_pagato": round(importo_pagato, 2),
        "importo_non_pagato": round(importo_non_pagato, 2),
        "dettaglio_mensile": dettaglio_mensile,
    }


@router.get("/{supplier_id}/iban-from-invoices")
async def get_supplier_iban_from_invoices(supplier_id: str) -> Dict[str, Any]:
    """Ritorna tutti gli IBAN trovati nelle fatture di un fornitore."""
    db = Database.get_db()
    
    supplier = await db[Collections.SUPPLIERS].find_one(
        _filtro_fornitore(supplier_id),
        {"_id": 0, "partita_iva": 1, "denominazione": 1, "ragione_sociale": 1, "iban": 1, "iban_lista": 1}
    )
    
    if not supplier:
        raise HTTPException(status_code=404, detail="Fornitore non trovato")
    
    piva = supplier.get("partita_iva")
    
    pipeline = [
        {
            "$match": {
                "cedente_piva": piva,
                "pagamento.iban": {"$exists": True, "$nin": ["", None]}
            }
        },
        {
            "$project": {
                "_id": 0,
                "iban": "$pagamento.iban",
                "data_fattura": 1,
                "numero_fattura": 1,
                "importo_totale": 1
            }
        },
        {"$sort": {"data_fattura": -1}}
    ]
    
    fatture_con_iban = await db[Collections.INVOICES].aggregate(pipeline).to_list(100)
    iban_unici = list(set([f.get("iban") for f in fatture_con_iban if f.get("iban")]))
    
    return {
        "fornitore": supplier.get("denominazione") or supplier.get("ragione_sociale", ""),
        "partita_iva": piva,
        "iban_principale": supplier.get("iban", ""),
        "iban_lista_salvata": supplier.get("iban_lista", []),
        "iban_da_fatture": iban_unici,
        "fatture_con_iban": fatture_con_iban[:20]
    }


@router.put("/{supplier_id}/metodo-pagamento")
async def update_supplier_payment_method(
    supplier_id: str,
    metodo_pagamento: str = Body(..., embed=True)
) -> Dict[str, Any]:
    """Alias di `PUT /{supplier_id}`: il metodo del fornitore ha un solo scrittore.

    Fino al 02/10/2026 questa rotta scriveva `metodo_pagamento` da sola, senza
    «metodo valido dal» ne' storico: un fornitore cambiato da qui non valeva
    mai per il passato (`applica-metodo-dal`) e la scheda non ne aveva
    traccia. Ora passa dallo stesso aggiornamento della scheda, che stampa
    `metodo_pagamento_dal` solo a un cambio vero e accoda lo storico.
    """
    metodo = (metodo_pagamento or "").lower().strip()
    # Sinonimi accettati dai vecchi chiamanti; il vocabolario e' PAYMENT_METHODS.
    metodo = {"cash": "cassa", "bank": "banca", "bon": "bonifico"}.get(metodo, metodo)
    if metodo not in PAYMENT_METHODS:
        raise HTTPException(
            status_code=400,
            detail=f"Metodo non valido. Ammessi: {sorted(PAYMENT_METHODS)}")

    esito = await update_supplier(supplier_id, {"metodo_pagamento": metodo})
    return {"success": True, "metodo_pagamento": metodo,
            "metodo_pagamento_dal": (esito.get("supplier") or {}).get("metodo_pagamento_dal"),
            "supplier": esito.get("supplier")}


@router.put("/{supplier_id}/nome")
async def update_supplier_nome(supplier_id: str, data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Aggiorna il nome/denominazione di un fornitore."""
    db = Database.get_db()
    
    denominazione = data.get("denominazione") or data.get("nome")
    if not denominazione:
        raise HTTPException(status_code=400, detail="Denominazione richiesta")
    
    result = await db[Collections.SUPPLIERS].update_one(
        _filtro_fornitore(supplier_id),
        {"$set": {
            "denominazione": denominazione,
            "ragione_sociale": denominazione,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    if result.matched_count == 0:
        nuovo = {
            "id": str(uuid.uuid4()),
            "partita_iva": supplier_id,
            "denominazione": denominazione,
            "ragione_sociale": denominazione,
            "metodo_pagamento": "bonifico",
            "attivo": True,
            "esclude_magazzino": True,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db[Collections.SUPPLIERS].insert_one(nuovo.copy())
        return {"success": True, "created": True, "denominazione": denominazione}
    
    return {"success": True, "updated": True, "denominazione": denominazione}


@router.get("/{supplier_id}/fatture")
async def get_fatture_fornitore(
    supplier_id: str,
    anno: Optional[int] = Query(None),
    data_da: Optional[str] = Query(None),
    data_a: Optional[str] = Query(None),
    importo_min: Optional[float] = Query(None),
    importo_max: Optional[float] = Query(None),
    tipo: Optional[str] = Query(None),
    limit: int = Query(100),
    skip: int = Query(0)
) -> Dict[str, Any]:
    """Restituisce l'estratto delle fatture di un fornitore."""
    db = Database.get_db()
    
    try:
        fornitore = await db[Collections.SUPPLIERS].find_one(
            _filtro_fornitore(supplier_id),
            {"_id": 0}
        )
        
        if not fornitore:
            raise HTTPException(status_code=404, detail="Fornitore non trovato")
        
        # Il DB usa sia 'piva' che 'partita_iva' come campo
        partita_iva = fornitore.get("partita_iva") or fornitore.get("piva")
        
        if not partita_iva:
            return {
                "fornitore": {"id": fornitore.get("id"), "partita_iva": None, "ragione_sociale": fornitore.get("nome", "")},
                "estratto": [],
                "totali": {"numero_documenti": 0, "importo_totale": 0},
                "pagination": {"total": 0, "limit": limit, "skip": skip}
            }

        # Filtro fornitore — deve sempre restare in AND con gli altri filtri.
        # Confronto tollerante al prefisso 'IT' (vedi _varianti_piva).
        varianti = _varianti_piva(partita_iva)
        supplier_filter = {
            "$or": [
                {"fornitore_partita_iva": {"$in": varianti}},
                {"supplier_vat": {"$in": varianti}},
                {"cedente_piva": {"$in": varianti}}
            ]
        }

        # Filtri aggiuntivi da combinare in $and. Le copie archiviate delle
        # fatture 2026 restano fuori: altrimenti ogni riga compare due volte.
        extra_filters = [dict(FILTRO_FATTURA_ATTIVA)]

        if anno:
            extra_filters.append({
                "$or": [
                    {"data_documento": {"$regex": f"^{anno}"}},
                    {"invoice_date": {"$regex": f"^{anno}"}}
                ]
            })

        if data_da:
            extra_filters.append({"$or": [
                {"data_documento": {"$gte": data_da}},
                {"invoice_date": {"$gte": data_da}}
            ]})
        if data_a:
            extra_filters.append({"$or": [
                {"data_documento": {"$lte": data_a}},
                {"invoice_date": {"$lte": data_a}}
            ]})
        if importo_min:
            extra_filters.append({"importo_totale": {"$gte": importo_min}})
        if importo_max:
            extra_filters.append({"importo_totale": {"$lte": importo_max}})

        if tipo and tipo != "tutti":
            # TD05 e' una nota di DEBITO: aumenta, non riduce. Le note di
            # credito sono TD04/TD08, costante unica.
            if tipo == "nota_credito":
                extra_filters.append({"tipo_documento": {"$in": list(TIPI_NOTA_CREDITO)}})
            elif tipo == "fattura":
                extra_filters.append({"tipo_documento": {"$nin": list(TIPI_NOTA_CREDITO)}})

        query = {"$and": [supplier_filter] + extra_filters}

        # `invoice_date` e' il campo canonico (regola 12): `data_documento`
        # manca sulle fatture che il motore IVA non ha toccato.
        fatture = await db["invoices"].find(query, {"_id": 0}).sort("invoice_date", -1).skip(skip).limit(limit).to_list(limit)
        totale = await db["invoices"].count_documents(query)
        
        estratto = []
        totale_importo = 0
        prove_per_fattura = await project_payment_evidence_many(db, fatture)
        for f, evidence in zip(fatture, prove_per_fattura):
            is_nc = is_credit_note(f)
            segno = -1 if is_nc else 1
            importo = importo_documento_con_segno(f, _invoice_amount(f))
            imponibile = segno * abs(float(f.get("imponibile") or f.get("importo_imponibile") or f.get("taxable_amount") or 0))
            iva = segno * abs(float(f.get("iva") or f.get("importo_iva") or f.get("vat_amount") or 0))
            tipo_doc = f.get("tipo_documento", "TD01")
            estratto.append({
                "id": f.get("id"),
                "data": f.get("invoice_date") or f.get("data_documento") or "",
                "numero": f.get("numero_documento") or f.get("invoice_number") or "",
                "importo_totale": importo,
                "imponibile": round(imponibile, 2),
                "iva": round(iva, 2),
                "tipo_documento": tipo_doc,
                "is_nota_credito": is_nc,
                "pagato": e_pagata(f),
                "riconciliato": f.get("riconciliato", False),
                "stato_pagamento": f.get("stato_pagamento", ""),
                "metodo_pagamento": f.get("metodo_pagamento") or f.get("metodo_pagamento_effettivo") or fornitore.get("metodo_pagamento") or "-",
                "data_pagamento": f.get("data_pagamento", ""),
                "document_role": "credit_note" if is_credit_note(f) else "invoice",
                **allocation_summary(f),
                "assegni_collegati": f.get("assegni_collegati") or [],
                "movimento_bancario_id": f.get("movimento_bancario_id"),
                "payment_evidence": evidence,
            })
            totale_importo += importo
        
        return {
            "fornitore": {
                "id": fornitore.get("id"),
                "partita_iva": partita_iva,
                "ragione_sociale": fornitore.get("ragione_sociale") or fornitore.get("nome") or fornitore.get("denominazione", "")
            },
            "estratto": estratto,
            "totali": {
                "numero_documenti": totale,
                "importo_totale": round(totale_importo, 2)
            },
            "pagination": {"total": totale, "limit": limit, "skip": skip}
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore recupero fatture fornitore {supplier_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e



@router.get("/{supplier_id}/dati-da-fatture")
async def get_dati_da_fatture(supplier_id: str) -> Dict[str, Any]:
    """Estrae i dati anagrafici del fornitore dalla sua prima fattura XML disponibile."""
    db = Database.get_db()

    fornitore = await db[Collections.SUPPLIERS].find_one(
        _filtro_fornitore(supplier_id),
        {"_id": 0}
    )
    if not fornitore:
        raise HTTPException(status_code=404, detail="Fornitore non trovato")

    # Prova entrambi i campi PIVA (il DB ha sia 'piva' troncata che 'partita_iva' completa)
    piva_options = list(filter(None, [
        fornitore.get("partita_iva"),
        fornitore.get("piva")
    ]))
    if not piva_options:
        return {"trovato": False, "dati": {}}

    piva = piva_options[0]  # priorità a partita_iva (campo completo)

    # Cerca nella collection invoices i dati del cedente/fornitore
    invoice = await db["invoices"].find_one(
        {"$or": [
            {"cedente_piva": {"$in": piva_options}},
            {"fornitore_partita_iva": {"$in": piva_options}},
            {"supplier_vat": {"$in": piva_options}}
        ]},
        {"_id": 0}
    )

    if not invoice:
        return {"trovato": False, "dati": {}}

    dati = {
        "ragione_sociale": (
            invoice.get("cedente_denominazione") or
            invoice.get("supplier_name") or
            fornitore.get("nome") or ""
        ),
        "partita_iva": invoice.get("cedente_piva") or piva or "",
        "codice_fiscale": invoice.get("cedente_codice_fiscale") or "",
        "indirizzo": (
            invoice.get("cedente_indirizzo") or
            invoice.get("cedente_sede_indirizzo") or ""
        ),
        "cap": (
            invoice.get("cedente_cap") or
            invoice.get("cedente_sede_cap") or ""
        ),
        "comune": (
            invoice.get("cedente_comune") or
            invoice.get("cedente_sede_comune") or ""
        ),
        "provincia": (
            invoice.get("cedente_provincia") or
            invoice.get("cedente_sede_provincia") or ""
        ),
        "nazione": (
            invoice.get("cedente_nazione") or
            invoice.get("cedente_sede_nazione") or "IT"
        ),
    }

    return {"trovato": True, "dati": dati}
