"""
Contabilità Gestionale - 3 moduli:
1. Bilancio di Verifica (completo, da TUTTE le fonti)
2. Partitario Clienti/Fornitori (estratti conto dare/avere/saldo)
3. Budget e Previsionale (budget per voce, confronto consuntivo, scostamenti)
"""

from fastapi import APIRouter, Query
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from uuid import uuid4
from collections import defaultdict

from app.database import Database, Collections

router = APIRouter(prefix="/api/contabilita-gestionale", tags=["Contabilità Gestionale"])

COLLECTION_PRIMA_NOTA_CASSA = "prima_nota_cassa"
COLLECTION_PRIMA_NOTA_BANCA = "prima_nota_banca"
COLLECTION_PRIMA_NOTA_SALARI = "prima_nota_salari"
COLLECTION_BUDGET = "budget"
COLLECTION_BUDGET_MENSILE = "budget_mensile"

# ============================================
# 1. BILANCIO DI VERIFICA
# ============================================

def _match_anno(data_str: str, anno: int) -> bool:
    """Check if a date string matches the given year."""
    if not data_str or not anno:
        return True
    try:
        return str(anno) in str(data_str)[:4]
    except (TypeError, AttributeError) as e:
        logger.debug(f"Errore match anno: {e}")
        return False


@router.get("/bilancio-verifica")
async def get_bilancio_verifica_completo(
    anno: int = Query(..., description="Anno di riferimento"),
    dettaglio: bool = Query(False, description="Mostra dettaglio movimenti per conto")
) -> Dict[str, Any]:
    """
    Bilancio di Verifica completo.
    Aggrega da TUTTE le fonti contabili: fatture, corrispettivi, prima nota, cespiti, cedolini.
    
    Struttura: per ogni conto del piano dei conti mostra:
    - Saldo iniziale (dare/avere)
    - Movimenti periodo (dare/avere)
    - Saldo finale (dare/avere)
    """
    db = Database.get_db()
    anno_str = str(anno)
    
    # Struttura conti: {codice: {nome, dare, avere, movimenti[]}}
    conti = defaultdict(lambda: {
        "codice": "",
        "nome": "",
        "tipo": "",  # attivo/passivo/ricavo/costo
        "dare": 0.0,
        "avere": 0.0,
        "n_movimenti": 0,
        "movimenti": []  # solo se dettaglio=True
    })
    
    # --- FATTURE RICEVUTE (COSTI) ---
    fatture = await db[Collections.INVOICES].find({
        "$or": [
            {"data_documento": {"$regex": f"^{anno_str}"}},
            {"data_ricezione": {"$regex": f"^{anno_str}"}},
            {"anno": anno}
        ]
    }, {"_id": 0}).to_list(10000)
    
    for f in fatture:
        try:
            importo = float(f.get("total_amount") or f.get("importo_totale") or 0)
            imponibile = float(f.get("imponibile") or f.get("total_amount") or importo)
            iva = float(f.get("importo_iva") or f.get("iva") or 0)
        except (ValueError, TypeError) as e:
            logger.warning(f"Errore conversione importi fattura {f.get('_id')}: {e}")
            continue
        
        tipo_doc = f.get("tipo_documento", "TD01")
        fornitore = f.get("supplier_name", "Fornitore sconosciuto")
        categoria = f.get("categoria_contabile", "Acquisti generici")
        is_nc = tipo_doc in ["TD04", "TD08"]
        
        # Conto costo (05.xx) - DARE per fatture, AVERE per note credito
        codice_costo = "05.01.01"
        if "personale" in categoria.lower() or "stipend" in categoria.lower():
            codice_costo = "05.03.01"
        elif "utenz" in categoria.lower() or "energia" in categoria.lower():
            codice_costo = "05.02.02"
        elif "affitto" in categoria.lower():
            codice_costo = "05.02.01"
        elif "manutenzione" in categoria.lower():
            codice_costo = "05.02.03"
        elif "assicuraz" in categoria.lower():
            codice_costo = "05.02.04"
        elif "consulenz" in categoria.lower() or "profession" in categoria.lower():
            codice_costo = "05.04.01"
        
        conto = conti[codice_costo]
        conto["codice"] = codice_costo
        conto["nome"] = categoria or "Acquisti merci e servizi"
        conto["tipo"] = "costo"
        
        if is_nc:
            conto["avere"] += imponibile
        else:
            conto["dare"] += imponibile
        conto["n_movimenti"] += 1
        
        # Debiti vs fornitori (02.01.01) - AVERE per fatture, DARE per NC
        conto_deb = conti["02.01.01"]
        conto_deb["codice"] = "02.01.01"
        conto_deb["nome"] = "Debiti verso fornitori"
        conto_deb["tipo"] = "passivo"
        
        if is_nc:
            conto_deb["dare"] += importo
        else:
            conto_deb["avere"] += importo
        conto_deb["n_movimenti"] += 1
        
        # IVA credito (01.04.01) - DARE
        if iva > 0 and not is_nc:
            conto_iva = conti["01.04.01"]
            conto_iva["codice"] = "01.04.01"
            conto_iva["nome"] = "IVA a credito"
            conto_iva["tipo"] = "attivo"
            conto_iva["dare"] += iva
            conto_iva["n_movimenti"] += 1
        
        if dettaglio:
            mov = {
                "data": f.get("data_documento", ""),
                "descrizione": f"Fatt. {f.get('invoice_number', '')} - {fornitore}",
                "dare": imponibile if not is_nc else 0,
                "avere": imponibile if is_nc else 0
            }
            conto["movimenti"].append(mov)
    
    # --- CORRISPETTIVI (RICAVI) ---
    corrispettivi = await db[Collections.CORRISPETTIVI].find({
        "$or": [
            {"data": {"$regex": f"^{anno_str}"}},
            {"anno": anno}
        ]
    }, {"_id": 0}).to_list(10000)
    
    for c in corrispettivi:
        totale = float(c.get("totale") or 0)
        imponibile = float(c.get("totale_imponibile") or c.get("imponibile") or totale)
        iva = float(c.get("totale_iva") or c.get("iva") or 0)
        
        if totale == 0:
            continue
        
        # Ricavi vendita (04.01.01) - AVERE
        conto_ric = conti["04.01.01"]
        conto_ric["codice"] = "04.01.01"
        conto_ric["nome"] = "Ricavi vendite e prestazioni"
        conto_ric["tipo"] = "ricavo"
        conto_ric["avere"] += imponibile
        conto_ric["n_movimenti"] += 1
        
        # IVA debito (02.03.01) - AVERE
        if iva > 0:
            conto_iva_d = conti["02.03.01"]
            conto_iva_d["codice"] = "02.03.01"
            conto_iva_d["nome"] = "IVA a debito"
            conto_iva_d["tipo"] = "passivo"
            conto_iva_d["avere"] += iva
            conto_iva_d["n_movimenti"] += 1
        
        # Cassa (01.01.01) - DARE
        conto_cassa = conti["01.01.01"]
        conto_cassa["codice"] = "01.01.01"
        conto_cassa["nome"] = "Cassa contanti"
        conto_cassa["tipo"] = "attivo"
        conto_cassa["dare"] += totale
        conto_cassa["n_movimenti"] += 1
    
    # --- PRIMA NOTA CASSA ---
    pn_cassa = await db[COLLECTION_PRIMA_NOTA_CASSA].find({
        "data": {"$regex": f"^{anno_str}"}
    }, {"_id": 0}).to_list(10000)
    
    for m in pn_cassa:
        importo = float(m.get("importo") or 0)
        tipo = m.get("tipo", "").lower()
        desc = m.get("descrizione", "")
        
        if importo == 0:
            continue
        
        # Skip corrispettivi già contati
        if m.get("corrispettivo_id") or m.get("source") == "corrispettivo":
            continue
        
        if tipo in ["entrata", "incasso"]:
            conto_cassa = conti["01.01.01"]
            conto_cassa["codice"] = "01.01.01"
            conto_cassa["nome"] = "Cassa contanti"
            conto_cassa["tipo"] = "attivo"
            conto_cassa["dare"] += importo
            conto_cassa["n_movimenti"] += 1
        elif tipo in ["uscita", "pagamento"]:
            conto_cassa = conti["01.01.01"]
            conto_cassa["codice"] = "01.01.01"
            conto_cassa["nome"] = "Cassa contanti"
            conto_cassa["tipo"] = "attivo"
            conto_cassa["avere"] += importo
            conto_cassa["n_movimenti"] += 1
        elif tipo == "versamento_banca":
            # Giroconto: cassa AVERE, banca DARE
            conti["01.01.01"]["avere"] += importo
            conti["01.01.01"]["n_movimenti"] += 1
            conti["01.01.01"]["codice"] = "01.01.01"
            conti["01.01.01"]["nome"] = "Cassa contanti"
            conti["01.01.01"]["tipo"] = "attivo"
            
            conti["01.02.01"]["dare"] += importo
            conti["01.02.01"]["n_movimenti"] += 1
            conti["01.02.01"]["codice"] = "01.02.01"
            conti["01.02.01"]["nome"] = "Banca c/c"
            conti["01.02.01"]["tipo"] = "attivo"
    
    # --- PRIMA NOTA BANCA ---
    pn_banca = await db[COLLECTION_PRIMA_NOTA_BANCA].find({
        "data": {"$regex": f"^{anno_str}"}
    }, {"_id": 0}).to_list(10000)
    
    for m in pn_banca:
        importo = float(m.get("importo") or 0)
        tipo = m.get("tipo", "").lower()
        
        if importo == 0:
            continue
        
        conto_banca = conti["01.02.01"]
        conto_banca["codice"] = "01.02.01"
        conto_banca["nome"] = "Banca c/c"
        conto_banca["tipo"] = "attivo"
        
        if tipo in ["entrata", "incasso", "accredito"]:
            conto_banca["dare"] += importo
        elif tipo in ["uscita", "pagamento", "addebito", "bonifico"]:
            conto_banca["avere"] += importo
        conto_banca["n_movimenti"] += 1
    
    # --- PRIMA NOTA SALARI ---
    pn_salari = await db[COLLECTION_PRIMA_NOTA_SALARI].find({
        "data": {"$regex": f"^{anno_str}"}
    }, {"_id": 0}).to_list(10000)
    
    for m in pn_salari:
        importo = float(m.get("importo") or m.get("netto") or 0)
        
        if importo == 0:
            continue
        
        # Costo personale (05.03.01) - DARE
        conto_sal = conti["05.03.01"]
        conto_sal["codice"] = "05.03.01"
        conto_sal["nome"] = "Costi del personale"
        conto_sal["tipo"] = "costo"
        conto_sal["dare"] += importo
        conto_sal["n_movimenti"] += 1
        
        # Debiti vs dipendenti (02.02.01) - AVERE
        conto_dip = conti["02.02.01"]
        conto_dip["codice"] = "02.02.01"
        conto_dip["nome"] = "Debiti verso dipendenti"
        conto_dip["tipo"] = "passivo"
        conto_dip["avere"] += importo
        conto_dip["n_movimenti"] += 1
    
    # --- CESPITI (ammortamenti) ---
    cespiti = await db.get_collection("cespiti").find({
        "anno_acquisto": anno
    }, {"_id": 0}).to_list(1000)
    
    for c in cespiti:
        valore = float(c.get("valore_acquisto") or 0)
        ammortamento = float(c.get("ammortamento_annuo") or 0)
        
        if valore > 0:
            # Immobilizzazioni (01.05.01) - DARE
            conto_imm = conti["01.05.01"]
            conto_imm["codice"] = "01.05.01"
            conto_imm["nome"] = "Immobilizzazioni materiali"
            conto_imm["tipo"] = "attivo"
            conto_imm["dare"] += valore
            conto_imm["n_movimenti"] += 1
        
        if ammortamento > 0:
            # Fondo ammortamento (01.05.02) - AVERE
            conto_fondo = conti["01.05.02"]
            conto_fondo["codice"] = "01.05.02"
            conto_fondo["nome"] = "Fondo ammortamento"
            conto_fondo["tipo"] = "attivo"  # rettifica
            conto_fondo["avere"] += ammortamento
            conto_fondo["n_movimenti"] += 1
            
            # Costo ammortamento (05.05.01) - DARE
            conto_amm = conti["05.05.01"]
            conto_amm["codice"] = "05.05.01"
            conto_amm["nome"] = "Ammortamenti"
            conto_amm["tipo"] = "costo"
            conto_amm["dare"] += ammortamento
            conto_amm["n_movimenti"] += 1
    
    # --- Costruisci risultato ---
    risultato = []
    for codice in sorted(conti.keys()):
        c = conti[codice]
        if c["dare"] == 0 and c["avere"] == 0:
            continue
        
        saldo = round(c["dare"] - c["avere"], 2)
        entry = {
            "codice": c["codice"],
            "nome": c["nome"],
            "tipo": c["tipo"],
            "dare": round(c["dare"], 2),
            "avere": round(c["avere"], 2),
            "saldo": saldo,
            "saldo_dare": round(saldo, 2) if saldo > 0 else 0,
            "saldo_avere": round(abs(saldo), 2) if saldo < 0 else 0,
            "n_movimenti": c["n_movimenti"]
        }
        if dettaglio and c["movimenti"]:
            entry["movimenti"] = c["movimenti"][:50]  # max 50 per conto
        risultato.append(entry)
    
    totale_dare = sum(c["dare"] for c in risultato)
    totale_avere = sum(c["avere"] for c in risultato)
    totale_saldo_dare = sum(c["saldo_dare"] for c in risultato)
    totale_saldo_avere = sum(c["saldo_avere"] for c in risultato)
    
    return {
        "success": True,
        "anno": anno,
        "data_generazione": datetime.now(timezone.utc).isoformat(),
        "conti": risultato,
        "totali": {
            "dare": round(totale_dare, 2),
            "avere": round(totale_avere, 2),
            "saldo_dare": round(totale_saldo_dare, 2),
            "saldo_avere": round(totale_saldo_avere, 2),
            "sbilancio": round(totale_dare - totale_avere, 2)
        },
        "quadratura": abs(totale_dare - totale_avere) < 0.01,
        "riepilogo": {
            "n_conti": len(risultato),
            "n_conti_attivo": len([c for c in risultato if c["tipo"] == "attivo"]),
            "n_conti_passivo": len([c for c in risultato if c["tipo"] == "passivo"]),
            "n_conti_ricavo": len([c for c in risultato if c["tipo"] == "ricavo"]),
            "n_conti_costo": len([c for c in risultato if c["tipo"] == "costo"])
        }
    }


# ============================================
# 2. PARTITARIO CLIENTI/FORNITORI
# ============================================

@router.get("/partitario/fornitori")
async def get_partitario_fornitori(
    anno: int = Query(..., description="Anno di riferimento"),
    fornitore_piva: Optional[str] = Query(None, description="Filtro per P.IVA fornitore"),
    solo_aperti: bool = Query(False, description="Solo con saldo aperto")
) -> Dict[str, Any]:
    """
    Partitario Fornitori - Estratto conto per ogni fornitore.
    Mostra: fatture ricevute (DARE), pagamenti effettuati (AVERE), saldo.
    """
    db = Database.get_db()
    anno_str = str(anno)
    
    # Query fatture anno
    query_fatture = {
        "$or": [
            {"data_documento": {"$regex": f"^{anno_str}"}},
            {"data_ricezione": {"$regex": f"^{anno_str}"}},
            {"anno": anno}
        ]
    }
    if fornitore_piva:
        query_fatture["cedente_piva"] = fornitore_piva
    
    fatture = await db[Collections.INVOICES].find(
        query_fatture, {"_id": 0}
    ).sort("data_documento", 1).to_list(10000)
    
    # Pagamenti prima nota banca (filtrati per fattura_id)
    pagamenti_banca = {}
    pn_banca = await db[COLLECTION_PRIMA_NOTA_BANCA].find({
        "data": {"$regex": f"^{anno_str}"},
        "fattura_id": {"$exists": True, "$ne": None}
    }, {"_id": 0}).to_list(10000)
    for p in pn_banca:
        fid = p.get("fattura_id")
        if fid:
            pagamenti_banca[fid] = pagamenti_banca.get(fid, 0) + float(p.get("importo", 0))
    
    # Pagamenti prima nota cassa
    pagamenti_cassa = {}
    pn_cassa = await db[COLLECTION_PRIMA_NOTA_CASSA].find({
        "data": {"$regex": f"^{anno_str}"},
        "fattura_id": {"$exists": True, "$ne": None}
    }, {"_id": 0}).to_list(10000)
    for p in pn_cassa:
        fid = p.get("fattura_id")
        if fid:
            pagamenti_cassa[fid] = pagamenti_cassa.get(fid, 0) + float(p.get("importo", 0))
    
    # Aggrega per fornitore
    fornitori_map = {}  # {piva: {info, movimenti[], totali}}
    
    for f in fatture:
        piva = f.get("cedente_piva") or f.get("supplier_vat") or "N/D"
        nome = f.get("supplier_name") or f.get("cedente_denominazione") or "Sconosciuto"
        fid = f.get("id", "")
        importo = float(f.get("total_amount") or f.get("importo_totale") or 0)
        tipo_doc = f.get("tipo_documento", "TD01")
        is_nc = tipo_doc in ["TD04", "TD08"]
        
        if piva not in fornitori_map:
            fornitori_map[piva] = {
                "fornitore": nome,
                "partita_iva": piva,
                "totale_dare": 0.0,
                "totale_avere": 0.0,
                "movimenti": []
            }
        
        entry = fornitori_map[piva]
        
        # Fattura = DARE (debito verso fornitore), NC = AVERE
        if is_nc:
            dare = 0
            avere = importo
            entry["totale_avere"] += importo
        else:
            dare = importo
            avere = 0
            entry["totale_dare"] += importo
        
        pagato_banca = pagamenti_banca.get(fid, 0)
        pagato_cassa = pagamenti_cassa.get(fid, 0)
        pagato_totale = pagato_banca + pagato_cassa
        
        # Pagamento = AVERE
        if pagato_totale > 0 and not is_nc:
            entry["totale_avere"] += pagato_totale
        
        stato_pag = f.get("stato_pagamento") or f.get("paid")
        is_pagata = stato_pag in [True, "pagato", "paid"]
        
        # Se pagata ma non in prima nota, assume pagamento avvenuto
        if is_pagata and pagato_totale == 0 and not is_nc:
            entry["totale_avere"] += importo
            pagato_totale = importo
        
        entry["movimenti"].append({
            "data": f.get("data_documento", ""),
            "tipo": "nota_credito" if is_nc else "fattura",
            "numero": f.get("invoice_number") or f.get("numero_fattura", ""),
            "descrizione": f"{'NC' if is_nc else 'Fatt.'} {f.get('invoice_number', '')}",
            "dare": round(dare, 2),
            "avere": round(avere, 2),
            "pagato": round(pagato_totale, 2),
            "stato": "pagata" if is_pagata else "aperta",
            "fattura_id": fid
        })
    
    # Calcola saldi e filtra
    risultato = []
    for piva, data in sorted(fornitori_map.items(), key=lambda x: x[1]["fornitore"]):
        saldo = round(data["totale_dare"] - data["totale_avere"], 2)
        
        if solo_aperti and abs(saldo) < 0.01:
            continue
        
        risultato.append({
            "fornitore": data["fornitore"],
            "partita_iva": data["partita_iva"],
            "totale_dare": round(data["totale_dare"], 2),
            "totale_avere": round(data["totale_avere"], 2),
            "saldo": saldo,
            "stato": "aperto" if saldo > 0.01 else ("a_credito" if saldo < -0.01 else "saldato"),
            "n_documenti": len(data["movimenti"]),
            "movimenti": sorted(data["movimenti"], key=lambda m: m["data"])
        })
    
    totale_dare = sum(f["totale_dare"] for f in risultato)
    totale_avere = sum(f["totale_avere"] for f in risultato)
    
    return {
        "success": True,
        "anno": anno,
        "tipo": "fornitori",
        "fornitori": risultato,
        "totali": {
            "n_fornitori": len(risultato),
            "n_aperti": len([f for f in risultato if f["stato"] == "aperto"]),
            "n_saldati": len([f for f in risultato if f["stato"] == "saldato"]),
            "totale_dare": round(totale_dare, 2),
            "totale_avere": round(totale_avere, 2),
            "saldo_totale": round(totale_dare - totale_avere, 2)
        }
    }


@router.get("/partitario/fornitori/{piva}")
async def get_partitario_singolo_fornitore(
    piva: str,
    anno: int = Query(..., description="Anno")
) -> Dict[str, Any]:
    """Estratto conto singolo fornitore."""
    result = await get_partitario_fornitori(anno=anno, fornitore_piva=piva)
    if result["fornitori"]:
        return {
            "success": True,
            "anno": anno,
            "fornitore": result["fornitori"][0]
        }
    return {"success": False, "error": f"Nessun movimento per P.IVA {piva} nel {anno}"}


@router.get("/partitario/clienti")
async def get_partitario_clienti(
    anno: int = Query(..., description="Anno di riferimento")
) -> Dict[str, Any]:
    """
    Partitario Clienti - Per HORECA i clienti sono prevalentemente anonimi (corrispettivi).
    Mostra: corrispettivi giornalieri aggregati per mese e fatture emesse a clienti.
    """
    db = Database.get_db()
    anno_str = str(anno)
    
    # Corrispettivi aggregati per mese
    corrispettivi = await db[Collections.CORRISPETTIVI].find({
        "$or": [
            {"data": {"$regex": f"^{anno_str}"}},
            {"anno": anno}
        ]
    }, {"_id": 0}).to_list(10000)
    
    mesi = defaultdict(lambda: {"totale": 0, "imponibile": 0, "iva": 0, "n_giorni": 0})
    for c in corrispettivi:
        data = c.get("data", "")
        try:
            mese = int(data[5:7]) if len(data) >= 7 else 0
        except (ValueError, IndexError) as e:
            logger.debug(f"Errore parsing mese da data '{data}': {e}")
            mese = 0
        if mese == 0:
            continue
        
        m = mesi[mese]
        m["totale"] += float(c.get("totale") or 0)
        m["imponibile"] += float(c.get("totale_imponibile") or c.get("imponibile") or 0)
        m["iva"] += float(c.get("totale_iva") or c.get("iva") or 0)
        m["n_giorni"] += 1
    
    mesi_list = []
    nomi_mesi = ["", "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
                  "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]
    
    for mese_num in range(1, 13):
        m = mesi.get(mese_num, {"totale": 0, "imponibile": 0, "iva": 0, "n_giorni": 0})
        mesi_list.append({
            "mese": mese_num,
            "nome_mese": nomi_mesi[mese_num],
            "totale_dare": round(m["totale"], 2),  # Credito vs clienti
            "totale_avere": round(m["totale"], 2),  # Incassato (corrispettivi = incasso immediato)
            "saldo": 0,  # Corrispettivi = incasso contestuale
            "imponibile": round(m["imponibile"], 2),
            "iva": round(m["iva"], 2),
            "n_operazioni": m["n_giorni"]
        })
    
    # Fatture emesse a clienti (se presenti)
    fatture_emesse = await db.get_collection("fatture_emesse").find({
        "$or": [
            {"data": {"$regex": f"^{anno_str}"}},
            {"anno": anno}
        ]
    }, {"_id": 0}).to_list(1000)
    
    clienti_fatturati = []
    for fe in fatture_emesse:
        clienti_fatturati.append({
            "cliente": fe.get("cliente_denominazione", "N/D"),
            "numero": fe.get("numero", ""),
            "data": fe.get("data", ""),
            "importo": float(fe.get("importo_totale") or 0),
            "stato": fe.get("stato", "emessa")
        })
    
    totale_corrispettivi = sum(m["totale_dare"] for m in mesi_list)
    
    return {
        "success": True,
        "anno": anno,
        "tipo": "clienti",
        "corrispettivi_mensili": mesi_list,
        "fatture_emesse": clienti_fatturati,
        "totali": {
            "totale_corrispettivi": round(totale_corrispettivi, 2),
            "totale_fatture_emesse": round(sum(f["importo"] for f in clienti_fatturati), 2),
            "n_giorni_vendita": sum(m["n_operazioni"] for m in mesi_list),
            "media_giornaliera": round(totale_corrispettivi / max(sum(m["n_operazioni"] for m in mesi_list), 1), 2)
        }
    }


# ============================================
# 3. BUDGET E PREVISIONALE
# ============================================

@router.get("/budget/{anno}")
async def get_budget_completo(anno: int) -> Dict[str, Any]:
    """
    Recupera il budget completo per l'anno con dettaglio mensile.
    """
    db = Database.get_db()
    
    budget_items = await db[COLLECTION_BUDGET].find(
        {"anno": anno}, {"_id": 0}
    ).to_list(200)
    
    budget_mensili = await db[COLLECTION_BUDGET_MENSILE].find(
        {"anno": anno}, {"_id": 0}
    ).to_list(2000)
    
    # Organizza per voce
    voci = {}
    for b in budget_items:
        voce = b.get("voce", "")
        voci[voce] = {
            "id": b.get("id", ""),
            "voce": voce,
            "categoria": b.get("categoria", "costo"),
            "importo_annuale": float(b.get("importo_budget", 0)),
            "note": b.get("note", ""),
            "mensile": {m: 0 for m in range(1, 13)}
        }
    
    # Aggiungi mensili
    for bm in budget_mensili:
        voce = bm.get("voce", "")
        mese = bm.get("mese", 0)
        if voce in voci and 1 <= mese <= 12:
            voci[voce]["mensile"][mese] = float(bm.get("importo", 0))
    
    # Per le voci senza mensile, distribuisci uniformemente
    for voce, data in voci.items():
        if all(v == 0 for v in data["mensile"].values()):
            mensile = round(data["importo_annuale"] / 12, 2)
            for m in range(1, 13):
                data["mensile"][m] = mensile
    
    voci_list = sorted(voci.values(), key=lambda v: (v["categoria"], v["voce"]))
    
    totale_costi = sum(v["importo_annuale"] for v in voci_list if v["categoria"] == "costo")
    totale_ricavi = sum(v["importo_annuale"] for v in voci_list if v["categoria"] == "ricavo")
    
    return {
        "success": True,
        "anno": anno,
        "voci": voci_list,
        "totali": {
            "costi_budget": round(totale_costi, 2),
            "ricavi_budget": round(totale_ricavi, 2),
            "margine_budget": round(totale_ricavi - totale_costi, 2),
            "margine_pct": round((totale_ricavi - totale_costi) / totale_ricavi * 100, 1) if totale_ricavi > 0 else 0
        }
    }


@router.post("/budget")
async def salva_voce_budget(data: Dict[str, Any]) -> Dict[str, Any]:
    """Crea o aggiorna una voce di budget."""
    db = Database.get_db()
    
    anno = data.get("anno")
    voce = data.get("voce", "").strip()
    categoria = data.get("categoria", "costo")
    importo = float(data.get("importo_annuale", 0))
    note = data.get("note", "")
    mensili = data.get("mensile", {})
    
    if not anno or not voce:
        return {"success": False, "error": "Anno e voce obbligatori"}
    
    # Upsert voce principale
    existing = await db[COLLECTION_BUDGET].find_one({"anno": anno, "voce": voce})
    
    record = {
        "anno": anno,
        "voce": voce,
        "categoria": categoria,
        "importo_budget": importo,
        "note": note,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    if existing:
        await db[COLLECTION_BUDGET].update_one(
            {"anno": anno, "voce": voce},
            {"$set": record}
        )
    else:
        record["id"] = str(uuid4())
        record["created_at"] = datetime.now(timezone.utc).isoformat()
        await db[COLLECTION_BUDGET].insert_one(record.copy())
    
    # Salva/aggiorna mensili
    if mensili:
        for mese_str, importo_mese in mensili.items():
            mese = int(mese_str)
            await db[COLLECTION_BUDGET_MENSILE].update_one(
                {"anno": anno, "voce": voce, "mese": mese},
                {"$set": {
                    "anno": anno,
                    "voce": voce,
                    "mese": mese,
                    "importo": float(importo_mese),
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }},
                upsert=True
            )
    
    return {"success": True, "messaggio": f"Budget '{voce}' salvato per {anno}"}


@router.delete("/budget/{anno}/{voce}")
async def elimina_voce_budget(anno: int, voce: str) -> Dict[str, Any]:
    """Elimina una voce di budget."""
    db = Database.get_db()
    
    r1 = await db[COLLECTION_BUDGET].delete_one({"anno": anno, "voce": voce})
    r2 = await db[COLLECTION_BUDGET_MENSILE].delete_many({"anno": anno, "voce": voce})
    
    return {
        "success": True,
        "eliminati": r1.deleted_count,
        "mensili_eliminati": r2.deleted_count
    }


@router.get("/budget-vs-consuntivo/{anno}")
async def get_budget_vs_consuntivo(
    anno: int,
    mese: Optional[int] = Query(None, description="Filtro mese (1-12), None = anno intero")
) -> Dict[str, Any]:
    """
    Confronto Budget vs Consuntivo con scostamenti.
    Aggrega i dati reali da corrispettivi (ricavi) e fatture (costi).
    """
    db = Database.get_db()
    anno_str = str(anno)
    
    # --- BUDGET ---
    budget_data = await get_budget_completo(anno)
    
    # --- CONSUNTIVO RICAVI (corrispettivi) ---
    query_corr = {"$or": [
        {"data": {"$regex": f"^{anno_str}"}},
        {"anno": anno}
    ]}
    corrispettivi = await db[Collections.CORRISPETTIVI].find(query_corr, {"_id": 0}).to_list(10000)
    
    ricavi_mensili = {m: 0 for m in range(1, 13)}
    for c in corrispettivi:
        data = c.get("data", "")
        try:
            m = int(data[5:7])
        except:
            continue
        if 1 <= m <= 12:
            ricavi_mensili[m] += float(c.get("totale_imponibile") or c.get("totale") or 0)
    
    # --- CONSUNTIVO COSTI (fatture ricevute) ---
    query_fatt = {"$or": [
        {"data_documento": {"$regex": f"^{anno_str}"}},
        {"anno": anno}
    ]}
    fatture = await db[Collections.INVOICES].find(query_fatt, {"_id": 0}).to_list(10000)
    
    costi_mensili = {m: 0 for m in range(1, 13)}
    costi_per_voce = defaultdict(lambda: {m: 0 for m in range(1, 13)})
    
    for f in fatture:
        data_doc = f.get("data_documento", "")
        try:
            m = int(data_doc[5:7])
        except:
            continue
        if not (1 <= m <= 12):
            continue
        
        importo = float(f.get("imponibile") or f.get("total_amount") or 0)
        tipo_doc = f.get("tipo_documento", "TD01")
        
        if tipo_doc in ["TD04", "TD08"]:
            importo = -importo
        
        costi_mensili[m] += importo
        
        categoria = f.get("categoria_contabile", "Acquisti generici")
        costi_per_voce[categoria][m] += importo
    
    # --- CONFRONTO PER VOCE ---
    confronto_voci = []
    for voce_budget in budget_data.get("voci", []):
        voce_nome = voce_budget["voce"]
        cat = voce_budget["categoria"]
        
        if mese:
            budget_importo = voce_budget["mensile"].get(mese, voce_budget["importo_annuale"] / 12)
        else:
            budget_importo = voce_budget["importo_annuale"]
        
        # Trova consuntivo corrispondente
        if cat == "ricavo":
            if mese:
                consuntivo_importo = ricavi_mensili.get(mese, 0)
            else:
                consuntivo_importo = sum(ricavi_mensili.values())
        else:
            # Cerca nelle categorie fattura
            consuntivo_importo = 0
            for cat_fatt, dati_mensili in costi_per_voce.items():
                if voce_nome.lower() in cat_fatt.lower() or cat_fatt.lower() in voce_nome.lower():
                    if mese:
                        consuntivo_importo += dati_mensili.get(mese, 0)
                    else:
                        consuntivo_importo += sum(dati_mensili.values())
        
        scostamento = consuntivo_importo - budget_importo
        scostamento_pct = round(scostamento / budget_importo * 100, 1) if budget_importo > 0 else 0
        
        # Per i ricavi: consuntivo > budget = positivo
        # Per i costi: consuntivo > budget = negativo
        if cat == "ricavo":
            valutazione = "positivo" if scostamento >= 0 else "negativo"
        else:
            valutazione = "negativo" if scostamento > 0 else "positivo"
        
        confronto_voci.append({
            "voce": voce_nome,
            "categoria": cat,
            "budget": round(budget_importo, 2),
            "consuntivo": round(consuntivo_importo, 2),
            "scostamento": round(scostamento, 2),
            "scostamento_pct": scostamento_pct,
            "valutazione": valutazione
        })
    
    # --- TOTALI ---
    if mese:
        totale_ricavi_budget = sum(v["budget"] for v in confronto_voci if v["categoria"] == "ricavo")
        totale_costi_budget = sum(v["budget"] for v in confronto_voci if v["categoria"] == "costo")
        totale_ricavi_cons = ricavi_mensili.get(mese, 0)
        totale_costi_cons = costi_mensili.get(mese, 0)
    else:
        totale_ricavi_budget = budget_data["totali"]["ricavi_budget"]
        totale_costi_budget = budget_data["totali"]["costi_budget"]
        totale_ricavi_cons = sum(ricavi_mensili.values())
        totale_costi_cons = sum(costi_mensili.values())
    
    margine_budget = totale_ricavi_budget - totale_costi_budget
    margine_cons = totale_ricavi_cons - totale_costi_cons
    
    # Andamento mensile per grafico
    andamento = []
    for m in range(1, 13):
        andamento.append({
            "mese": m,
            "ricavi_budget": round(sum(
                v["mensile"].get(m, v["importo_annuale"] / 12)
                for v in budget_data.get("voci", [])
                if v["categoria"] == "ricavo"
            ), 2),
            "ricavi_consuntivo": round(ricavi_mensili.get(m, 0), 2),
            "costi_budget": round(sum(
                v["mensile"].get(m, v["importo_annuale"] / 12)
                for v in budget_data.get("voci", [])
                if v["categoria"] == "costo"
            ), 2),
            "costi_consuntivo": round(costi_mensili.get(m, 0), 2)
        })
    
    return {
        "success": True,
        "anno": anno,
        "mese": mese,
        "confronto_voci": confronto_voci,
        "totali": {
            "ricavi": {
                "budget": round(totale_ricavi_budget, 2),
                "consuntivo": round(totale_ricavi_cons, 2),
                "scostamento": round(totale_ricavi_cons - totale_ricavi_budget, 2),
                "scostamento_pct": round((totale_ricavi_cons - totale_ricavi_budget) / totale_ricavi_budget * 100, 1) if totale_ricavi_budget > 0 else 0
            },
            "costi": {
                "budget": round(totale_costi_budget, 2),
                "consuntivo": round(totale_costi_cons, 2),
                "scostamento": round(totale_costi_cons - totale_costi_budget, 2),
                "scostamento_pct": round((totale_costi_cons - totale_costi_budget) / totale_costi_budget * 100, 1) if totale_costi_budget > 0 else 0
            },
            "margine": {
                "budget": round(margine_budget, 2),
                "consuntivo": round(margine_cons, 2),
                "scostamento": round(margine_cons - margine_budget, 2)
            }
        },
        "andamento_mensile": andamento
    }


@router.post("/budget/duplica/{anno_origine}/{anno_destinazione}")
async def duplica_budget(
    anno_origine: int,
    anno_destinazione: int,
    variazione_pct: float = Query(0, description="Variazione % da applicare (es: 5 = +5%)")
) -> Dict[str, Any]:
    """Duplica il budget da un anno all'altro con variazione % opzionale."""
    db = Database.get_db()
    
    budget_origine = await db[COLLECTION_BUDGET].find(
        {"anno": anno_origine}, {"_id": 0}
    ).to_list(200)
    
    if not budget_origine:
        return {"success": False, "error": f"Nessun budget trovato per {anno_origine}"}
    
    moltiplicatore = 1 + (variazione_pct / 100)
    creati = 0
    
    for b in budget_origine:
        existing = await db[COLLECTION_BUDGET].find_one({
            "anno": anno_destinazione, "voce": b["voce"]
        })
        if existing:
            continue
        
        nuovo = {
            "id": str(uuid4()),
            "anno": anno_destinazione,
            "voce": b["voce"],
            "categoria": b["categoria"],
            "importo_budget": round(float(b.get("importo_budget", 0)) * moltiplicatore, 2),
            "note": f"Duplicato da {anno_origine} ({variazione_pct:+.1f}%)",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        await db[COLLECTION_BUDGET].insert_one(nuovo.copy())
        creati += 1
    
    # Duplica anche mensili
    mensili_origine = await db[COLLECTION_BUDGET_MENSILE].find(
        {"anno": anno_origine}, {"_id": 0}
    ).to_list(2000)
    
    for bm in mensili_origine:
        existing = await db[COLLECTION_BUDGET_MENSILE].find_one({
            "anno": anno_destinazione, "voce": bm["voce"], "mese": bm["mese"]
        })
        if not existing:
            await db[COLLECTION_BUDGET_MENSILE].insert_one({
                "anno": anno_destinazione,
                "voce": bm["voce"],
                "mese": bm["mese"],
                "importo": round(float(bm.get("importo", 0)) * moltiplicatore, 2),
                "updated_at": datetime.now(timezone.utc).isoformat()
            })
    
    return {
        "success": True,
        "messaggio": f"Duplicati {creati} voci da {anno_origine} a {anno_destinazione}",
        "variazione_applicata": f"{variazione_pct:+.1f}%"
    }
