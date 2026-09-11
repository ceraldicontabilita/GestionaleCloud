"""
Centri di Costo e Utile Obiettivo Router
Sistema di contabilità analitica per bar-pasticceria
"""
from fastapi import APIRouter, HTTPException, Query, Body
from typing import Dict, Any, List, Optional
from datetime import datetime, date, timezone
from app.database import Database, Collections

router = APIRouter()

# ============== CENTRI DI COSTO ==============

# Struttura centri di costo per i 4 settori operativi reali (scelta utente):
# Bar/Caffetteria, Pasticceria, Gelateria, Rosticceria.
CDC_STANDARD = {
    # Centri Operativi (generano ricavi) — i 4 settori reali
    "CDC-01": {"nome": "BAR / CAFFETTERIA", "tipo": "operativo", "descrizione": "Vendita caffè, bevande calde/fredde, snack"},
    "CDC-02": {"nome": "PASTICCERIA", "tipo": "operativo", "descrizione": "Produzione e vendita dolci, torte, pasticcini"},
    "CDC-03": {"nome": "GELATERIA", "tipo": "operativo", "descrizione": "Produzione e vendita gelato, sorbetti, semifreddi"},
    "CDC-04": {"nome": "ROSTICCERIA", "tipo": "operativo", "descrizione": "Produzione e vendita gastronomia calda/fredda, tavola calda"},

    # Centri di Supporto (costi da ribaltare)
    "CDC-90": {"nome": "PERSONALE", "tipo": "supporto", "descrizione": "Costi del personale da ribaltare"},
    "CDC-91": {"nome": "AMMINISTRAZIONE", "tipo": "supporto", "descrizione": "Costi amministrativi e gestionali"},
    "CDC-92": {"nome": "MARKETING", "tipo": "supporto", "descrizione": "Pubblicità, promozioni, social"},

    # Centro Struttura (costi fissi)
    "CDC-99": {"nome": "COSTI GENERALI / STRUTTURA", "tipo": "struttura", "descrizione": "Affitto, utenze, manutenzione"}
}

# Elenco dei centri operativi (i settori che generano ricavi), usato dal
# ribaltamento e dai margini.
CDC_OPERATIVI = ("CDC-01", "CDC-02", "CDC-03", "CDC-04")
# Centri i cui costi vengono ribaltati sui settori operativi (supporto + struttura).
CDC_DA_RIBALTARE = ("CDC-90", "CDC-91", "CDC-92", "CDC-99")

# Mapping automatico categoria_contabile → centro di costo (4 settori reali).
# Le materie prime condivise sono assegnate al settore che ne è consumatore
# prevalente; casi ambigui puntano al settore più probabile (rivedibile).
CATEGORIA_TO_CDC = {
    # BAR / CAFFETTERIA
    "caffe": "CDC-01",
    "bevande": "CDC-01",
    "bevande_alcoliche": "CDC-01",
    "birra": "CDC-01",
    "vino": "CDC-01",
    "bibite": "CDC-01",
    "snack": "CDC-01",

    # PASTICCERIA (dolci + materie prime prevalenti da pasticceria)
    "pasticceria": "CDC-02",
    "dolci": "CDC-02",
    "torte": "CDC-02",
    "farine": "CDC-02",
    "zucchero": "CDC-02",
    "uova": "CDC-02",
    "cioccolato": "CDC-02",
    "latticini": "CDC-02",

    # GELATERIA
    "gelato": "CDC-03",
    "frutta": "CDC-03",

    # ROSTICCERIA (gastronomia + materie prime salate + confezionamento asporto)
    "gastronomia": "CDC-04",
    "salumi": "CDC-04",
    "carne": "CDC-04",
    "pesce": "CDC-04",
    "alimentari": "CDC-04",
    "surgelati": "CDC-04",
    "imballaggi": "CDC-04",
    "packaging": "CDC-04",
    "delivery": "CDC-04",

    # PERSONALE
    "stipendi": "CDC-90",
    "contributi": "CDC-90",
    "tfr": "CDC-90",
    
    # AMMINISTRAZIONE
    "consulenze": "CDC-91",
    "commercialista": "CDC-91",
    "software": "CDC-91",
    "canoni_abbonamenti": "CDC-91",
    
    # MARKETING
    "pubblicita": "CDC-92",
    "marketing": "CDC-92",
    
    # COSTI GENERALI
    "affitto": "CDC-99",
    "utenze_elettricita": "CDC-99",
    "utenze_gas": "CDC-99",
    "utenze_acqua": "CDC-99",
    "telefonia": "CDC-99",
    "manutenzione": "CDC-99",
    "pulizia": "CDC-99",
    "assicurazioni": "CDC-99",
    "noleggio_auto": "CDC-99",
    "carburante": "CDC-99",
    "ferramenta": "CDC-99",
    "materiale_edile": "CDC-99"
}

# Mapping fornitore → centro di costo (per fornitori specifici)
FORNITORE_TO_CDC = {
    "KIMBO": "CDC-01",  # Caffè
    "LAVAZZA": "CDC-01",
    "ILLY": "CDC-01",
    "COCA": "CDC-01",
    "PEPSI": "CDC-01",
    "PERONI": "CDC-01",
    "HEINEKEN": "CDC-01",
    "ENEL": "CDC-99",  # Utenze
    "EDISON": "CDC-99",
    "ENI": "CDC-99",
    "TELECOM": "CDC-99",
    "TIM": "CDC-99",
    "VODAFONE": "CDC-99",
    "ARVAL": "CDC-99",  # Noleggio auto
    "LEASYS": "CDC-99",
    "ALD": "CDC-99"
}


@router.get("")
async def list_centri_costo() -> List[Dict[str, Any]]:
    """Lista tutti i centri di costo con statistiche."""
    db = Database.get_db()
    
    # Verifica se esistono nel DB, altrimenti usa standard
    centri = await db["centri_costo"].find({}, {"_id": 0}).to_list(100)
    
    if not centri:
        # Inizializza con struttura standard
        centri = []
        for codice, dati in CDC_STANDARD.items():
            centro = {
                "codice": codice,
                **dati,
                "attivo": True,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            centri.append(centro.copy())  # Usa copy() per evitare che insert_many modifichi
        
        # Salva nel DB (crea copie per evitare mutazione con _id)
        centri_to_insert = [c.copy() for c in centri]
        await db["centri_costo"].insert_many(centri_to_insert)
    
    # Aggiungi statistiche per ogni centro
    for centro in centri:
        codice = centro["codice"]
        
        # Conta fatture associate
        fatture_count = await db[Collections.INVOICES].count_documents({"centro_costo": codice})
        fatture_totale = 0
        
        pipeline = [
            {"$match": {"centro_costo": codice}},
            {"$group": {"_id": None, "totale": {"$sum": "$total_amount"}}}
        ]
        result = await db[Collections.INVOICES].aggregate(pipeline).to_list(1)
        if result:
            fatture_totale = result[0].get("totale", 0)
        
        centro["fatture_count"] = fatture_count
        centro["fatture_totale"] = round(fatture_totale, 2)
    
    return centri


@router.post("")
async def create_centro_costo(data: Dict[str, Any] = Body(...)) -> Dict[str, str]:
    """Crea nuovo centro di costo."""
    db = Database.get_db()
    
    codice = data.get("codice")
    if not codice:
        raise HTTPException(status_code=400, detail="Codice centro di costo obbligatorio")
    
    # Verifica duplicato
    existing = await db["centri_costo"].find_one({"codice": codice})
    if existing:
        raise HTTPException(status_code=400, detail=f"Centro di costo {codice} già esistente")
    
    centro = {
        "codice": codice,
        "nome": data.get("nome", codice),
        "tipo": data.get("tipo", "operativo"),
        "descrizione": data.get("descrizione", ""),
        "attivo": True,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db["centri_costo"].insert_one(centro.copy())
    return {"message": f"Centro di costo {codice} creato", "codice": codice}


@router.get("/mapping-categorie")
async def get_mapping_categorie() -> Dict[str, Any]:
    """Restituisce il mapping categoria → centro di costo."""
    return {
        "categoria_to_cdc": CATEGORIA_TO_CDC,
        "fornitore_to_cdc": FORNITORE_TO_CDC,
        "cdc_standard": CDC_STANDARD
    }


@router.post("/assegna-cdc-fatture")
async def assegna_cdc_fatture(
    anno: Optional[int] = Query(None),
    force: bool = Query(False, description="Sovrascrive assegnazioni esistenti")
) -> Dict[str, Any]:
    """
    Assegna automaticamente i centri di costo alle fatture
    basandosi su categoria_contabile e fornitore.
    """
    db = Database.get_db()
    
    query = {}
    if anno:
        query["invoice_date"] = {"$regex": f"^{anno}"}
    
    if not force:
        query["centro_costo"] = {"$exists": False}
    
    fatture = await db[Collections.INVOICES].find(query, {"_id": 1, "categoria_contabile": 1, "supplier_name": 1}).to_list(10000)
    
    updated = 0
    stats = {}
    
    for fatt in fatture:
        cdc = None
        
        # 1. Prima prova con categoria
        categoria = fatt.get("categoria_contabile", "").lower()
        if categoria in CATEGORIA_TO_CDC:
            cdc = CATEGORIA_TO_CDC[categoria]
        
        # 2. Se non trovato, prova con fornitore
        if not cdc:
            supplier = (fatt.get("supplier_name") or "").upper()
            for key, value in FORNITORE_TO_CDC.items():
                if key in supplier:
                    cdc = value
                    break
        
        # 3. Nessun fallback inventato: se categoria e fornitore non
        # identificano un centro in modo esplicito, la fattura resta da
        # verificare invece di essere forzata in CDC-99.
        if not cdc:
            await db[Collections.INVOICES].update_one(
                {"_id": fatt["_id"]},
                {"$set": {
                    "cdc_auto_assigned": False,
                    "cdc_requires_review": True,
                }, "$unset": {"centro_costo": ""}}
            )
            stats["DA_VERIFICARE"] = stats.get("DA_VERIFICARE", 0) + 1
            continue

        # Aggiorna fattura soltanto quando il mapping è deterministico.
        await db[Collections.INVOICES].update_one(
            {"_id": fatt["_id"]},
            {"$set": {
                "centro_costo": cdc,
                "cdc_auto_assigned": True,
                "cdc_requires_review": False,
            }}
        )
        updated += 1
        stats[cdc] = stats.get(cdc, 0) + 1
    
    return {
        "message": f"Assegnati {updated} centri di costo",
        "fatture_aggiornate": updated,
        "distribuzione": stats
    }


# ============== UTILE OBIETTIVO ==============

@router.get("/utile-obiettivo")
async def get_utile_obiettivo(anno: int = Query(...)) -> Dict[str, Any]:
    """
    Recupera il target di utile e calcola lo stato attuale.
    """
    db = Database.get_db()
    
    # Recupera target
    target = await db["utile_obiettivo"].find_one({"anno": anno}, {"_id": 0})
    
    if not target:
        # Default se non configurato
        target = {
            "anno": anno,
            "utile_target_annuo": 50000,
            "margine_medio_atteso": 0.35,
            "giorni_lavorativi_anno": 300,
            "configurato": False
        }
    
    # Calcola dati reali usando lo stesso Conto Economico canonico della pagina
    # Bilancio: ricavi imponibili da corrispettivi, costi imponibili al netto
    # delle note di credito e dei documenti eliminati/archiviati.
    from app.routers.accounting.bilancio import get_conto_economico
    conto_economico = await get_conto_economico(anno=anno, mese=None)
    ricavi_totali = conto_economico["ricavi"]["totale_ricavi"]
    costi_totali = conto_economico["costi"]["totale_costi"]
    
    # Calcoli
    utile_corrente = ricavi_totali - costi_totali
    utile_target = target.get("utile_target_annuo", 50000)
    scostamento = utile_corrente - utile_target
    
    # Giorni trascorsi nell'anno
    oggi = date.today()
    if oggi.year == anno:
        giorni_trascorsi = (oggi - date(anno, 1, 1)).days + 1
    else:
        giorni_trascorsi = 365
    
    giorni_lavorativi = target.get("giorni_lavorativi_anno", 300)
    giorni_lavorativi_trascorsi = int(giorni_trascorsi * (giorni_lavorativi / 365))
    giorni_rimanenti = giorni_lavorativi - giorni_lavorativi_trascorsi
    
    # Utile target proporzionato
    utile_target_ad_oggi = (utile_target / giorni_lavorativi) * giorni_lavorativi_trascorsi
    scostamento_ad_oggi = utile_corrente - utile_target_ad_oggi
    percentuale_target_annuo = (
        (utile_corrente / utile_target) * 100 if utile_target > 0 else 0
    )
    gap_target_annuo = max(utile_target - utile_corrente, 0)
    surplus_target_annuo = max(utile_corrente - utile_target, 0)
    
    # Proiezione fine anno
    if giorni_trascorsi > 0:
        utile_proiezione = (utile_corrente / giorni_trascorsi) * 365
    else:
        utile_proiezione = 0
    
    # Calcolo azioni necessarie
    margine_medio = target.get("margine_medio_atteso", 0.35)
    
    if scostamento < 0:
        # Siamo sotto target
        ricavi_necessari = abs(scostamento) / margine_medio
        costi_da_tagliare = abs(scostamento)
    else:
        ricavi_necessari = 0
        costi_da_tagliare = 0
    
    return {
        "anno": anno,
        "target": {
            "utile_target_annuo": utile_target,
            "utile_target_ad_oggi": round(utile_target_ad_oggi, 2),
            "margine_medio_atteso": margine_medio,
            "giorni_lavorativi_anno": giorni_lavorativi,
            "configurato": target.get("configurato", False)
        },
        "reale": {
            "ricavi_totali": round(ricavi_totali, 2),
            "costi_totali": round(costi_totali, 2),
            "utile_corrente": round(utile_corrente, 2),
            "margine_reale": round(utile_corrente / ricavi_totali, 4) if ricavi_totali > 0 else 0
        },
        "analisi": {
            "scostamento_target": round(scostamento, 2),
            "scostamento_ad_oggi": round(scostamento_ad_oggi, 2),
            "stato": "IN_TARGET" if scostamento_ad_oggi >= 0 else "SOTTO_TARGET",
            "percentuale_raggiungimento": round((utile_corrente / utile_target_ad_oggi) * 100, 1) if utile_target_ad_oggi > 0 else 0,
            "percentuale_target_annuo": round(percentuale_target_annuo, 1),
            "gap_target_annuo": round(gap_target_annuo, 2),
            "surplus_target_annuo": round(surplus_target_annuo, 2),
            "stato_target_annuo": "RAGGIUNTO" if gap_target_annuo == 0 else "DA_RAGGIUNGERE",
            "utile_proiezione_fine_anno": round(utile_proiezione, 2)
        },
        "tempo": {
            "giorni_trascorsi": giorni_trascorsi,
            "giorni_lavorativi_trascorsi": giorni_lavorativi_trascorsi,
            "giorni_rimanenti": giorni_rimanenti
        },
        "azioni_suggerite": {
            "ricavi_aggiuntivi_necessari": round(ricavi_necessari, 2) if scostamento < 0 else 0,
            "costi_da_ridurre": round(costi_da_tagliare, 2) if scostamento < 0 else 0,
            "utile_giornaliero_necessario": round(abs(scostamento) / max(giorni_rimanenti, 1), 2) if scostamento < 0 else 0
        }
    }


@router.post("/utile-obiettivo")
async def set_utile_obiettivo(data: Dict[str, Any] = Body(...)) -> Dict[str, str]:
    """Imposta il target di utile per un anno."""
    db = Database.get_db()
    
    anno = data.get("anno")
    if not anno:
        raise HTTPException(status_code=400, detail="Anno obbligatorio")
    
    target = {
        "anno": anno,
        "utile_target_annuo": data.get("utile_target_annuo", 50000),
        "utile_target_mensile": data.get("utile_target_annuo", 50000) / 12,
        "margine_medio_atteso": data.get("margine_medio_atteso", 0.35),
        "giorni_lavorativi_anno": data.get("giorni_lavorativi_anno", 300),
        "note": data.get("note", ""),
        "configurato": True,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db["utile_obiettivo"].update_one(
        {"anno": anno},
        {"$set": target},
        upsert=True
    )
    
    return {"message": f"Target utile {anno} impostato: €{target['utile_target_annuo']:,.2f}"}


@router.get("/utile-obiettivo/suggerimenti")
async def get_suggerimenti_utile(anno: int = Query(...)) -> Dict[str, Any]:
    """
    Genera suggerimenti intelligenti per raggiungere l'utile obiettivo.
    Motore decisionale stile TeamSystem.
    """
    db = Database.get_db()
    
    # Recupera dati base
    stato = await get_utile_obiettivo(anno)
    
    suggerimenti = []
    priorita = "NORMALE"
    
    scostamento = stato["analisi"]["scostamento_ad_oggi"]
    ricavi = stato["reale"]["ricavi_totali"]
    costi = stato["reale"]["costi_totali"]
    
    if scostamento < 0:
        priorita = "ALTA" if abs(scostamento) > 5000 else "MEDIA"
        
        # Suggerimenti per recuperare
        ricavi_necessari = stato["azioni_suggerite"]["ricavi_aggiuntivi_necessari"]
        costi_da_ridurre = stato["azioni_suggerite"]["costi_da_ridurre"]
        
        suggerimenti.append({
            "tipo": "CRITICO",
            "messaggio": f"Per raggiungere l'utile target mancano €{abs(scostamento):,.2f}",
            "azione": None
        })
        
        suggerimenti.append({
            "tipo": "OPZIONE_A",
            "messaggio": f"Aumentare i ricavi di €{ricavi_necessari:,.2f} (con margine {stato['target']['margine_medio_atteso']*100:.0f}%)",
            "azione": "incremento_vendite"
        })
        
        suggerimenti.append({
            "tipo": "OPZIONE_B",
            "messaggio": f"Ridurre i costi di €{costi_da_ridurre:,.2f}",
            "azione": "riduzione_costi"
        })
        
        # Analisi per centro di costo
        cdc_pipeline = [
            {"$match": {"invoice_date": {"$regex": f"^{anno}"}, "centro_costo": {"$exists": True}}},
            {"$group": {"_id": "$centro_costo", "totale": {"$sum": "$total_amount"}}},
            {"$sort": {"totale": -1}}
        ]
        cdc_costi = await db[Collections.INVOICES].aggregate(cdc_pipeline).to_list(10)
        
        if cdc_costi:
            top_cdc = cdc_costi[0]
            cdc_nome = CDC_STANDARD.get(top_cdc["_id"], {}).get("nome", top_cdc["_id"])
            suggerimenti.append({
                "tipo": "ANALISI_CDC",
                "messaggio": f"Il centro di costo più costoso è {cdc_nome} con €{top_cdc['totale']:,.2f}",
                "azione": "analizza_cdc",
                "cdc": top_cdc["_id"]
            })
    
    else:
        priorita = "BASSA"
        suggerimenti.append({
            "tipo": "POSITIVO",
            "messaggio": f"Sei in linea con l'obiettivo! Surplus di €{scostamento:,.2f}",
            "azione": None
        })
        
        # Proiezione
        proiezione = stato["analisi"]["utile_proiezione_fine_anno"]
        target = stato["target"]["utile_target_annuo"]
        if proiezione > target:
            suggerimenti.append({
                "tipo": "PROIEZIONE",
                "messaggio": f"Proiezione fine anno: €{proiezione:,.2f} (+{((proiezione/target)-1)*100:.1f}% vs target)",
                "azione": None
            })
    
    return {
        "anno": anno,
        "priorita": priorita,
        "suggerimenti": suggerimenti,
        "stato_corrente": stato["analisi"]["stato"],
        "percentuale_raggiungimento": stato["analisi"]["percentuale_raggiungimento"]
    }


def _cdc_operativo_da_learning(codice: str, nome: str = "") -> Optional[str]:
    """Traduce solo categorie learning con significato operativo esplicito.

    Nessun fallback inventato: categorie non mappabili restano DA_VERIFICARE.
    """
    codice = str(codice or "")
    nome_norm = str(nome or "").casefold()
    if codice in CDC_STANDARD:
        return codice
    prefissi = (
        (("1.1_", "1.2_", "1.6_"), "CDC-01"),
        (("1.3_", "1.4_"), "CDC-02"),
        (("1.5_",), "CDC-03"),
        (("1.8_", "13.1_"), "CDC-04"),
        (("4.", "4_"), "CDC-90"),
    )
    for gruppi, cdc in prefissi:
        if codice.startswith(gruppi):
            return cdc
    if any(k in nome_norm for k in ("marketing", "pubblicit", "promozion", "social")):
        return "CDC-92"
    if any(k in nome_norm for k in ("commercialista", "consulenza", "software", "amministr", "cancelleria")):
        return "CDC-91"
    if any(k in nome_norm for k in (
        "energia", "gas", "acqua", "rifiuti", "affitto", "locazione", "condominio",
        "manutenzione", "pulizia", "assicur", "noleggio", "carburante", "telefon",
    )):
        return "CDC-99"
    return None


def _firma_riga(descrizione: str, importo: float):
    return (" ".join(str(descrizione or "").casefold().split()), round(float(importo or 0), 2))


async def _costi_cdc_da_righe_xml(db, anno: int) -> Dict[str, Any]:
    """Costi analitici da classificazioni riga XML, al netto dei cespiti.

    Le righe dubbie o con vocabolario non traducibile non vengono forzate in
    CDC-99: restano esplicitamente DA_VERIFICARE.
    """
    data_start = f"{anno}-01-01"
    data_end = f"{anno}-12-31"
    fatture = await db[Collections.INVOICES].find({
        "status": {"$nin": ["deleted", "archived"]},
        "$or": [
            {"invoice_date": {"$gte": data_start, "$lte": data_end}},
            {"data_ricezione": {"$gte": data_start, "$lte": data_end}},
        ],
    }, {"_id": 0}).to_list(10000)
    cespiti = await db["cespiti"].find({
        "provenienza": "fattura_xml",
        "data_acquisto": {"$gte": data_start, "$lte": data_end},
    }, {"_id": 0, "fattura_id": 1, "descrizione": 1, "valore_acquisto": 1}).to_list(10000)

    asset_signatures = {}
    asset_totals = {}
    for cespite in cespiti:
        fid = str(cespite.get("fattura_id") or "")
        if not fid:
            continue
        valore = float(cespite.get("valore_acquisto") or 0)
        sig = (fid, *_firma_riga(cespite.get("descrizione"), valore))
        asset_signatures[sig] = asset_signatures.get(sig, 0) + 1
        asset_totals[fid] = asset_totals.get(fid, 0.0) + valore

    costi = {cdc: 0.0 for cdc in CDC_STANDARD}
    fatture_per_cdc = {cdc: set() for cdc in CDC_STANDARD}
    da_verificare = 0.0
    righe_da_verificare = 0
    righe_usate = 0
    cespiti_esclusi = 0.0

    for fattura in fatture:
        fid = str(fattura.get("id") or fattura.get("invoice_key") or "")
        segno = -1.0 if fattura.get("tipo_documento") in ("TD04", "TD08") else 1.0
        righe = fattura.get("classificazioni_righe") or []
        if righe:
            for riga in righe:
                importo = float(riga.get("imponibile") or 0)
                sig = (fid, *_firma_riga(riga.get("descrizione"), importo))
                if asset_signatures.get(sig, 0) > 0:
                    asset_signatures[sig] -= 1
                    cespiti_esclusi += importo
                    continue
                cdc = None if riga.get("richiede_verifica") else _cdc_operativo_da_learning(
                    riga.get("centro_costo_id"), riga.get("centro_costo_nome")
                )
                if not cdc:
                    da_verificare += segno * importo
                    righe_da_verificare += 1
                    continue
                costi[cdc] += segno * importo
                fatture_per_cdc[cdc].add(fid)
                righe_usate += 1
            continue

        # Fallback solo per fatture legacy con CDC di testata esplicito e non
        # marcato da verificare. La quota cespite viene comunque esclusa.
        imponibile = float(fattura.get("imponibile") or 0)
        if not imponibile:
            imponibile = float(fattura.get("total_amount") or 0) - float(fattura.get("iva") or 0)
        imponibile -= float(asset_totals.get(fid, 0) or 0)
        cdc = fattura.get("centro_costo")
        if cdc in CDC_STANDARD and not fattura.get("cdc_requires_review"):
            costi[cdc] += segno * imponibile
            fatture_per_cdc[cdc].add(fid)
        else:
            da_verificare += segno * imponibile
            righe_da_verificare += 1

    return {
        "costi": {k: round(v, 2) for k, v in costi.items()},
        "fatture_count": {k: len(v) for k, v in fatture_per_cdc.items()},
        "da_verificare": round(da_verificare, 2),
        "righe_da_verificare": righe_da_verificare,
        "righe_usate": righe_usate,
        "cespiti_esclusi": round(cespiti_esclusi, 2),
        "fonte": "classificazioni_righe_xml",
    }


@router.get("/utile-obiettivo/per-cdc")
async def get_utile_per_cdc(anno: int = Query(...)) -> Dict[str, Any]:
    """Analisi utile/margine per CDC basata sulle singole righe XML."""
    db = Database.get_db()
    analitica = await _costi_cdc_da_righe_xml(db, anno)
    from app.routers.accounting.bilancio import get_conto_economico
    ce = await get_conto_economico(anno=anno, mese=None)
    ricavi_totali = float(ce["ricavi"]["totale_ricavi"] or 0)

    costi_dict = analitica["costi"]
    costi_totali_validati = sum(costi_dict.values())
    report = []
    for codice, costo in sorted(costi_dict.items(), key=lambda item: -abs(item[1])):
        if abs(costo) < 0.005:
            continue
        info = CDC_STANDARD.get(codice, {"nome": codice, "tipo": "altro"})
        peso_costi = costo / costi_totali_validati if costi_totali_validati > 0 else 0
        ricavi_cdc = ricavi_totali * peso_costi * 1.5 if info.get("tipo") == "operativo" else 0
        margine = ricavi_cdc - costo
        report.append({
            "codice": codice,
            "nome": info.get("nome", codice),
            "tipo": info.get("tipo", "altro"),
            "costi": round(costo, 2),
            "ricavi_stimati": round(ricavi_cdc, 2),
            "ricavi_sono_stima": True,
            "margine": round(margine, 2),
            "margine_percentuale": round((margine / ricavi_cdc * 100), 1) if ricavi_cdc > 0 else 0,
            "fatture_count": analitica["fatture_count"].get(codice, 0),
            "stato": "PROFITTO (stima)" if margine > 0 else "PERDITA (stima)",
        })

    return {
        "anno": anno,
        "centri_costo": report,
        "qualita_costi": analitica,
        "avviso_ricavi": (
            "I COSTI per CDC derivano dalle singole righe XML classificate; righe "
            "ambigue restano DA_VERIFICARE. I RICAVI per CDC restano una stima "
            "finche non esiste una fonte ricavi reale per settore."
        ),
        "totali": {
            "ricavi": round(ricavi_totali, 2),
            "costi_validati": round(costi_totali_validati, 2),
            "costi_da_verificare": analitica["da_verificare"],
            "margine_su_costi_validati": round(ricavi_totali - costi_totali_validati, 2),
        },
    }


# ============== RIBALTAMENTO CDC ==============

# Criterio di ribaltamento (scelta utente): i costi di supporto (CDC-90/91/92) e
# di struttura (CDC-99) vengono ribaltati sui settori operativi in PROPORZIONE AI
# RICAVI di ciascun settore. Non ci sono più percentuali fisse configurate: la
# ripartizione segue i ricavi per settore. Poiché i ricavi non sono tracciati per
# settore, le quote-ricavo sono una STIMA (proxy sui costi diretti, o override
# manuale in `config_ribaltamento`): il risultato è etichettato come stima.


async def _quote_ricavo_per_settore(db) -> Optional[Dict[str, float]]:
    """Override manuale delle quote-ricavo per settore (somma ~1), se configurato
    in `config_ribaltamento`. None se assente."""
    conf = await db["config_ribaltamento"].find_one({"_id": "quote_ricavo_settori"})
    if not conf:
        return None
    quote = {k: float(v) for k, v in (conf.get("quote") or {}).items()
             if k in CDC_OPERATIVI and float(v) > 0}
    tot = sum(quote.values())
    if tot <= 0:
        return None
    return {k: v / tot for k, v in quote.items()}


@router.post("/ribaltamento/calcola")
async def calcola_ribaltamento(anno: int = Query(...)) -> Dict[str, Any]:
    """Ribalta i costi di supporto e struttura sui settori operativi in
    proporzione ai ricavi di ciascun settore (scelta utente).

    I ricavi per settore non sono tracciati: si usano le quote configurate in
    `config_ribaltamento` (override manuale) oppure, in mancanza, una stima
    proporzionale ai costi diretti di ciascun settore. Il campo `ricavi_stima`
    segnala quando la ripartizione è stimata."""
    db = Database.get_db()

    date_start = f"{anno}-01-01"
    date_end = f"{anno}-12-31"

    # 1. Costi per centro di costo: fonte analitica = righe XML classificate.
    analitica = await _costi_cdc_da_righe_xml(db, anno)
    costi_dict = analitica["costi"]

    # 2. Costi diretti dei settori operativi
    costi_diretti = {cdc: costi_dict.get(cdc, 0) for cdc in CDC_OPERATIVI}

    # 3. Ricavi totali dalla stessa fonte canonica del Conto Economico.
    from app.routers.accounting.bilancio import get_conto_economico
    ce = await get_conto_economico(anno=anno, mese=None)
    ricavi_totali = float(ce["ricavi"]["totale_ricavi"] or 0)

    quote_override = await _quote_ricavo_per_settore(db)
    if quote_override:
        quote_ricavo = {cdc: quote_override.get(cdc, 0.0) for cdc in CDC_OPERATIVI}
        ricavi_stima = False
    else:
        # Proxy: ricavi per settore ∝ costi diretti (unico segnale di attività
        # disponibile per settore). Se non ci sono costi diretti, ripartizione equa.
        tot_diretti = sum(costi_diretti.values())
        if tot_diretti > 0:
            quote_ricavo = {cdc: costi_diretti[cdc] / tot_diretti for cdc in CDC_OPERATIVI}
        else:
            quote_ricavo = {cdc: 1.0 / len(CDC_OPERATIVI) for cdc in CDC_OPERATIVI}
        ricavi_stima = True
    ricavi_cdc = {cdc: ricavi_totali * quote_ricavo[cdc] for cdc in CDC_OPERATIVI}

    # 4. Ribalta supporto + struttura in proporzione ai ricavi
    ribaltamenti = []
    totale_ribaltato = {cdc: 0.0 for cdc in CDC_OPERATIVI}
    for cdc_fonte in CDC_DA_RIBALTARE:
        costo_fonte = costi_dict.get(cdc_fonte, 0)
        if costo_fonte == 0:
            continue
        for cdc_dest in CDC_OPERATIVI:
            quota = quote_ricavo[cdc_dest]
            if quota <= 0:
                continue
            importo = costo_fonte * quota
            totale_ribaltato[cdc_dest] += importo
            ribaltamenti.append({
                "da_cdc": cdc_fonte,
                "da_cdc_nome": CDC_STANDARD.get(cdc_fonte, {}).get("nome", cdc_fonte),
                "a_cdc": cdc_dest,
                "a_cdc_nome": CDC_STANDARD.get(cdc_dest, {}).get("nome", cdc_dest),
                "quota_percentuale": round(quota * 100, 1),
                "importo_origine": round(costo_fonte, 2),
                "importo_ribaltato": round(importo, 2)
            })

    # 5. Costi pieni (diretti + ribaltati) e margini per settore
    costi_pieni = {cdc: costi_diretti[cdc] + totale_ribaltato[cdc] for cdc in CDC_OPERATIVI}
    margini = {}
    for cdc in CDC_OPERATIVI:
        r = ricavi_cdc[cdc]
        margini[cdc] = {
            "cdc": cdc,
            "nome": CDC_STANDARD.get(cdc, {}).get("nome", cdc),
            "ricavi": round(r, 2),
            "quota_ricavo_percentuale": round(quote_ricavo[cdc] * 100, 1),
            "costi_diretti": round(costi_diretti[cdc], 2),
            "costi_ribaltati": round(totale_ribaltato[cdc], 2),
            "costi_pieni": round(costi_pieni[cdc], 2),
            "margine_diretto": round(r - costi_diretti[cdc], 2),
            "margine_pieno": round(r - costi_pieni[cdc], 2),
            "margine_percentuale": round((r - costi_pieni[cdc]) / r * 100, 1) if r > 0 else 0,
        }

    return {
        "anno": anno,
        "criterio": "proporzionale_ai_ricavi",
        "ricavi_stima": ricavi_stima,
        "avviso_ricavi": (
            "Ricavi per settore stimati (proporzionali ai costi diretti): i ricavi "
            "reali non sono tracciati per settore. Configura le quote reali con "
            "/ribaltamento/quote-ricavo per un ribaltamento esatto."
            if ricavi_stima else
            "Ribaltamento basato sulle quote-ricavo per settore configurate."
        ),
        "qualita_costi": analitica,
        "ribaltamenti": ribaltamenti,
        "totali_ribaltati": {k: round(v, 2) for k, v in totale_ribaltato.items()},
        "margini_per_cdc": list(margini.values()),
        "sintesi": {
            "ricavi_totali": round(ricavi_totali, 2),
            "costi_diretti_totali": round(sum(costi_diretti.values()), 2),
            "costi_ribaltati_totali": round(sum(totale_ribaltato.values()), 2),
            "margine_aziendale": round(ricavi_totali - sum(costi_pieni.values()), 2)
        }
    }


@router.post("/ribaltamento/quote-ricavo")
async def imposta_quote_ricavo(quote: Dict[str, float] = Body(...)) -> Dict[str, Any]:
    """Imposta le quote-ricavo reali per settore (es. {"CDC-01": 0.4, "CDC-03": 0.3,
    ...}) usate dal ribaltamento proporzionale. Le quote vengono normalizzate a 1.
    Senza questa configurazione il ribaltamento usa una stima sui costi diretti."""
    db = Database.get_db()
    valide = {k: float(v) for k, v in (quote or {}).items()
              if k in CDC_OPERATIVI and float(v) >= 0}
    if not valide or sum(valide.values()) <= 0:
        raise HTTPException(status_code=400,
                            detail="Fornire almeno una quota > 0 per un settore operativo valido")
    await db["config_ribaltamento"].update_one(
        {"_id": "quote_ricavo_settori"},
        {"$set": {"quote": valide, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True
    )
    return {"success": True, "quote_salvate": valide,
            "settori": {cdc: CDC_STANDARD[cdc]["nome"] for cdc in CDC_OPERATIVI}}
