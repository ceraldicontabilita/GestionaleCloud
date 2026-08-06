"""
Contabilità Gestionale - 3 moduli:
1. Bilancio di Verifica (completo, da TUTTE le fonti)
2. Partitario Clienti/Fornitori (estratti conto dare/avere/saldo)
3. Budget e Previsionale (budget per voce, confronto consuntivo, scostamenti)
"""

from fastapi import APIRouter, Query, HTTPException, Depends
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from uuid import uuid4
from collections import defaultdict
import math
import logging

from app.database import Database, Collections
from app.utils.dependencies import get_current_admin_user
from app.services.mapping_piano_conti import operativo_a_ufficiale, descrizione_ufficiale

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Contabilità Gestionale"])

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


def _tipo_conto_da_codice(codice: str) -> str:
    """Classificazione operativa usata dalla vista del bilancio di verifica."""
    gruppo = str(codice or "").split(".", 1)[0]
    return {
        "01": "attivo",
        "02": "passivo",
        "03": "patrimonio_netto",
        "04": "ricavo",
        "05": "costo",
    }.get(gruppo, "altro")


async def _bilancio_verifica_da_registro(
    db, anno: int, dettaglio: bool,
) -> Dict[str, Any]:
    """Aggrega il registro definitivo, senza risommare le fonti operative."""
    anno_str = str(anno)
    periodo_query = {"$or": [
        {"anno": anno},
        {"data_documento": {"$regex": f"^{anno_str}"}},
        {"data": {"$regex": f"^{anno_str}"}},
    ]}
    tutte_scritture = await db["movimenti_contabili"].find(
        periodo_query, {"_id": 0}
    ).sort("data_documento", 1).to_list(100000)
    scritture = [s for s in tutte_scritture if s.get("righe")]
    scritture_senza_righe = len(tutte_scritture) - len(scritture)

    conti = defaultdict(lambda: {
        "codice": "", "nome": "", "tipo": "", "dare": 0.0,
        "avere": 0.0, "n_movimenti": 0, "movimenti": [],
    })
    scritture_sbilanciate = []
    righe_non_numeriche = 0
    righe_senza_conto = 0
    for scrittura in scritture:
        conti_toccati = set()
        dare_scrittura = 0.0
        avere_scrittura = 0.0
        for riga in scrittura.get("righe") or []:
            codice = str(riga.get("conto_codice") or riga.get("conto") or "").strip()
            if not codice:
                righe_senza_conto += 1
                continue
            try:
                dare = float(riga.get("dare") or 0)
                avere = float(riga.get("avere") or 0)
            except (TypeError, ValueError):
                logger.warning("Riga non numerica nella scrittura %s", scrittura.get("id"))
                righe_non_numeriche += 1
                continue
            if not math.isfinite(dare) or not math.isfinite(avere):
                logger.warning("Riga non finita nella scrittura %s", scrittura.get("id"))
                righe_non_numeriche += 1
                continue
            dare_scrittura += dare
            avere_scrittura += avere
            conto = conti[codice]
            conto["codice"] = codice
            conto["nome"] = riga.get("conto_nome") or conto["nome"] or codice
            conto["tipo"] = _tipo_conto_da_codice(codice)
            conto["dare"] += dare
            conto["avere"] += avere
            conti_toccati.add(codice)
            if dettaglio and len(conto["movimenti"]) < 50:
                conto["movimenti"].append({
                    "data": scrittura.get("data_documento") or scrittura.get("data") or "",
                    "descrizione": scrittura.get("descrizione") or "Scrittura contabile",
                    "dare": round(dare, 2), "avere": round(avere, 2),
                    "numero_registrazione": scrittura.get("numero_registrazione"),
                })
        for codice in conti_toccati:
            conti[codice]["n_movimenti"] += 1
        differenza_scrittura = round(dare_scrittura - avere_scrittura, 2)
        if abs(differenza_scrittura) >= 0.01:
            scritture_sbilanciate.append({
                "id": str(scrittura.get("id") or scrittura.get("_id") or ""),
                "numero_registrazione": scrittura.get("numero_registrazione"),
                "data": scrittura.get("data_documento") or scrittura.get("data") or "",
                "dare": round(dare_scrittura, 2),
                "avere": round(avere_scrittura, 2),
                "differenza": differenza_scrittura,
            })

    risultato = []
    for codice in sorted(conti):
        conto = conti[codice]
        saldo = round(conto["dare"] - conto["avere"], 2)
        voce = {
            "codice": codice,
            "nome": conto["nome"],
            "tipo": conto["tipo"],
            "dare": round(conto["dare"], 2),
            "avere": round(conto["avere"], 2),
            "saldo": saldo,
            "saldo_dare": saldo if saldo > 0 else 0,
            "saldo_avere": abs(saldo) if saldo < 0 else 0,
            "n_movimenti": conto["n_movimenti"],
        }
        if dettaglio:
            voce["movimenti"] = conto["movimenti"]
        risultato.append(voce)

    totale_dare = round(sum(v["dare"] for v in risultato), 2)
    totale_avere = round(sum(v["avere"] for v in risultato), 2)
    backlog_fatture = await db[Collections.INVOICES].count_documents({
        "status": {"$nin": ["deleted", "archived"]},
        "$or": [
            {"invoice_date": {"$regex": f"^{anno_str}"}},
            {"data_fattura": {"$regex": f"^{anno_str}"}},
            {"data_documento": {"$regex": f"^{anno_str}"}},
        ],
        "registrata_contabilita": {"$ne": True},
    })
    backlog_corrispettivi = await db[Collections.CORRISPETTIVI].count_documents({
        "entity_status": {"$ne": "deleted"},
        "data": {"$regex": f"^{anno_str}"},
        "registrato_contabilita": {"$ne": True},
    })
    backlog_totale = backlog_fatture + backlog_corrispettivi
    quadratura_totali = abs(totale_dare - totale_avere) < 0.01
    registro_valido = (
        not scritture_sbilanciate
        and scritture_senza_righe == 0
        and righe_non_numeriche == 0
        and righe_senza_conto == 0
    )
    return {
        "success": True,
        "anno": anno,
        "data_generazione": datetime.now(timezone.utc).isoformat(),
        "fonte": "movimenti_contabili",
        "fonte_descrizione": "Registro definitivo in partita doppia",
        "conti": risultato,
        "totali": {
            "dare": totale_dare,
            "avere": totale_avere,
            "saldo_dare": round(sum(v["saldo_dare"] for v in risultato), 2),
            "saldo_avere": round(sum(v["saldo_avere"] for v in risultato), 2),
            "sbilancio": round(totale_dare - totale_avere, 2),
        },
        "quadratura": quadratura_totali and registro_valido,
        "qualita_registro": {
            "quadratura_totali": quadratura_totali,
            "registro_valido": registro_valido,
            "scritture_sbilanciate": len(scritture_sbilanciate),
            "dettaglio_scritture_sbilanciate": scritture_sbilanciate[:50],
            "scritture_senza_righe": scritture_senza_righe,
            "righe_non_numeriche": righe_non_numeriche,
            "righe_senza_conto": righe_senza_conto,
        },
        "completezza_registro": {
            "scritture_registrate": len(scritture),
            "fatture_da_registrare": backlog_fatture,
            "corrispettivi_da_registrare": backlog_corrispettivi,
            "documenti_da_registrare": backlog_totale,
            "completo": backlog_totale == 0 and registro_valido,
        },
        "riepilogo": {
            "n_conti": len(risultato),
            "n_conti_attivo": sum(v["tipo"] == "attivo" for v in risultato),
            "n_conti_passivo": sum(v["tipo"] == "passivo" for v in risultato),
            "n_conti_patrimonio_netto": sum(
                v["tipo"] == "patrimonio_netto" for v in risultato
            ),
            "n_conti_ricavo": sum(v["tipo"] == "ricavo" for v in risultato),
            "n_conti_costo": sum(v["tipo"] == "costo" for v in risultato),
            "n_conti_altro": sum(v["tipo"] == "altro" for v in risultato),
        },
    }


@router.get("/bilancio-verifica")
async def get_bilancio_verifica_completo(
    anno: int = Query(..., description="Anno di riferimento"),
    dettaglio: bool = Query(False, description="Mostra dettaglio movimenti per conto")
) -> Dict[str, Any]:
    """
    Bilancio di Verifica dal registro definitivo in partita doppia.
    Le fonti operative non vengono risommate: i documenti mancanti sono
    riportati separatamente come backlog di registrazione.
    
    Struttura: per ogni conto del piano dei conti mostra:
    - Saldo iniziale (dare/avere)
    - Movimenti periodo (dare/avere)
    - Saldo finale (dare/avere)
    """
    db = Database.get_db()
    return await _bilancio_verifica_da_registro(db, anno, dettaglio)

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
    # solo_aperti=False esplicito: senza, il parametro riceve il default non
    # risolto Query(False, ...) (chiamata Python diretta, non richiesta HTTP),
    # che è truthy — un fornitore con saldo esattamente 0 (conto chiuso/saldato)
    # veniva escluso dal risultato, facendo rispondere erroneamente "nessun
    # movimento" anche quando lo storico esiste (bug trovato lug 2026, stesso
    # pattern di alert_oggi in pos_corrispettivi_check.py).
    result = await get_partitario_fornitori(anno=anno, fornitore_piva=piva, solo_aperti=False)
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
    # Esclude i corrispettivi eliminati (soft-delete su entity_status) —
    # senza questo filtro un doppione cancellato restava sommato nei
    # ricavi consuntivi, falsando lo scostamento Budget vs Consuntivo
    # (stesso bug già corretto in bilancio.py/piano_conti.py).
    query_corr = {
        "$and": [
            {"$or": [
                {"data": {"$regex": f"^{anno_str}"}},
                {"anno": anno}
            ]},
            {"entity_status": {"$ne": "deleted"}},
        ]
    }
    corrispettivi = await db[Collections.CORRISPETTIVI].find(query_corr, {"_id": 0}).to_list(10000)
    
    ricavi_mensili = {m: 0 for m in range(1, 13)}
    for c in corrispettivi:
        data = c.get("data", "")
        try:
            m = int(data[5:7])
        except Exception:
            continue
        if 1 <= m <= 12:
            ricavi_mensili[m] += float(c.get("totale_imponibile") or c.get("totale") or 0)
    
    # --- CONSUNTIVO COSTI (fatture ricevute) ---
    # Esclude le fatture eliminate (status "deleted"/"archived", vedi
    # cascade_operations.py) — stesso motivo del filtro sui corrispettivi
    # sopra: senza questo, una fattura cancellata restava sommata nei
    # costi consuntivi.
    query_fatt = {
        "$and": [
            {"$or": [
                {"data_documento": {"$regex": f"^{anno_str}"}},
                {"anno": anno}
            ]},
            {"status": {"$nin": ["deleted", "archived"]}},
        ]
    }
    fatture = await db[Collections.INVOICES].find(query_fatt, {"_id": 0}).to_list(10000)
    
    costi_mensili = {m: 0 for m in range(1, 13)}
    costi_per_voce = defaultdict(lambda: {m: 0 for m in range(1, 13)})
    
    for f in fatture:
        data_doc = f.get("data_documento", "")
        try:
            m = int(data_doc[5:7])
        except Exception:
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


# ============================================
# 4. LIBRO GIORNALE e LIBRO MASTRO (partita doppia)
#    Vedi memoria/LOGICA_LIBRO_MASTRO.md
# ============================================

@router.get("/libro-giornale")
async def get_libro_giornale(
    data_da: Optional[str] = Query(None, description="Data inizio (YYYY-MM-DD)"),
    data_a: Optional[str] = Query(None, description="Data fine (YYYY-MM-DD)"),
    invoice_key: Optional[str] = Query(None, description="Filtra per chiave fattura"),
    limit: int = Query(500, description="Max scritture da restituire"),
) -> Dict[str, Any]:
    """Libro giornale: elenco cronologico delle scritture in partita doppia.

    A7 (scelta utente 2026-07-13): legge il registro UNICO `movimenti_contabili`
    (motore registrazione_contabile §6.1: fatture, corrispettivi, TFR,
    ammortamenti), non più il registro parallelo `scritture_contabili`
    (rimasto come archivio storico)."""
    db = Database.get_db()
    match: Dict[str, Any] = {"righe": {"$exists": True, "$ne": []}}
    if invoice_key:
        match["$or"] = [{"invoice_key": invoice_key}, {"fattura_id": invoice_key},
                        {"fonte_documento.id": invoice_key}]
    if data_da or data_a:
        match["data_documento"] = {}
        if data_da:
            match["data_documento"]["$gte"] = data_da
        if data_a:
            match["data_documento"]["$lte"] = data_a
    scritture = await db["movimenti_contabili"].find(
        match, {"_id": 0}
    ).sort("data_documento", 1).to_list(limit)
    tot_dare = 0.0
    tot_avere = 0.0
    for s in scritture:
        for r in (s.get("righe") or []):
            tot_dare += float(r.get("dare") or 0)
            tot_avere += float(r.get("avere") or 0)
            # Regola vincolante (CLAUDE.md): il piano dei conti ufficiale è
            # SOLO il CEE. Il codice operativo interno (conto_codice, es.
            # "05.01.01") resta per la ricostruibilità pari-pari richiesta
            # dall'art. 2216 c.c.; qui si AGGIUNGE la conversione ufficiale,
            # senza sostituirlo, così il commercialista legge sempre anche
            # il conto CEE corretto.
            cod_op = r.get("conto_codice") or r.get("conto")
            cod_uff = operativo_a_ufficiale(cod_op) if cod_op else None
            r["conto_codice_ufficiale"] = cod_uff
            r["conto_nome_ufficiale"] = descrizione_ufficiale(cod_uff) if cod_uff else None
    return {
        "success": True,
        "scritture": scritture,
        "totale": len(scritture),
        "totale_dare": round(tot_dare, 2),
        "totale_avere": round(tot_avere, 2),
        "quadratura": abs(round(tot_dare - tot_avere, 2)) < 0.01,
    }


@router.get("/libro-mastro")
async def get_libro_mastro(
    data_da: Optional[str] = Query(None, description="Data inizio (YYYY-MM-DD)"),
    data_a: Optional[str] = Query(None, description="Data fine (YYYY-MM-DD)"),
) -> Dict[str, Any]:
    """Libro mastro: le scritture riclassificate per conto (mastrini) con saldo
    dare/avere. È la base da cui il commercialista ricostruisce la contabilità.

    A7: aggrega il registro UNICO `movimenti_contabili` (righe del motore
    §6.1); gestisce sia `righe.conto_codice` (motore) sia `righe.conto`
    (schema storico)."""
    db = Database.get_db()
    match: Dict[str, Any] = {"righe": {"$exists": True, "$ne": []}}
    if data_da or data_a:
        match["data_documento"] = {}
        if data_da:
            match["data_documento"]["$gte"] = data_da
        if data_a:
            match["data_documento"]["$lte"] = data_a
    pipeline = [
        {"$match": match},
        {"$unwind": "$righe"},
        {"$group": {
            "_id": {"$ifNull": ["$righe.conto_codice", "$righe.conto"]},
            "conto_nome": {"$last": "$righe.conto_nome"},
            "dare": {"$sum": {"$toDouble": {"$ifNull": ["$righe.dare", 0]}}},
            "avere": {"$sum": {"$toDouble": {"$ifNull": ["$righe.avere", 0]}}},
            "righe": {"$sum": 1},
        }},
        {"$sort": {"_id": 1}},
    ]
    mastrini = []
    async for m in db["movimenti_contabili"].aggregate(pipeline):
        dare = round(m.get("dare", 0), 2)
        avere = round(m.get("avere", 0), 2)
        # Stessa regola vincinante del libro giornale: aggiunge il conto
        # ufficiale CEE accanto al codice operativo interno, senza sostituirlo.
        cod_uff = operativo_a_ufficiale(m["_id"]) if m["_id"] else None
        mastrini.append({
            "conto": m["_id"],
            "conto_nome": m.get("conto_nome"),
            "conto_ufficiale": cod_uff,
            "conto_ufficiale_nome": descrizione_ufficiale(cod_uff) if cod_uff else None,
            "dare": dare,
            "avere": avere,
            "saldo": round(dare - avere, 2),
            "movimenti": m.get("righe", 0),
        })
    tot_dare = round(sum(m["dare"] for m in mastrini), 2)
    tot_avere = round(sum(m["avere"] for m in mastrini), 2)
    return {
        "success": True,
        "mastrini": mastrini,
        "totale_conti": len(mastrini),
        "totale_dare": tot_dare,
        "totale_avere": tot_avere,
        "quadratura": abs(round(tot_dare - tot_avere, 2)) < 0.01,
    }


# ============================================
# 5. EXPORT / REIMPORT DEL LIBRO GIORNALE
#    Requisito utente (art. 2216 c.c. + prassi): il registro definitivo deve
#    permettere di RICOSTRUIRE la contabilità pari pari — anche dopo una
#    cancellazione totale, reimportando il registro si ricreano tutte le
#    operazioni con il loro numero di protocollo originale.
# ============================================

@router.get("/libro-giornale/export")
async def export_libro_giornale(
    anno: Optional[int] = Query(None, description="Solo l'anno indicato; vuoto = tutto"),
) -> Dict[str, Any]:
    """Dump completo del registro definitivo (movimenti_contabili con righe).

    Il file è autosufficiente per la ricostruzione: contiene ogni scrittura
    con numero_registrazione (protocollo definitivo), righe DARE/AVERE,
    fonte documento e date originali.
    """
    db = Database.get_db()
    match: Dict[str, Any] = {"righe": {"$exists": True, "$ne": []}}
    if anno:
        match["anno"] = anno
    movimenti = await db["movimenti_contabili"].find(
        match, {"_id": 0}
    ).sort("numero_registrazione", 1).to_list(100000)
    if len(movimenti) >= 100000:
        logger.warning("libro_giornale: raggiunto il tetto di 100000 documenti, possibile troncamento")
    return {
        "tipo": "libro_giornale_gestionalecloud",
        "versione": 1,
        "generato_il": datetime.now(timezone.utc).isoformat(),
        "anno": anno,
        "numero_scritture": len(movimenti),
        "scritture": movimenti,
    }


@router.post("/libro-giornale/import")
async def import_libro_giornale(
    dump: Dict[str, Any],
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Ricostruzione del registro da un export precedente (Admin-only).

    NON distruttivo e idempotente: ogni scrittura viene reinserita SOLO se il
    suo protocollo non esiste già (dedup per `id`, poi per numero_registrazione
    + anno). Le scritture ricreate mantengono numero di protocollo, date e
    righe originali — "pari pari" come registrate all'epoca dei fatti.
    """
    if dump.get("tipo") != "libro_giornale_gestionalecloud":
        raise HTTPException(status_code=400,
                            detail="File non riconosciuto: usare un export del libro giornale")
    db = Database.get_db()
    ricreate, gia_presenti, scartate = 0, 0, 0
    for scrittura in dump.get("scritture", []):
        if not scrittura.get("righe") or not scrittura.get("numero_registrazione"):
            scartate += 1
            continue
        esiste = None
        if scrittura.get("id"):
            esiste = await db["movimenti_contabili"].find_one(
                {"id": scrittura["id"]}, {"_id": 1})
        if not esiste:
            esiste = await db["movimenti_contabili"].find_one(
                {"numero_registrazione": scrittura["numero_registrazione"],
                 "anno": scrittura.get("anno")}, {"_id": 1})
        if esiste:
            gia_presenti += 1
            continue
        await db["movimenti_contabili"].insert_one(dict(scrittura))
        ricreate += 1
    return {
        "success": True,
        "scritture_nel_file": len(dump.get("scritture", [])),
        "ricreate": ricreate,
        "gia_presenti": gia_presenti,
        "scartate_senza_righe_o_protocollo": scartate,
    }


@router.get("/libro-giornale/controllo-60-giorni")
async def controllo_registrazioni_60_giorni() -> Dict[str, Any]:
    """Controllo di conformità DPR 600/73 art. 22: le registrazioni nelle
    scritture cronologiche vanno eseguite entro 60 giorni. Segnala fatture e
    corrispettivi con data documento più vecchia di 60 giorni non ancora
    registrati in contabilità (motore §6.1)."""
    from datetime import timedelta
    db = Database.get_db()
    limite = (datetime.now(timezone.utc) - timedelta(days=60)).strftime("%Y-%m-%d")

    fatture_in_ritardo = await db[Collections.INVOICES].count_documents({
        "$or": [{"invoice_date": {"$lt": limite, "$gt": ""}},
                {"data_fattura": {"$lt": limite, "$gt": ""}}],
        "registrata_contabilita": {"$ne": True},
    })
    corrispettivi_in_ritardo = await db["corrispettivi"].count_documents({
        "data": {"$lt": limite, "$gt": ""},
        "registrato_contabilita": {"$ne": True},
    })
    totale = fatture_in_ritardo + corrispettivi_in_ritardo
    return {
        "limite_60_giorni": limite,
        "fatture_non_registrate_oltre_60gg": fatture_in_ritardo,
        "corrispettivi_non_registrati_oltre_60gg": corrispettivi_in_ritardo,
        "totale_in_ritardo": totale,
        "conforme": totale == 0,
        "azione": None if totale == 0 else
                  "Eseguire la registrazione contabile (Piano dei Conti → Registra fatture / corrispettivi)",
    }
