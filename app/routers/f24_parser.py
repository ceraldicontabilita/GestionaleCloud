"""
Parser PDF per Modello F24
==========================

Estrae i dati dal Modello F24 (Agenzia delle Entrate):
- Dati contribuente
- Sezione ERARIO (tributi, ritenute, crediti)
- Sezione INPS (contributi previdenziali)
- Sezione REGIONI (addizionali regionali)
- Sezione IMU/TASI (tributi locali)
- Sezione INAIL (premi assicurativi)
- Totale da pagare

Workflow completo: parsing → f24_pagamenti → tributi_pagati → distinta_f24 → scadenza → riconciliazione bancaria
"""

import re
import uuid
import pdfplumber
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
from fastapi import APIRouter, HTTPException, UploadFile, File
import tempfile
import os
import logging

from app.database import Database

router = APIRouter(tags=["F24 Parser"])
logger = logging.getLogger(__name__)


def parse_euro_amount(text: str) -> float:
    """Converte un importo testuale in float - gestisce formato F24 con virgola e spazi"""
    if not text:
        return 0.0
    # Rimuovi simboli e spazi extra
    cleaned = re.sub(r'[€\s]', '', str(text))
    # Gestisci formato F24: "1.307, 25" o "1.307,25" o "1307,25"
    # Prima rimuovi i punti delle migliaia
    cleaned = cleaned.replace('.', '')
    # Poi sostituisci la virgola con punto per i decimali
    cleaned = cleaned.replace(',', '.')
    # Rimuovi spazi residui
    cleaned = cleaned.replace(' ', '')
    try:
        return float(cleaned)
    except:
        return 0.0


def parse_f24_pdf(pdf_path: str) -> Dict:
    """
    Parsa un PDF del Modello F24 e estrae tutti i dati.
    """
    result = {
        "tipo_documento": "F24",
        "contribuente": {},
        "domicilio_fiscale": {},
        "scadenza": None,
        "sezione_erario": {
            "righe": [],
            "totale_debito": 0.0,
            "totale_credito": 0.0,
            "saldo": 0.0
        },
        "sezione_inps": {
            "righe": [],
            "totale": 0.0
        },
        "sezione_regioni": {
            "righe": [],
            "totale_debito": 0.0,
            "totale_credito": 0.0
        },
        "sezione_imu": {
            "righe": [],
            "totale": 0.0
        },
        "sezione_inail": {
            "righe": [],
            "totale": 0.0
        },
        "totale_da_pagare": 0.0,
        "pagamento": {}
    }
    
    all_text = ""
    
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                all_text += text + "\n"
    
    # --- CONTRIBUENTE ---
    # Codice fiscale - pattern specifico per F24
    # "0 4 5 2 3 8 3 1 2 1 4" (con spazi) o "04523831214" (senza)
    cf_match = re.search(r'(\d[\s\d]{10,20}\d)', all_text)
    if cf_match:
        cf_raw = cf_match.group(1).replace(' ', '')
        if len(cf_raw) == 11 or len(cf_raw) == 16:
            result["contribuente"]["codice_fiscale"] = cf_raw
    
    # Ragione sociale - cerca dopo il CF
    rs_match = re.search(r'CERALDI\s+GROUP\s+S\.?R\.?L\.?', all_text)
    if rs_match:
        result["contribuente"]["ragione_sociale"] = "CERALDI GROUP S.R.L."
    else:
        # Pattern generico per società
        rs_match2 = re.search(r'([A-Z][A-Z\s]+(?:S\.?R\.?L\.?|S\.?P\.?A\.?|S\.?A\.?S\.?|S\.?N\.?C\.?))', all_text)
        if rs_match2:
            nome = rs_match2.group(1).strip()
            if "BANCO BPM" not in nome:  # Escludi la banca
                result["contribuente"]["ragione_sociale"] = nome
    
    # --- DOMICILIO FISCALE ---
    # Pattern specifico: "NAPOLI N A PIAZZA NAZIONALE 46"
    dom_match = re.search(r'([A-Z]+)\s+([A-Z])\s+([A-Z])\s+((?:PIAZZA|VIA|CORSO|VIALE)[A-Z\s]+\d+)', all_text)
    if dom_match:
        result["domicilio_fiscale"]["comune"] = dom_match.group(1)
        result["domicilio_fiscale"]["provincia"] = dom_match.group(2) + dom_match.group(3)
        result["domicilio_fiscale"]["indirizzo"] = dom_match.group(4).strip()
    else:
        # Pattern alternativo: "comune NAPOLI prov. NA"
        comune_match = re.search(r'comune\s+([A-Z]+)\s+prov\.?\s*([A-Z]{2})', all_text, re.IGNORECASE)
        if comune_match:
            result["domicilio_fiscale"]["comune"] = comune_match.group(1)
            result["domicilio_fiscale"]["provincia"] = comune_match.group(2)
        
        via_match = re.search(r'via\s+(.+?)\s+cap\s+(\d{5})', all_text, re.IGNORECASE)
        if via_match:
            result["domicilio_fiscale"]["indirizzo"] = via_match.group(1).strip()
            result["domicilio_fiscale"]["cap"] = via_match.group(2)
    
    # --- SCADENZA ---
    scad_match = re.search(r'Scadenza\s+(\d{2}[-/]\d{4})', all_text)
    if scad_match:
        result["scadenza"] = scad_match.group(1)
    
    # --- SEZIONE ERARIO ---
    # Pattern: codice tributo (4 cifre) + rateazione + anno + importi
    # Esempio: "1001 0101 2026 1.307,25"
    erario_pattern = r'(\d{4})\s+(\d{4})?\s*(\d{4})\s+([\d.,]+)?\s*([\d.,]+)?'
    
    # Cerca la sezione ERARIO
    erario_section = re.search(r'SEZIONE\s*ERARIO(.*?)(?:SEZIONE|TOTALE\s*[A-Z])', all_text, re.DOTALL | re.IGNORECASE)
    if erario_section:
        erario_text = erario_section.group(1)
        
        # Pattern più specifico per le righe tributi
        righe_pattern = r'(\d{4})\s+(?:(\d{4})\s+)?(\d{4})\s+([\d.,]*)\s*([\d.,]*)'
        for match in re.finditer(righe_pattern, erario_text):
            codice_tributo = match.group(1)
            rateazione = match.group(2) or ""
            anno = match.group(3)
            debito = parse_euro_amount(match.group(4)) if match.group(4) else 0.0
            credito = parse_euro_amount(match.group(5)) if match.group(5) else 0.0
            
            # Ignora righe con codici non validi
            if int(codice_tributo) > 0:
                result["sezione_erario"]["righe"].append({
                    "codice_tributo": codice_tributo,
                    "rateazione": rateazione,
                    "anno_riferimento": anno,
                    "importo_debito": debito,
                    "importo_credito": credito
                })
                result["sezione_erario"]["totale_debito"] += debito
                result["sezione_erario"]["totale_credito"] += credito
    
    result["sezione_erario"]["saldo"] = result["sezione_erario"]["totale_debito"] - result["sezione_erario"]["totale_credito"]
    
    # --- SEZIONE INPS ---
    # Pattern dal testo reale: "5100 DM10 5124776507 01 2026 6.227, 00"
    inps_pattern = r'(\d{4})\s+DM10\s+(\d{10})\s+(\d{2})\s+(\d{4})\s+([\d.,]+)'
    for match in re.finditer(inps_pattern, all_text):
        codice_sede = match.group(1)
        matricola = match.group(2)
        mese = match.group(3)
        anno = match.group(4)
        importo = parse_euro_amount(match.group(5))
        
        result["sezione_inps"]["righe"].append({
            "codice_sede": codice_sede,
            "causale": "DM10",
            "matricola": matricola,
            "periodo_da": f"{mese}/{anno}",
            "periodo_a": f"{mese}/{anno}",
            "importo": importo
        })
        result["sezione_inps"]["totale"] += importo
    
    # --- SEZIONE REGIONI ---
    # Pattern dal testo reale: "0 5 3802 0001 2025 220, 02"
    # Il codice regione può avere spazi: "0 5" = "05"
    regioni_pattern = r'(\d)\s+(\d)\s+(\d{4})\s+(\d{4})\s+(\d{4})\s+([\d.,]+)'
    for match in re.finditer(regioni_pattern, all_text):
        codice_regione = match.group(1) + match.group(2)
        codice_tributo = match.group(3)
        rateazione = match.group(4)
        anno = match.group(5)
        debito = parse_euro_amount(match.group(6))
        
        # Filtra solo codici tributo validi per regioni (38xx)
        if codice_tributo.startswith('38'):
            result["sezione_regioni"]["righe"].append({
                "codice_regione": codice_regione,
                "codice_tributo": codice_tributo,
                "anno_riferimento": anno,
                "importo_debito": debito,
                "importo_credito": 0.0
            })
            result["sezione_regioni"]["totale_debito"] += debito
    
    # --- SEZIONE IMU ---
    # Pattern dal testo reale: "F 8 3 9 3848 0001 2025 66, 44"
    # Codice ente con spazi: "F 8 3 9" = "F839"
    imu_pattern = r'([A-Z])\s+(\d)\s+(\d)\s+(\d)\s+(\d{4})\s+(\d{4})\s+(\d{4})\s+([\d.,]+)'
    for match in re.finditer(imu_pattern, all_text):
        codice_ente = match.group(1) + match.group(2) + match.group(3) + match.group(4)
        codice_tributo = match.group(5)
        rateazione = match.group(6)
        anno = match.group(7)
        importo = parse_euro_amount(match.group(8))
        
        result["sezione_imu"]["righe"].append({
            "codice_ente": codice_ente,
            "codice_tributo": codice_tributo,
            "anno_riferimento": anno,
            "importo": importo
        })
        result["sezione_imu"]["totale"] += importo
    
    # --- SEZIONE INAIL ---
    # Pattern dal testo reale: "33400 13882560 91 902026 P 645, 61"
    inail_pattern = r'(\d{5})\s+(\d{8})\s+(\d{2})\s+(\d{2})(\d{4})\s+P\s+([\d.,]+)'
    for match in re.finditer(inail_pattern, all_text):
        codice_sede = match.group(1)
        codice_ditta = match.group(2)
        cc = match.group(3)
        mese = match.group(4)
        anno = match.group(5)
        importo = parse_euro_amount(match.group(6))
        
        result["sezione_inail"]["righe"].append({
            "codice_sede": codice_sede,
            "codice_ditta": codice_ditta,
            "cc": cc,
            "periodo": f"{mese}/{anno}",
            "importo": importo
        })
        result["sezione_inail"]["totale"] += importo
    
    # --- TOTALE DA PAGARE ---
    # Pattern dal testo reale: "FIRMA PANE GIUSEPPINA 7.465, 55"
    totale_match = re.search(r'FIRMA\s+[A-Z]+\s+[A-Z]+\s+([\d.,]+)', all_text)
    if totale_match:
        result["totale_da_pagare"] = parse_euro_amount(totale_match.group(1))
    else:
        # Pattern alternativo: "SALDO FINALE (G-H+I-L+Z) 7.465,55"
        totale_match2 = re.search(r'SALDO\s*FINALE.*?([\d.,]+)', all_text)
        if totale_match2:
            result["totale_da_pagare"] = parse_euro_amount(totale_match2.group(1))
        else:
            # Calcola dal totale delle sezioni
            result["totale_da_pagare"] = (
                result["sezione_erario"]["saldo"] +
                result["sezione_inps"]["totale"] +
                result["sezione_regioni"]["totale_debito"] - result["sezione_regioni"]["totale_credito"] +
                result["sezione_imu"]["totale"] +
                result["sezione_inail"]["totale"]
            )
    
    # --- PAGAMENTO ---
    # IBAN dal testo reale: "05034 03406" poi "I T" -> IT + ABI + CAB
    # Cerco pattern IBAN
    iban_match = re.search(r'I\s*T\s*(\d[\s\d]+)', all_text)
    if iban_match:
        iban_digits = iban_match.group(1).replace(' ', '')
        if len(iban_digits) >= 23:
            result["pagamento"]["iban"] = "IT" + iban_digits[:25]
    
    # Se non trovato, prova pattern standard
    if not result["pagamento"].get("iban"):
        iban_match2 = re.search(r'(IT\d{2}[A-Z0-9]{23})', all_text.replace(' ', ''))
        if iban_match2:
            result["pagamento"]["iban"] = iban_match2.group(1)
    
    # Banca
    banca_match = re.search(r'(BANCO\s*BPM\s*S\.?P\.?A\.?)', all_text)
    if banca_match:
        result["pagamento"]["banca"] = "BANCO BPM S.P.A."
    
    # Filiale
    filiale_match = re.search(r'(NAPOLI\s*-\s*[A-Z\s]+)', all_text)
    if filiale_match:
        result["pagamento"]["filiale"] = filiale_match.group(1).strip()
    
    # Scadenza - "Scadenza 16/02/2026"
    scad_match = re.search(r'Scadenza\s+(\d{2}/\d{2}/\d{4})', all_text)
    if scad_match:
        result["scadenza"] = scad_match.group(1)
    else:
        scad_match2 = re.search(r'(\d{2})/(\d{4})', all_text)
        if scad_match2:
            result["scadenza"] = f"{scad_match2.group(1)}/{scad_match2.group(2)}"
    
    return result


# ============== API ENDPOINTS ==============

@router.post("/parse-f24", summary="Parsa Modello F24")
async def parse_f24_endpoint(file: UploadFile = File(...)):
    """
    Carica e parsa un PDF del Modello F24.
    Estrae tutte le sezioni tributarie e il totale da pagare.
    """
    try:
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Il file deve essere un PDF")
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name
        
        try:
            result = parse_f24_pdf(tmp_path)
            
            return {
                "success": True,
                "message": f"F24 parsato con successo. Totale da pagare: €{result['totale_da_pagare']:,.2f}",
                "data": result
            }
        finally:
            os.unlink(tmp_path)
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore parsing F24: {e}")
        raise HTTPException(status_code=500, detail=f"Errore parsing: {str(e)}")




# ============== DESCRIZIONE TRIBUTI F24 ==============
DESCRIZIONE_TRIBUTI = {
    # ERARIO
    "1001": "IRPEF - Saldo",
    "1002": "IRPEF - Primo acconto",
    "1004": "IRPEF - Ritenute su redditi lavoro dipendente",
    "1012": "IRPEF - Secondo acconto",
    "1301": "IRES - Saldo",
    "1601": "IVA - Saldo annuale",
    "1627": "IVA - Versamento mensile/trimestrale",
    "3801": "Addizionale regionale IRPEF",
    "3802": "Addizionale regionale IRPEF - trattenute",
    "3812": "Addizionale comunale IRPEF",
    "3813": "Addizionale comunale IRPEF - trattenute",
    # INPS
    "5100": "INPS - Contributi DM10",
    "5101": "INPS - Contributi F24 EP",
    # INAIL
    "INAIL": "INAIL - Premio assicurativo",
}


def get_descrizione_tributo(codice: str, sezione: str) -> str:
    """Ritorna la descrizione di un tributo dato il codice."""
    return DESCRIZIONE_TRIBUTI.get(codice, f"Tributo {codice} - Sezione {sezione}")


async def riconcilia_f24_con_banca(db, f24_id: str, totale: float, scadenza_str: str) -> Optional[str]:
    """
    Cerca in estratto_conto_movimenti e prima_nota_banca un movimento per l'F24.
    """
    from app.services.paghe_riconciliazione import cerca_in_estratto_conto
    try:
        keywords = ["F24", "ERARIO", "INPS", "AGENZIA", "ENTRATE", "TRIBUT"]
        result = await cerca_in_estratto_conto(
            db, totale, scadenza_str,
            giorni_tolleranza=7,
            keywords_descrizione=keywords
        )
        if result:
            return result[0]
        return None
    except Exception as e:
        logger.warning(f"Errore riconciliazione bancaria F24 {f24_id}: {e}")
        return None


@router.post("/import-f24", summary="Importa F24 nel database (workflow completo)")
async def import_f24(
    file: UploadFile = File(...),
    aggiorna_esistente: bool = True
):
    """
    Parsa e importa il Modello F24 nel database - WORKFLOW COMPLETO.
    
    Esegue:
    1. Salvataggio F24 completo (collection 'f24_pagamenti') con stato 'DA_PAGARE'
    2. Storico tributi per codice (collection 'tributi_pagati') - ricercabile
    3. Distinta F24 aggregata (collection 'distinte_f24')
    4. Scadenza di pagamento (collection 'scadenze')
    5. Riconciliazione bancaria automatica (prima_nota_banca)
    """
    try:
        db = Database.get_db()
        
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Il file deve essere un PDF")
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name
        
        try:
            try:
                parsed = parse_f24_pdf(tmp_path)
            except Exception as pdf_err:
                raise HTTPException(status_code=400, detail=f"Errore parsing PDF - file non valido o corrotto: {str(pdf_err)}")
            
            cf = parsed["contribuente"].get("codice_fiscale", "")
            scadenza = parsed.get("scadenza", "")
            totale = parsed["totale_da_pagare"]
            f24_id = f"f24_{cf}_{scadenza}".replace("/", "-").replace(" ", "")
            
            # ============================================================
            # STEP 1: SALVATAGGIO F24 PRINCIPALE (f24_pagamenti)
            # ============================================================
            documento = {
                "f24_id": f24_id,
                **parsed,
                "imported_at": datetime.now(timezone.utc).isoformat(),
                "source_file": file.filename,
                "stato": "DA_PAGARE",
                "data_pagamento": None,
                "movimento_bancario_id": None,
                "riconciliato": False
            }
            # Rimuovi _id se presente
            documento.pop("_id", None)
            
            if aggiorna_esistente:
                result = await db.f24_pagamenti.update_one(
                    {"f24_id": f24_id},
                    {"$set": documento},
                    upsert=True
                )
                action = "aggiornato" if result.matched_count > 0 else "importato"
            else:
                existing = await db.f24_pagamenti.find_one({"f24_id": f24_id})
                if existing:
                    raise HTTPException(status_code=400, detail=f"F24 {f24_id} già esistente")
                await db.f24_pagamenti.insert_one(documento.copy())
                action = "importato"
            
            # ============================================================
            # STEP 2: STORICO TRIBUTI PAGATI (tributi_pagati)
            # ============================================================
            tributi_inseriti = 0
            
            # Converti scadenza in data ISO per tributi
            data_scadenza_iso = None
            try:
                if scadenza:
                    if "/" in scadenza and len(scadenza) > 5:
                        # Formato DD/MM/YYYY
                        data_scadenza_iso = datetime.strptime(scadenza, "%d/%m/%Y").strftime("%Y-%m-%d")
                    elif "/" in scadenza:
                        # Formato MM/YYYY → 16/MM/YYYY
                        mm, yyyy = scadenza.split("/")
                        data_scadenza_iso = f"{yyyy}-{mm.zfill(2)}-16"
            except (ValueError, TypeError):
                pass
            
            def salva_tributi(righe: list, sezione: str):
                nonlocal tributi_inseriti
                for riga in righe:
                    codice = riga.get("codice_tributo") or riga.get("codice_sede", "")
                    importo_deb = float(riga.get("importo_debito") or riga.get("importo") or 0)
                    importo_cred = float(riga.get("importo_credito") or 0)
                    importo_netto = importo_deb - importo_cred
                    anno_rif = riga.get("anno_riferimento") or riga.get("periodo_da", "")
                    
                    if importo_netto <= 0 and importo_deb <= 0:
                        continue
                    
                    tributo_id = f"trib_{f24_id}_{sezione}_{codice}"
                    tributo_doc = {
                        "tributo_id": tributo_id,
                        "f24_id": f24_id,
                        "codice_tributo": str(codice),
                        "descrizione_tributo": get_descrizione_tributo(str(codice), sezione),
                        "sezione": sezione,
                        "anno_riferimento": str(anno_rif),
                        "periodo_riferimento": scadenza,
                        "importo_debito": importo_deb,
                        "importo_credito": importo_cred,
                        "importo_netto": importo_netto,
                        "data_scadenza": data_scadenza_iso,
                        "data_pagamento": None,
                        "stato": "DA_PAGARE",
                        "contribuente_cf": cf,
                        "contribuente_rs": parsed["contribuente"].get("ragione_sociale", ""),
                        "note": "",
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }
                    
                    return tributo_doc
                return None
            
            # Processa ogni sezione
            sezioni_dati = [
                (parsed["sezione_erario"]["righe"], "ERARIO"),
                (parsed["sezione_inps"]["righe"], "INPS"),
                (parsed["sezione_regioni"]["righe"], "REGIONI"),
                (parsed["sezione_imu"]["righe"], "IMU"),
                (parsed["sezione_inail"]["righe"], "INAIL"),
            ]
            
            for righe, sezione_nome in sezioni_dati:
                for riga in righe:
                    codice = riga.get("codice_tributo") or riga.get("codice_sede", "")
                    importo_deb = float(riga.get("importo_debito") or riga.get("importo") or 0)
                    importo_cred = float(riga.get("importo_credito") or 0)
                    importo_netto = importo_deb - importo_cred
                    anno_rif = riga.get("anno_riferimento") or riga.get("periodo_da", "")
                    
                    if importo_netto <= 0 and importo_deb <= 0:
                        continue
                    
                    tributo_id = f"trib_{f24_id}_{sezione_nome}_{codice}"
                    tributo_doc = {
                        "tributo_id": tributo_id,
                        "f24_id": f24_id,
                        "codice_tributo": str(codice),
                        "descrizione_tributo": get_descrizione_tributo(str(codice), sezione_nome),
                        "sezione": sezione_nome,
                        "anno_riferimento": str(anno_rif),
                        "periodo_riferimento": scadenza,
                        "importo_debito": importo_deb,
                        "importo_credito": importo_cred,
                        "importo_netto": importo_netto,
                        "data_scadenza": data_scadenza_iso,
                        "data_pagamento": None,
                        "stato": "DA_PAGARE",
                        "contribuente_cf": cf,
                        "contribuente_rs": parsed["contribuente"].get("ragione_sociale", ""),
                        "note": "",
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }
                    
                    await db.tributi_pagati.update_one(
                        {"tributo_id": tributo_id},
                        {"$set": tributo_doc},
                        upsert=True
                    )
                    tributi_inseriti += 1
            
            # ============================================================
            # STEP 3: DISTINTA F24 AGGREGATA (distinte_f24)
            # ============================================================
            distinta_id = f"dist_{f24_id}"
            distinta_doc = {
                "distinta_id": distinta_id,
                "f24_ids": [f24_id],
                "data_creazione": datetime.now(timezone.utc).isoformat(),
                "scadenza": scadenza,
                "data_scadenza": data_scadenza_iso,
                "contribuente_cf": cf,
                "contribuente_rs": parsed["contribuente"].get("ragione_sociale", ""),
                "riepilogo": {
                    "totale_erario": parsed["sezione_erario"]["totale_debito"] - parsed["sezione_erario"]["totale_credito"],
                    "totale_inps": parsed["sezione_inps"]["totale"],
                    "totale_regioni": parsed["sezione_regioni"]["totale_debito"],
                    "totale_imu": parsed["sezione_imu"]["totale"],
                    "totale_inail": parsed["sezione_inail"]["totale"],
                    "totale_generale": totale
                },
                "banca_pagamento": parsed["pagamento"].get("banca", ""),
                "iban": parsed["pagamento"].get("iban", ""),
                "stato": "DA_PAGARE",
                "data_pagamento": None,
                "movimento_bancario_id": None,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            
            await db.distinte_f24.update_one(
                {"distinta_id": distinta_id},
                {"$set": distinta_doc},
                upsert=True
            )
            
            # ============================================================
            # STEP 4: SCADENZA F24 (scadenze)
            # ============================================================
            scadenza_creata = False
            if scadenza:
                try:
                    scad_doc = {
                        "titolo": f"F24 {scadenza} - €{totale:,.2f}",
                        "tipo": "F24",
                        "data_scadenza": data_scadenza_iso,
                        "importo": totale,
                        "descrizione": f"Pagamento F24 - {parsed['contribuente'].get('ragione_sociale', cf)}",
                        "documento_id": f24_id,
                        "priorita": "ALTA",
                        "completata": False,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }
                    
                    await db.scadenze.update_one(
                        {"documento_id": f24_id},
                        {"$set": scad_doc},
                        upsert=True
                    )
                    scadenza_creata = True
                except Exception as e:
                    logger.warning(f"Errore creazione scadenza F24: {e}")
            
            # ============================================================
            # STEP 5: RICONCILIAZIONE BANCARIA AUTOMATICA
            # ============================================================
            riconciliato = False
            mov_id = None
            
            if totale > 0 and data_scadenza_iso:
                mov_id = await riconcilia_f24_con_banca(db, f24_id, totale, data_scadenza_iso)
                if mov_id:
                    # Aggiorna f24 come PAGATO
                    await db.f24_pagamenti.update_one(
                        {"f24_id": f24_id},
                        {"$set": {
                            "stato": "PAGATO",
                            "data_pagamento": datetime.now(timezone.utc).isoformat(),
                            "movimento_bancario_id": mov_id,
                            "riconciliato": True
                        }}
                    )
                    # Aggiorna tutti i tributi come PAGATI
                    await db.tributi_pagati.update_many(
                        {"f24_id": f24_id},
                        {"$set": {
                            "stato": "PAGATO",
                            "data_pagamento": datetime.now(timezone.utc).isoformat()
                        }}
                    )
                    # Aggiorna distinta come PAGATA
                    await db.distinte_f24.update_one(
                        {"distinta_id": distinta_id},
                        {"$set": {
                            "stato": "PAGATO",
                            "data_pagamento": datetime.now(timezone.utc).isoformat(),
                            "movimento_bancario_id": mov_id
                        }}
                    )
                    # Marca scadenza come completata
                    await db.scadenze.update_one(
                        {"documento_id": f24_id},
                        {"$set": {"completata": True}}
                    )
                    # Marca movimento come riconciliato
                    await db.prima_nota_banca.update_one(
                        {"id": mov_id},
                        {"$set": {
                            "riconciliato_f24": True,
                            "documento_f24_id": f24_id
                        }}
                    )
                    riconciliato = True
            
            return {
                "success": True,
                "message": f"F24 {action} con successo" + (" - RICONCILIATO" if riconciliato else " - in attesa riconciliazione"),
                "data": {
                    "f24_id": f24_id,
                    "scadenza": scadenza,
                    "totale_da_pagare": totale,
                    "stato": "PAGATO" if riconciliato else "DA_PAGARE",
                    "tributi_salvati": tributi_inseriti,
                    "distinta_creata": True,
                    "scadenza_creata": scadenza_creata,
                    "riconciliato": riconciliato,
                    "movimento_bancario_id": mov_id,
                    "sezioni": {
                        "erario": len(parsed["sezione_erario"]["righe"]),
                        "inps": len(parsed["sezione_inps"]["righe"]),
                        "regioni": len(parsed["sezione_regioni"]["righe"]),
                        "imu": len(parsed["sezione_imu"]["righe"]),
                        "inail": len(parsed["sezione_inail"]["righe"])
                    }
                }
            }
        finally:
            os.unlink(tmp_path)
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore import F24: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/riconcilia-f24", summary="Riconcilia F24 con movimenti bancari")
async def riconcilia_f24(
    anno: Optional[int] = None
):
    """
    Riesegue la riconciliazione bancaria per tutti gli F24 DA_PAGARE.
    Normalmente avviene automaticamente al caricamento dell'estratto conto.
    """
    try:
        db = Database.get_db()
        from app.services.paghe_riconciliazione import riconcilia_tutti_f24
        result = await riconcilia_tutti_f24(db, anno=anno)
        return {
            "success": True,
            "message": f"Riconciliazione F24: {result['riconciliati']} pagati, {result['non_trovati']} da pagare",
            "data": result
        }
    except Exception as e:
        logger.error(f"Errore riconciliazione F24: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tributi-pagati", summary="Storico tributi versati")
async def get_tributi_pagati(
    anno: Optional[int] = None,
    codice_tributo: Optional[str] = None,
    sezione: Optional[str] = None,
    stato: Optional[str] = None
):
    """
    Ritorna lo storico dei tributi pagati, ricercabile per codice, anno, sezione e stato.
    """
    try:
        db = Database.get_db()
        
        query = {}
        if anno:
            query["anno_riferimento"] = {"$regex": str(anno)}
        if codice_tributo:
            query["codice_tributo"] = codice_tributo
        if sezione:
            query["sezione"] = sezione.upper()
        if stato:
            query["stato"] = stato.upper()
        
        tributi = await db.tributi_pagati.find(
            query, {"_id": 0}
        ).sort("data_scadenza", -1).to_list(length=1000)
        
        # Calcola totale
        totale = sum(t.get("importo_netto", 0) for t in tributi)
        
        return {
            "success": True,
            "data": tributi,
            "count": len(tributi),
            "totale": round(totale, 2)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/distinte-f24", summary="Lista distinte F24")
async def get_distinte_f24(
    anno: Optional[int] = None,
    stato: Optional[str] = None
):
    """Lista delle distinte F24 con riepilogo aggregato."""
    try:
        db = Database.get_db()
        
        query = {}
        if anno:
            query["scadenza"] = {"$regex": str(anno)}
        if stato:
            query["stato"] = stato.upper()
        
        distinte = await db.distinte_f24.find(
            query, {"_id": 0}
        ).sort("data_scadenza", -1).to_list(length=200)
        
        return {
            "success": True,
            "data": distinte,
            "count": len(distinte)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/f24/lista", summary="Lista F24 importati")
async def get_lista_f24(
    anno: Optional[int] = None,
    stato: Optional[str] = None
):
    """
    Restituisce la lista degli F24 importati nel database.
    """
    try:
        db = Database.get_db()
        
        query = {}
        if anno:
            query["scadenza"] = {"$regex": str(anno)}
        if stato:
            query["stato"] = stato
        
        f24_list = await db.f24_pagamenti.find(
            query,
            {"_id": 0, "f24_id": 1, "scadenza": 1, "totale_da_pagare": 1,
             "stato": 1, "contribuente": 1, "imported_at": 1, "riconciliato": 1}
        ).sort("scadenza", -1).to_list(length=100)
        
        return {
            "success": True,
            "data": f24_list,
            "count": len(f24_list)
        }
        
    except Exception as e:
        logger.error(f"Errore lista F24: {e}")
        raise HTTPException(status_code=500, detail=str(e))
