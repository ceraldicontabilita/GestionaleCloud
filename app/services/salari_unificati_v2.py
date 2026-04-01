"""
Servizio Gestione Salari Unificata V2
======================================

Migliora il flusso cedolini → prima nota → riconciliazione con:

1. PARSING COMPLETO: Estrae anche ferie, ROL, permessi, contributi INPS, 
   addizionali, TFR dal cedolino (non solo netto/lordo)
   
2. PAGAMENTI PARZIALI: Gestisce acconti e saldi residui per dipendente
   - Ogni pagamento (bonifico, assegno) viene registrato
   - Il saldo debito/credito si aggiorna progressivamente
   
3. RICONCILIAZIONE BANCA: Confronta estratto conto con cedolini
   - Match automatico per nome/IBAN/importo
   - Segna come pagato e aggiorna saldo
   
4. SALDI COMPLETI: Per ogni dipendente restituisce:
   - Ferie maturate, godute, residue
   - ROL maturato, goduto, residuo
   - Permessi ex-festività
   - TFR accantonato
   - Saldo stipendio (debito/credito con storico acconti)

Collections coinvolte:
- cedolini: cedolini parsati con tutti i dettagli
- prima_nota_salari: movimenti stipendio (debiti)
- pagamenti_salari: pagamenti effettuati (acconti + saldi)
- estratto_conto_movimenti: movimenti bancari per riconciliazione
- anagrafica_dipendenti: dati dipendente + saldi ferie/ROL
"""

import logging
import uuid
import re
from datetime import datetime, timezone, date
from typing import Dict, Any, List, Optional
import calendar

logger = logging.getLogger(__name__)


# ============================================================
# 1. PARSING CEDOLINO COMPLETO (ferie, ROL, contributi)
# ============================================================

def estrai_ferie_rol_from_text(text: str) -> Dict[str, Any]:
    """
    Estrae ferie, ROL, permessi, contributi dal testo del cedolino.
    Supporta formati CSC e Zucchetti.
    """
    result = {
        "ferie_maturate": 0,
        "ferie_godute": 0,
        "ferie_residue": 0,
        "ferie_residuo_ap": 0,  # Anno precedente
        "rol_maturato": 0,
        "rol_goduto": 0,
        "rol_residuo": 0,
        "permessi_ex_fest_maturati": 0,
        "permessi_ex_fest_goduti": 0,
        "permessi_ex_fest_residui": 0,
        "contributi_inps": 0,
        "contributi_inps_azienda": 0,
        "irpef": 0,
        "addizionale_regionale": 0,
        "addizionale_comunale": 0,
        "bonus_renzi_trattamento": 0,
        "tfr_mese": 0,
        "tfr_accantonato": 0,
        "inail": 0,
        "totale_competenze": 0,
        "totale_trattenute": 0,
    }
    
    def parse_importo(val):
        if not val:
            return 0.0
        val = str(val).strip().replace('.', '').replace(',', '.').replace(' ', '')
        val = re.sub(r'[^\d.\-]', '', val)
        try:
            return abs(float(val))
        except (ValueError, TypeError):
            return 0.0
    
    # === FERIE ===
    # Formato: "Ferie  8,66666  14,00000  -5,33334 GG."
    # (maturate, godute, residuo)
    ferie_3col = re.search(r'Ferie\s+([\d,.\-]+)\s+([\d,.\-]+)\s+([\d,.\-]+)', text)
    if ferie_3col:
        result["ferie_maturate"] = parse_importo(ferie_3col.group(1))
        result["ferie_godute"] = parse_importo(ferie_3col.group(2))
        result["ferie_residue"] = parse_importo(ferie_3col.group(3))
    
    # Formato: "FERIE RES. 12,5"
    ferie_res = re.search(r'FERIE\s*RES\.?\s*([\d,.\-]+)', text, re.IGNORECASE)
    if ferie_res and result["ferie_residue"] == 0:
        result["ferie_residue"] = parse_importo(ferie_res.group(1))
    
    # Ferie maturate singole
    ferie_mat = re.search(r'Mat\.\s*([\d,.\-]+)\+?\s*Mat\.', text)
    if ferie_mat and result["ferie_maturate"] == 0:
        result["ferie_maturate"] = parse_importo(ferie_mat.group(1))
    
    # Ferie godute singole
    ferie_god = re.search(r'God\.\s*([\d,.\-]+)\+', text)
    if ferie_god and result["ferie_godute"] == 0:
        result["ferie_godute"] = parse_importo(ferie_god.group(1))
    
    # Residuo anno precedente
    ferie_ap = re.search(r'Residuo\s*(?:AP|a\.p\.)\s*([\d,.\-]+)', text, re.IGNORECASE)
    if ferie_ap:
        result["ferie_residuo_ap"] = parse_importo(ferie_ap.group(1))
    
    # === ROL ===
    # Formato: "Permessi  12,00000  12,00000 ORE"
    rol_3col = re.search(r'Permessi\s+([\d,.\-]+)\s+([\d,.\-]+)\s*ORE', text)
    if rol_3col:
        result["rol_maturato"] = parse_importo(rol_3col.group(1))
        result["rol_residuo"] = parse_importo(rol_3col.group(2))
    
    # Formato: "ROL RES 24,00"
    rol_res = re.search(r'ROL\s*RES\.?\s*([\d,.\-]+)', text, re.IGNORECASE)
    if rol_res and result["rol_residuo"] == 0:
        result["rol_residuo"] = parse_importo(rol_res.group(1))
    
    # ROL maturato singolo
    rol_mat = re.search(r'R\.?O\.?L\.?\s*(?:mat|maturato)\s*([\d,.\-]+)', text, re.IGNORECASE)
    if rol_mat and result["rol_maturato"] == 0:
        result["rol_maturato"] = parse_importo(rol_mat.group(1))
    
    # ROL goduto
    rol_god = re.search(r'R\.?O\.?L\.?\s*(?:god|goduto)\s*([\d,.\-]+)', text, re.IGNORECASE)
    if rol_god:
        result["rol_goduto"] = parse_importo(rol_god.group(1))
    
    # === EX FESTIVITA ===
    exf = re.search(r'Ex[- ]?[Ff]est\w*\s+([\d,.\-]+)\s+([\d,.\-]+)', text)
    if exf:
        result["permessi_ex_fest_maturati"] = parse_importo(exf.group(1))
        result["permessi_ex_fest_residui"] = parse_importo(exf.group(2))
    
    # === CONTRIBUTI INPS ===
    inps = re.search(r'(?:Contributo\s*IVS|INPS\s*dip|Contrib.*previd)\w*.*?([\d.,]+)\s*$', text, re.IGNORECASE | re.MULTILINE)
    if inps:
        result["contributi_inps"] = parse_importo(inps.group(1))
    
    inps_az = re.search(r'(?:INPS\s*az|Contrib.*azienda)\w*.*?([\d.,]+)\s*$', text, re.IGNORECASE | re.MULTILINE)
    if inps_az:
        result["contributi_inps_azienda"] = parse_importo(inps_az.group(1))
    
    # === IRPEF ===
    irpef = re.search(r'(?:RITENUTE?\s*FISCALI?|IRPEF|Ritenute?\s*IRPEF)\s*[:\s]*([\d.,]+)', text, re.IGNORECASE)
    if irpef:
        result["irpef"] = parse_importo(irpef.group(1))
    
    # === ADDIZIONALI ===
    add_reg = re.search(r'Add(?:izionale)?\s*[Rr]eg(?:ionale)?\s*[:\s]*([\d.,]+)', text)
    if add_reg:
        result["addizionale_regionale"] = parse_importo(add_reg.group(1))
    
    add_com = re.search(r'Add(?:izionale)?\s*[Cc]om(?:unale)?\s*[:\s]*([\d.,]+)', text)
    if add_com:
        result["addizionale_comunale"] = parse_importo(add_com.group(1))
    
    # === BONUS RENZI / TRATTAMENTO INTEGRATIVO ===
    bonus = re.search(r'(?:Bonus|Trattamento\s*integrativo|DL\s*3/2020)\s*[:\s]*([\d.,]+)', text, re.IGNORECASE)
    if bonus:
        result["bonus_renzi_trattamento"] = parse_importo(bonus.group(1))
    
    # === TFR ===
    tfr_mese = re.search(r'(?:Quota\s*anno|T\.?F\.?R\.?\s*mese|Accant.*TFR)\s*[:\s]*([\d.,]+)', text, re.IGNORECASE)
    if tfr_mese:
        result["tfr_mese"] = parse_importo(tfr_mese.group(1))
    
    tfr_tot = re.search(r'(?:TFR\s*accanton|Fondo\s*TFR)\w*\s*[:\s]*([\d.,]+)', text, re.IGNORECASE)
    if tfr_tot:
        result["tfr_accantonato"] = parse_importo(tfr_tot.group(1))
    
    # === INAIL ===
    inail = re.search(r'INAIL\s*[:\s]*([\d.,]+)', text, re.IGNORECASE)
    if inail:
        result["inail"] = parse_importo(inail.group(1))
    
    # === TOTALI ===
    comp = re.search(r'TOTALE\s*COMPETENZE\s*[:\s]*([\d.,]+)', text, re.IGNORECASE)
    if comp:
        result["totale_competenze"] = parse_importo(comp.group(1))
    
    tratt = re.search(r'TOTALE\s*TRATTENUTE\s*[:\s]*([\d.,]+)', text, re.IGNORECASE)
    if tratt:
        result["totale_trattenute"] = parse_importo(tratt.group(1))
    
    return result


# ============================================================
# 2. PROCESSAMENTO CEDOLINO COMPLETO V2
# ============================================================

async def processa_cedolino_v2(
    db,
    cedolino_data: Dict[str, Any],
    pdf_text: str = "",
    filename: str = "",
    pdf_data: str = None
) -> Dict[str, Any]:
    """
    Processa cedolino con estrazione completa ferie/ROL/contributi.
    
    1. Estrae dati aggiuntivi dal testo PDF
    2. Salva cedolino completo in collection 'cedolini'
    3. Aggiorna anagrafica dipendente con ferie/ROL
    4. Crea movimento in prima_nota_salari  
    5. Tenta riconciliazione con estratto conto
    """
    result = {
        "success": False,
        "cedolino_id": None,
        "dipendente_id": None,
        "prima_nota_id": None,
        "riconciliato": False,
        "ferie_aggiornate": False,
        "errore": None
    }
    
    try:
        cf = (cedolino_data.get("codice_fiscale") or "").upper()
        nome = cedolino_data.get("nome_dipendente") or ""
        mese = cedolino_data.get("mese")
        anno = cedolino_data.get("anno")
        netto = float(cedolino_data.get("netto_mese") or cedolino_data.get("netto") or 0)
        lordo = float(cedolino_data.get("lordo") or 0)
        
        if not cf or not mese or not anno or netto == 0:
            result["errore"] = "Dati mancanti (CF, mese, anno, o netto=0)"
            return result
        
        # --- Estrai dati aggiuntivi dal testo PDF ---
        dati_extra = {}
        if pdf_text:
            dati_extra = estrai_ferie_rol_from_text(pdf_text)
        
        # Merge con dati dal parser multi-template se presenti
        ferie_permessi = cedolino_data.get("ferie_permessi", {})
        if ferie_permessi:
            for key, val in ferie_permessi.items():
                mapped_key = {
                    "ferie_maturate": "ferie_maturate",
                    "ferie_godute": "ferie_godute", 
                    "ferie_residuo": "ferie_residue",
                    "permessi_maturati": "rol_maturato",
                    "permessi_residuo": "rol_residuo",
                    "permessi_goduti": "rol_goduto",
                }.get(key, key)
                if val and (not dati_extra.get(mapped_key)):
                    dati_extra[mapped_key] = float(val)
        
        # --- 1. Anagrafica dipendente ---
        dipendente = await db["employees"].find_one({"codice_fiscale": cf})
        
        if dipendente:
            dipendente_id = dipendente.get("id")
            update_anagrafica = {
                "ultimo_cedolino": f"{mese:02d}/{anno}",
                "ultimo_netto": netto,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            
            # Aggiorna ferie/ROL se presenti
            if dati_extra.get("ferie_residue"):
                update_anagrafica["ferie_residue"] = dati_extra["ferie_residue"]
                update_anagrafica["ferie_maturate_anno"] = dati_extra.get("ferie_maturate", 0)
                update_anagrafica["ferie_godute_anno"] = dati_extra.get("ferie_godute", 0)
                update_anagrafica["ferie_residuo_ap"] = dati_extra.get("ferie_residuo_ap", 0)
                result["ferie_aggiornate"] = True
            
            if dati_extra.get("rol_residuo"):
                update_anagrafica["rol_residuo"] = dati_extra["rol_residuo"]
                update_anagrafica["rol_maturato_anno"] = dati_extra.get("rol_maturato", 0)
                update_anagrafica["rol_goduto_anno"] = dati_extra.get("rol_goduto", 0)
                result["ferie_aggiornate"] = True
            
            if dati_extra.get("permessi_ex_fest_residui"):
                update_anagrafica["permessi_ex_fest_residui"] = dati_extra["permessi_ex_fest_residui"]
            
            if dati_extra.get("tfr_accantonato"):
                update_anagrafica["tfr_accantonato"] = dati_extra["tfr_accantonato"]
            elif dati_extra.get("tfr_mese"):
                update_anagrafica["tfr_ultimo_mese"] = dati_extra["tfr_mese"]
            
            iban = cedolino_data.get("iban")
            if iban and iban != dipendente.get("iban"):
                update_anagrafica["iban"] = iban
            
            await db["employees"].update_one(
                {"codice_fiscale": cf},
                {"$set": update_anagrafica}
            )
        else:
            # Crea nuova anagrafica
            dipendente_id = str(uuid.uuid4())
            parti_nome = nome.split() if nome else []
            
            nuova = {
                "id": dipendente_id,
                "codice_fiscale": cf,
                "cognome": parti_nome[0] if parti_nome else "",
                "nome": " ".join(parti_nome[1:]) if len(parti_nome) > 1 else "",
                "nome_completo": nome,
                "iban": cedolino_data.get("iban"),
                "stato": "attivo",
                "primo_cedolino": f"{mese:02d}/{anno}",
                "ultimo_cedolino": f"{mese:02d}/{anno}",
                "ultimo_netto": netto,
                "ferie_residue": dati_extra.get("ferie_residue", 0),
                "rol_residuo": dati_extra.get("rol_residuo", 0),
                "tfr_accantonato": dati_extra.get("tfr_accantonato", 0),
                "source": "auto_cedolino_v2",
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await db["employees"].insert_one(dict(nuova).copy())
        
        result["dipendente_id"] = dipendente_id
        
        # --- 2. Salva cedolino COMPLETO ---
        cedolino_id = str(uuid.uuid4())
        
        cedolino_record = {
            "id": cedolino_id,
            "dipendente_id": dipendente_id,
            "nome_dipendente": nome,
            "codice_fiscale": cf,
            "mese": int(mese),
            "anno": int(anno),
            "periodo": f"{int(mese):02d}/{int(anno)}",
            # Importi principali
            "netto": netto,
            "netto_mese": netto,
            "lordo": lordo,
            "totale_competenze": dati_extra.get("totale_competenze", lordo),
            "totale_trattenute": dati_extra.get("totale_trattenute") or cedolino_data.get("totale_trattenute", 0),
            # Trattenute dettaglio
            "irpef": dati_extra.get("irpef", 0),
            "contributi_inps": dati_extra.get("contributi_inps", 0),
            "contributi_inps_azienda": dati_extra.get("contributi_inps_azienda", 0),
            "addizionale_regionale": dati_extra.get("addizionale_regionale", 0),
            "addizionale_comunale": dati_extra.get("addizionale_comunale", 0),
            "bonus_renzi_trattamento": dati_extra.get("bonus_renzi_trattamento", 0),
            "inail": dati_extra.get("inail", 0),
            # Ferie e permessi
            "ferie_maturate": dati_extra.get("ferie_maturate", 0),
            "ferie_godute": dati_extra.get("ferie_godute", 0),
            "ferie_residue": dati_extra.get("ferie_residue", 0),
            "ferie_residuo_ap": dati_extra.get("ferie_residuo_ap", 0),
            "rol_maturato": dati_extra.get("rol_maturato", 0),
            "rol_goduto": dati_extra.get("rol_goduto", 0),
            "rol_residuo": dati_extra.get("rol_residuo", 0),
            "permessi_ex_fest": dati_extra.get("permessi_ex_fest_residui", 0),
            # TFR
            "tfr_mese": dati_extra.get("tfr_mese") or cedolino_data.get("tfr_quota", 0),
            "tfr_accantonato": dati_extra.get("tfr_accantonato", 0),
            # Ore
            "ore_lavorate": cedolino_data.get("ore_lavorate", 0),
            # Pagamento
            "iban": cedolino_data.get("iban"),
            "pagato": False,
            "importo_pagato": 0,
            "saldo_residuo": netto,  # Inizialmente tutto da pagare
            "pagamenti": [],  # Lista acconti/pagamenti
            # Meta
            "filename": filename,
            "formato": cedolino_data.get("formato_rilevato"),
            "source": "cedolino_v2",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        # Upsert per evitare duplicati
        await db["cedolini"].update_one(
            {"codice_fiscale": cf, "mese": int(mese), "anno": int(anno)},
            {"$set": cedolino_record},
            upsert=True
        )
        result["cedolino_id"] = cedolino_id
        
        # --- 3. Prima Nota Salari ---
        existing_pn = await db["prima_nota_salari"].find_one({
            "codice_fiscale": cf,
            "mese": int(mese),
            "anno": int(anno),
            "tipo": "stipendio"
        })
        
        if not existing_pn:
            ultimo_giorno = calendar.monthrange(int(anno), int(mese))[1]
            pn_id = str(uuid.uuid4())
            
            pn_record = {
                "id": pn_id,
                "dipendente_id": dipendente_id,
                "dipendente": nome.upper(),
                "dipendente_nome": nome,
                "codice_fiscale": cf,
                "data": f"{anno}-{int(mese):02d}-{ultimo_giorno:02d}",
                "mese": int(mese),
                "anno": int(anno),
                "importo_busta": netto,
                "importo_bonifico": 0,
                "saldo": -netto,  # Debito verso dipendente
                "progressivo": 0,
                "tipo": "stipendio",
                "riconciliato": False,
                "descrizione": f"Stipendio {nome} - {int(mese):02d}/{anno}",
                "cedolino_id": cedolino_id,
                "source": "cedolino_v2",
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            await db["prima_nota_salari"].insert_one(dict(pn_record).copy())
            result["prima_nota_id"] = pn_id
        
        # --- 4. Riconciliazione automatica ---
        from app.services.cedolini_manager import riconcilia_stipendio_automatico
        
        riconc = await riconcilia_stipendio_automatico(
            db, nome, netto, int(mese), int(anno),
            result.get("prima_nota_id") or (existing_pn or {}).get("id", ""),
            cedolino_data.get("iban")
        )
        
        if riconc:
            result["riconciliato"] = True
            # Aggiorna cedolino come pagato
            await db["cedolini"].update_one(
                {"codice_fiscale": cf, "mese": int(mese), "anno": int(anno)},
                {"$set": {
                    "pagato": True,
                    "importo_pagato": netto,
                    "saldo_residuo": 0,
                    "metodo_pagamento": "bonifico",
                    "riconciliato_auto": True
                }}
            )
        
        result["success"] = True
        
    except Exception as e:
        logger.error(f"Errore processa_cedolino_v2: {e}")
        result["errore"] = str(e)
    
    return result


# ============================================================
# 3. REGISTRA PAGAMENTO (acconti e saldi)
# ============================================================

async def registra_pagamento_salario(
    db,
    cedolino_id: str,
    importo: float,
    metodo: str = "bonifico",
    data_pagamento: str = None,
    note: str = "",
    tipo_pagamento: str = "saldo"  # "acconto" o "saldo"
) -> Dict[str, Any]:
    """
    Registra pagamento (totale o parziale) per un cedolino.
    Gestisce acconti multipli e calcola saldo residuo.
    """
    cedolino = await db["cedolini"].find_one({"id": cedolino_id})
    if not cedolino:
        return {"success": False, "errore": "Cedolino non trovato"}
    
    if importo <= 0:
        return {"success": False, "errore": "Importo deve essere > 0"}
    
    netto = float(cedolino.get("netto") or cedolino.get("netto_mese") or 0)
    pagato_finora = float(cedolino.get("importo_pagato") or 0)
    
    if not data_pagamento:
        data_pagamento = datetime.now(timezone.utc).isoformat()[:10]
    
    # Calcola nuovo saldo
    nuovo_pagato = pagato_finora + importo
    nuovo_residuo = round(netto - nuovo_pagato, 2)
    
    # Crea record pagamento
    pagamento_id = str(uuid.uuid4())
    pagamento = {
        "id": pagamento_id,
        "cedolino_id": cedolino_id,
        "dipendente_id": cedolino.get("dipendente_id"),
        "codice_fiscale": cedolino.get("codice_fiscale"),
        "nome_dipendente": cedolino.get("nome_dipendente"),
        "importo": importo,
        "metodo": metodo,
        "data_pagamento": data_pagamento,
        "tipo": tipo_pagamento,
        "note": note,
        "netto_cedolino": netto,
        "pagato_prima": pagato_finora,
        "pagato_dopo": nuovo_pagato,
        "saldo_residuo": nuovo_residuo,
        "mese": cedolino.get("mese"),
        "anno": cedolino.get("anno"),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db["pagamenti_salari"].insert_one(dict(pagamento).copy())
    
    # Aggiorna cedolino
    pagamenti_lista = cedolino.get("pagamenti", [])
    pagamenti_lista.append({
        "id": pagamento_id,
        "importo": importo,
        "metodo": metodo,
        "data": data_pagamento,
        "tipo": tipo_pagamento
    })
    
    update_ced = {
        "importo_pagato": round(nuovo_pagato, 2),
        "saldo_residuo": nuovo_residuo,
        "pagamenti": pagamenti_lista,
        "pagato": nuovo_residuo <= 0.01,  # Pagato se saldo ≤ 0.01€
        "metodo_pagamento": metodo,
        "data_pagamento": data_pagamento,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db["cedolini"].update_one({"id": cedolino_id}, {"$set": update_ced})
    
    # Registra in prima nota
    pn_collection = "prima_nota_cassa" if metodo in ["contanti", "cassa"] else "prima_nota_banca"
    
    pn_movimento = {
        "id": str(uuid.uuid4()),
        "data": data_pagamento,
        "tipo": "uscita",
        "importo": importo,
        "descrizione": f"{'Acconto' if tipo_pagamento == 'acconto' else 'Stipendio'} "
                       f"{cedolino.get('nome_dipendente', '')} - {cedolino.get('mese', '')}/{cedolino.get('anno', '')}",
        "categoria": "Stipendi",
        "cedolino_id": cedolino_id,
        "pagamento_id": pagamento_id,
        "codice_fiscale": cedolino.get("codice_fiscale"),
        "source": "pagamento_salario_v2",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db[pn_collection].insert_one(dict(pn_movimento).copy())
    
    return {
        "success": True,
        "pagamento_id": pagamento_id,
        "importo_pagato": importo,
        "totale_pagato": round(nuovo_pagato, 2),
        "saldo_residuo": nuovo_residuo,
        "stato": "pagato" if nuovo_residuo <= 0.01 else f"acconto (residuo €{nuovo_residuo})"
    }


# ============================================================
# 4. SALDI COMPLETI PER DIPENDENTE
# ============================================================

async def get_saldo_completo_dipendente(
    db,
    codice_fiscale: str = None,
    dipendente_id: str = None,
    anno: int = None
) -> Dict[str, Any]:
    """
    Restituisce saldo completo di un dipendente:
    - Ferie maturate, godute, residue
    - ROL maturato, goduto, residuo
    - TFR accantonato
    - Saldo stipendi (debito/credito)
    - Storico pagamenti con acconti
    """
    if not anno:
        anno = datetime.now().year
    
    # Trova dipendente
    query_dip = {}
    if codice_fiscale:
        query_dip = {"codice_fiscale": codice_fiscale}
    elif dipendente_id:
        query_dip = {"id": dipendente_id}
    else:
        return {"errore": "Specificare codice_fiscale o dipendente_id"}
    
    dipendente = await db["employees"].find_one(query_dip, {"_id": 0})
    if not dipendente:
        return {"errore": "Dipendente non trovato"}
    
    cf = dipendente.get("codice_fiscale")
    
    # Cedolini dell'anno
    cedolini = await db["cedolini"].find(
        {"codice_fiscale": cf, "anno": {"$in": [anno, str(anno)]}},
        {"_id": 0}
    ).sort([("mese", 1)]).to_list(20)
    
    # Pagamenti dell'anno
    pagamenti = await db["pagamenti_salari"].find(
        {"codice_fiscale": cf, "anno": {"$in": [anno, str(anno)]}},
        {"_id": 0}
    ).sort([("data_pagamento", 1)]).to_list(100)
    
    # Calcola saldi stipendi
    totale_netto = sum(float(c.get("netto") or c.get("netto_mese") or 0) for c in cedolini)
    totale_pagato = sum(float(c.get("importo_pagato") or 0) for c in cedolini)
    saldo_stipendi = round(totale_pagato - totale_netto, 2)  # Positivo = credito azienda, Negativo = debito
    
    # Cedolini non pagati
    non_pagati = [c for c in cedolini if not c.get("pagato")]
    parzialmente_pagati = [c for c in cedolini if c.get("importo_pagato", 0) > 0 and not c.get("pagato")]
    
    # Ultimo cedolino per ferie/ROL attuali
    ultimo_cedolino = cedolini[-1] if cedolini else {}
    
    # Ferie/ROL dal dipendente o dall'ultimo cedolino
    ferie_residue = (dipendente.get("ferie_residue") or 
                     ultimo_cedolino.get("ferie_residue") or 0)
    rol_residuo = (dipendente.get("rol_residuo") or 
                   ultimo_cedolino.get("rol_residuo") or 0)
    
    # TFR
    tfr_anno = sum(float(c.get("tfr_mese") or 0) for c in cedolini)
    tfr_totale = dipendente.get("tfr_accantonato") or ultimo_cedolino.get("tfr_accantonato") or 0
    
    return {
        "dipendente": {
            "id": dipendente.get("id"),
            "nome_completo": dipendente.get("nome_completo"),
            "codice_fiscale": cf,
            "iban": dipendente.get("iban"),
            "stato": dipendente.get("stato")
        },
        "anno": anno,
        "stipendi": {
            "totale_netto_anno": round(totale_netto, 2),
            "totale_pagato_anno": round(totale_pagato, 2),
            "saldo": saldo_stipendi,  # Neg = debito verso dip, Pos = credito azienda
            "saldo_label": f"{'Credito azienda' if saldo_stipendi >= 0 else 'Debito verso dipendente'} €{abs(saldo_stipendi):,.2f}",
            "cedolini_anno": len(cedolini),
            "cedolini_pagati": len([c for c in cedolini if c.get("pagato")]),
            "cedolini_non_pagati": len(non_pagati),
            "cedolini_parziali": len(parzialmente_pagati),
        },
        "dettaglio_mesi": [
            {
                "mese": c.get("mese"),
                "periodo": c.get("periodo"),
                "netto": float(c.get("netto") or c.get("netto_mese") or 0),
                "pagato": float(c.get("importo_pagato") or 0),
                "residuo": float(c.get("saldo_residuo") or (float(c.get("netto") or c.get("netto_mese") or 0) - float(c.get("importo_pagato") or 0))),
                "stato": "✅ Pagato" if c.get("pagato") else 
                         f"⚠️ Acconto €{c.get('importo_pagato', 0)}" if c.get("importo_pagato", 0) > 0 else "❌ Da pagare",
                "pagamenti": c.get("pagamenti", [])
            }
            for c in cedolini
        ],
        "ferie_permessi": {
            "ferie_residue": round(float(ferie_residue), 2),
            "ferie_maturate_anno": round(float(dipendente.get("ferie_maturate_anno") or ultimo_cedolino.get("ferie_maturate") or 0), 2),
            "ferie_godute_anno": round(float(dipendente.get("ferie_godute_anno") or ultimo_cedolino.get("ferie_godute") or 0), 2),
            "ferie_residuo_ap": round(float(dipendente.get("ferie_residuo_ap") or ultimo_cedolino.get("ferie_residuo_ap") or 0), 2),
            "rol_residuo": round(float(rol_residuo), 2),
            "rol_maturato_anno": round(float(dipendente.get("rol_maturato_anno") or ultimo_cedolino.get("rol_maturato") or 0), 2),
            "rol_goduto_anno": round(float(dipendente.get("rol_goduto_anno") or ultimo_cedolino.get("rol_goduto") or 0), 2),
            "permessi_ex_fest": round(float(dipendente.get("permessi_ex_fest_residui") or ultimo_cedolino.get("permessi_ex_fest") or 0), 2),
        },
        "tfr": {
            "accantonamento_anno": round(tfr_anno, 2),
            "totale_accantonato": round(float(tfr_totale), 2),
        },
        "pagamenti_recenti": [
            {
                "data": p.get("data_pagamento"),
                "importo": p.get("importo"),
                "metodo": p.get("metodo"),
                "tipo": p.get("tipo"),
                "note": p.get("note"),
                "mese_rif": p.get("mese"),
            }
            for p in pagamenti[-10:]  # Ultimi 10
        ]
    }


# ============================================================
# 5. RIEPILOGO TUTTI I DIPENDENTI
# ============================================================

async def get_riepilogo_salari_tutti(db, anno: int = None) -> Dict[str, Any]:
    """
    Riepilogo salari per tutti i dipendenti attivi.
    Mostra saldo debito/credito, ferie, ROL per ciascuno.
    """
    if not anno:
        anno = datetime.now().year
    
    dipendenti = await db["employees"].find(
        {"stato": {"$ne": "cessato"}},
        {"_id": 0}
    ).sort("cognome", 1).to_list(200)
    
    riepilogo = []
    totale_debito = 0
    totale_credito = 0
    
    for dip in dipendenti:
        cf = dip.get("codice_fiscale")
        if not cf:
            continue
        
        # Cedolini anno
        cedolini = await db["cedolini"].find(
            {"codice_fiscale": cf, "anno": {"$in": [anno, str(anno)]}},
            {"_id": 0, "netto": 1, "netto_mese": 1, "importo_pagato": 1, "pagato": 1, 
             "mese": 1, "saldo_residuo": 1, "ferie_residue": 1, "rol_residuo": 1}
        ).to_list(20)
        
        netto_tot = sum(float(c.get("netto") or c.get("netto_mese") or 0) for c in cedolini)
        pagato_tot = sum(float(c.get("importo_pagato") or 0) for c in cedolini)
        saldo = round(pagato_tot - netto_tot, 2)
        
        non_pagati = len([c for c in cedolini if not c.get("pagato")])
        
        # Ferie/ROL dall'ultimo cedolino o anagrafica
        ultimo = cedolini[-1] if cedolini else {}
        ferie = float(dip.get("ferie_residue") or ultimo.get("ferie_residue") or 0)
        rol = float(dip.get("rol_residuo") or ultimo.get("rol_residuo") or 0)
        
        if saldo < 0:
            totale_debito += abs(saldo)
        else:
            totale_credito += saldo
        
        riepilogo.append({
            "dipendente_id": dip.get("id"),
            "nome": dip.get("nome_completo") or f"{dip.get('cognome', '')} {dip.get('nome', '')}",
            "codice_fiscale": cf,
            "cedolini_anno": len(cedolini),
            "non_pagati": non_pagati,
            "netto_totale": round(netto_tot, 2),
            "pagato_totale": round(pagato_tot, 2),
            "saldo": saldo,
            "saldo_tipo": "credito" if saldo >= 0 else "debito",
            "ferie_residue": round(ferie, 2),
            "rol_residuo": round(rol, 2),
            "evidenziato": saldo < -0.01 or non_pagati > 0,  # Highlight se debito o non pagato
        })
    
    # Ordina: prima quelli con debito (evidenziati), poi gli altri
    riepilogo.sort(key=lambda x: (not x["evidenziato"], x["saldo"]))
    
    return {
        "anno": anno,
        "dipendenti": riepilogo,
        "totali": {
            "dipendenti_attivi": len(riepilogo),
            "totale_netto_anno": round(sum(r["netto_totale"] for r in riepilogo), 2),
            "totale_pagato_anno": round(sum(r["pagato_totale"] for r in riepilogo), 2),
            "totale_debito": round(totale_debito, 2),
            "totale_credito": round(totale_credito, 2),
            "saldo_netto": round(totale_credito - totale_debito, 2),
            "cedolini_non_pagati": sum(r["non_pagati"] for r in riepilogo),
        }
    }
