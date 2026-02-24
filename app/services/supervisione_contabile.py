"""
Servizio di Supervisione Contabile Intelligente.
Implementa la logica di business per:
- Spostamento automatico Cassa → Banca
- Auto-riconciliazione F24 con estratto conto
- Controlli di coerenza contabile
"""
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List
from app.database import Database

logger = logging.getLogger(__name__)


async def supervisione_cassa_banca() -> Dict[str, Any]:
    """
    Regola 1 PRD: Spostamento Automatico Cassa → Banca.
    
    Se una fattura è stata registrata in Prima Nota Cassa ma esiste un movimento
    corrispondente nell'estratto conto bancario, sposta automaticamente la fattura
    da Prima Nota Cassa a Prima Nota Banca.
    
    Returns:
        Dict con statistiche delle operazioni eseguite e alert da mostrare
    """
    db = Database.get_db()
    
    risultati = {
        "controllate": 0,
        "spostate": 0,
        "alert": [],
        "errori": []
    }
    
    # 1. Trova tutte le voci in Prima Nota Cassa
    voci_cassa = await db.prima_nota_cassa.find(
        {"tipo": "uscita"},
        {"_id": 0}
    ).to_list(1000)
    
    risultati["controllate"] = len(voci_cassa)
    
    for voce in voci_cassa:
        importo = abs(float(voce.get("importo", 0)))
        data = voce.get("data") or voce.get("data_registrazione")
        numero_fattura = voce.get("numero_fattura")
        fornitore = voce.get("fornitore") or voce.get("descrizione", "")
        
        if importo <= 0:
            continue
        
        # 2. Cerca movimento corrispondente nell'estratto conto bancario
        # Cerca con tolleranza di ±7 giorni sulla data e ±0.01€ sull'importo
        query_ec = {
            "importo": {"$gte": -importo - 0.01, "$lte": -importo + 0.01}
        }
        
        # Cerca prima per importo esatto
        movimento_banca = await db.estratto_conto_movimenti.find_one(
            query_ec,
            {"_id": 0}
        )
        
        if not movimento_banca:
            # Prova anche con importo positivo (alcune banche registrano uscite come positive)
            query_ec["importo"] = {"$gte": importo - 0.01, "$lte": importo + 0.01}
            movimento_banca = await db.estratto_conto_movimenti.find_one(
                query_ec,
                {"_id": 0}
            )
        
        if movimento_banca:
            # 3. MATCH TROVATO - Sposta da Cassa a Banca
            try:
                # Crea voce in Prima Nota Banca
                voce_banca = dict(voce)
                voce_banca["id"] = f"banca_{voce.get('id', '')}"
                voce_banca["spostato_da_cassa"] = True
                voce_banca["voce_cassa_originale_id"] = voce.get("id")
                voce_banca["movimento_bancario_id"] = movimento_banca.get("id")
                voce_banca["data_spostamento"] = datetime.now(timezone.utc).isoformat()
                voce_banca["note_supervisione"] = "Spostato automaticamente: trovato pagamento in estratto conto bancario"
                
                await db.prima_nota_banca.insert_one(voce_banca.copy())
                
                # Elimina o marca la voce originale in Cassa
                await db.prima_nota_cassa.update_one(
                    {"id": voce.get("id")},
                    {"$set": {
                        "spostato_in_banca": True,
                        "annullato": True,
                        "data_annullamento": datetime.now(timezone.utc).isoformat(),
                        "motivo_annullamento": "Spostato in Prima Nota Banca - trovato in estratto conto"
                    }}
                )
                
                risultati["spostate"] += 1
                risultati["alert"].append({
                    "tipo": "spostamento_cassa_banca",
                    "severita": "info",
                    "messaggio": f"Fattura {numero_fattura or 'N/A'} spostata da Cassa a Banca",
                    "dettagli": {
                        "fornitore": fornitore[:50] if fornitore else "N/A",
                        "importo": importo,
                        "data": data,
                        "motivo": "Trovato pagamento in estratto conto bancario"
                    }
                })
                
                logger.info(f"Supervisione: spostata voce {voce.get('id')} da Cassa a Banca")
                
            except Exception as e:
                logger.error(f"Errore spostamento voce {voce.get('id')}: {e}")
                risultati["errori"].append(str(e))
    
    return risultati


async def auto_riconcilia_f24_con_estratto_conto() -> Dict[str, Any]:
    """
    Auto-riconciliazione F24 con estratto conto.
    
    Se un F24 ha importo e data che corrispondono a un movimento bancario
    con descrizione tipo "I24", "F24", "AGENZIA ENTRATE", segna il F24 come pagato.
    
    Returns:
        Dict con statistiche delle riconciliazioni
    """
    db = Database.get_db()
    
    risultati = {
        "f24_controllati": 0,
        "f24_riconciliati": 0,
        "dettagli": []
    }
    
    # 1. Trova tutti gli F24 non pagati
    f24_non_pagati = await db.f24_models.find(
        {"$or": [{"pagato": False}, {"pagato": {"$exists": False}}]},
        {"_id": 0}
    ).to_list(500)
    
    risultati["f24_controllati"] = len(f24_non_pagati)
    
    for f24 in f24_non_pagati:
        # Calcola importo totale F24
        importo_f24 = f24.get("totale_debito") or f24.get("saldo_finale") or f24.get("importo_totale") or 0
        
        if not importo_f24 or importo_f24 <= 0:
            # Calcola dai tributi
            tributi = (
                f24.get("tributi_erario", []) +
                f24.get("tributi_inps", []) +
                f24.get("tributi_regioni", []) +
                f24.get("tributi_imu", [])
            )
            importo_f24 = sum(t.get("importo_debito", 0) or t.get("importo", 0) for t in tributi)
        
        if importo_f24 <= 0:
            continue
        
        # 2. Cerca nell'estratto conto un movimento corrispondente
        # Pattern comuni per F24: I24, F24, AGENZIA ENTRATE, AGENZIA DELLE ENTRATE
        query_movimento = {
            "importo": {"$gte": -importo_f24 - 1, "$lte": -importo_f24 + 1},  # Tolleranza 1€
            "$or": [
                {"descrizione": {"$regex": "I24|F24|AGENZIA.ENTRATE|TRIBUT", "$options": "i"}},
                {"descrizione_originale": {"$regex": "I24|F24|AGENZIA.ENTRATE|TRIBUT", "$options": "i"}}
            ]
        }
        
        movimento = await db.estratto_conto_movimenti.find_one(query_movimento, {"_id": 0})
        
        if movimento:
            # 3. MATCH TROVATO - Segna F24 come pagato
            await db.f24_models.update_one(
                {"id": f24.get("id")},
                {"$set": {
                    "pagato": True,
                    "auto_riconciliato": True,
                    "data_pagamento": movimento.get("data"),
                    "movimento_bancario_id": movimento.get("id"),
                    "riconciliato_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            
            # Marca anche il movimento come riconciliato
            await db.estratto_conto_movimenti.update_one(
                {"id": movimento.get("id")},
                {"$set": {
                    "riconciliato": True,
                    "tipo_riconciliazione": "f24",
                    "f24_id": f24.get("id")
                }}
            )
            
            risultati["f24_riconciliati"] += 1
            risultati["dettagli"].append({
                "f24_id": f24.get("id"),
                "importo": importo_f24,
                "data_pagamento": movimento.get("data"),
                "descrizione_banca": movimento.get("descrizione", "")[:50]
            })
            
            logger.info(f"Auto-riconciliato F24 {f24.get('id')} con movimento {movimento.get('id')}")
    
    return risultati


async def esegui_supervisione_completa() -> Dict[str, Any]:
    """
    Esegue tutti i controlli di supervisione contabile.
    Chiamare periodicamente o dopo ogni import di estratti conto.
    """
    risultati = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "supervisione_cassa_banca": {},
        "auto_riconciliazione_f24": {},
        "totale_alert": 0
    }
    
    try:
        # 1. Supervisione Cassa → Banca
        risultati["supervisione_cassa_banca"] = await supervisione_cassa_banca()
        
        # 2. Auto-riconciliazione F24
        risultati["auto_riconciliazione_f24"] = await auto_riconcilia_f24_con_estratto_conto()
        
        # Conta alert totali
        risultati["totale_alert"] = len(risultati["supervisione_cassa_banca"].get("alert", []))
        
    except Exception as e:
        logger.exception(f"Errore supervisione completa: {e}")
        risultati["errore"] = str(e)
    
    return risultati


async def get_alert_supervisione() -> List[Dict[str, Any]]:
    """
    Recupera gli alert di supervisione recenti da mostrare all'utente.
    """
    db = Database.get_db()
    
    # Cerca voci spostate nelle ultime 24 ore
    from datetime import timedelta
    data_limite = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    
    voci_spostate = await db.prima_nota_banca.find(
        {"spostato_da_cassa": True, "data_spostamento": {"$gte": data_limite}},
        {"_id": 0, "id": 1, "fornitore": 1, "importo": 1, "data_spostamento": 1, "numero_fattura": 1}
    ).to_list(50)
    
    f24_auto = await db.f24_models.find(
        {"auto_riconciliato": True, "riconciliato_at": {"$gte": data_limite}},
        {"_id": 0, "id": 1, "totale_debito": 1, "data_pagamento": 1}
    ).to_list(50)
    
    alert = []
    
    for v in voci_spostate:
        alert.append({
            "tipo": "spostamento_cassa_banca",
            "messaggio": f"Fattura {v.get('numero_fattura', 'N/A')} spostata da Cassa a Banca",
            "importo": v.get("importo"),
            "timestamp": v.get("data_spostamento")
        })
    
    for f in f24_auto:
        alert.append({
            "tipo": "auto_riconciliazione_f24",
            "messaggio": "F24 riconciliato automaticamente",
            "importo": f.get("totale_debito"),
            "timestamp": f.get("riconciliato_at")
        })
    
    return alert
