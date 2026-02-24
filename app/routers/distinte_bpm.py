"""
Importatore Distinte Stipendi BPM

Questo modulo importa le distinte stipendi esportate dalla banca BPM
e le riconcilia automaticamente con le buste paga esistenti.

Formato CSV atteso (separatore ;):
- Data spedizione
- Azienda  
- ABI
- Rapporto
- N. disp.
- Tipo disp.
- Stato
- Sottostato
- Importo
- Divisa
- Data esecuzione
- IBAN
- Beneficiario
- Causale
"""

from fastapi import APIRouter, UploadFile, File, HTTPException
from typing import Optional
import csv
import io
import re
import logging
from datetime import datetime, timezone
import os

logger = logging.getLogger(__name__)
router = APIRouter()

# Database connection - usa il singleton già configurato
from app.database import Database

def get_db():
    return Database.get_db()


def normalize_name(name: str) -> str:
    """Normalizza il nome per il confronto"""
    if not name:
        return ""
    # Rimuovi spazi extra, converti in maiuscolo
    name = ' '.join(name.upper().split())
    return name


def match_names(name1: str, name2: str) -> bool:
    """
    Verifica se due nomi corrispondono.
    Gestisce variazioni come "CERALDI VALERIO" vs "Ceraldi Valerio"
    e anche ordine invertito "VALERIO CERALDI" vs "CERALDI VALERIO"
    """
    n1 = normalize_name(name1)
    n2 = normalize_name(name2)
    
    if not n1 or not n2:
        return False
    
    # Confronto diretto
    if n1 == n2:
        return True
    
    # Confronto con ordine invertito
    parts1 = n1.split()
    parts2 = n2.split()
    
    if len(parts1) >= 2 and len(parts2) >= 2:
        # Prova combinazioni
        if f"{parts1[1]} {parts1[0]}" == n2:
            return True
        if f"{parts2[1]} {parts2[0]}" == n1:
            return True
    
    # Confronto fuzzy: tutti i token di un nome sono contenuti nell'altro
    if all(p in n2 for p in parts1) or all(p in n1 for p in parts2):
        return True
    
    return False


def parse_date_it(date_str: str) -> Optional[str]:
    """Converte data italiana DD/MM/YYYY in ISO YYYY-MM-DD"""
    if not date_str:
        return None
    try:
        parts = date_str.strip().split('/')
        if len(parts) == 3:
            return f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
    except:
        pass
    return None


def parse_importo(value: str) -> float:
    """Converte importo stringa in float"""
    if not value:
        return 0.0
    try:
        # Rimuovi spazi e caratteri non numerici tranne punto e virgola
        clean = value.strip().replace(' ', '').replace('€', '')
        # Gestisce formato italiano con virgola decimale
        if ',' in clean and '.' in clean:
            clean = clean.replace('.', '').replace(',', '.')
        elif ',' in clean:
            clean = clean.replace(',', '.')
        return float(clean)
    except:
        return 0.0


@router.post("/import-distinte-bpm")
async def import_distinte_bpm(
    file: UploadFile = File(...),
    solo_anteprima: bool = False
):
    """
    Importa file CSV distinte stipendi formato BPM e riconcilia con buste paga.
    
    Il file deve avere separatore ; e le colonne:
    Beneficiario, Importo, Data esecuzione, Causale, IBAN
    
    Il sistema:
    1. Legge tutte le righe
    2. Per ogni riga, cerca una busta paga corrispondente per nome e importo
    3. Se trova match, aggiorna stato_pagamento = "PAGATO"
    """
    
    if not file.filename.lower().endswith('.csv'):
        raise HTTPException(status_code=400, detail="Il file deve essere un CSV")
    
    db = get_db()
    
    try:
        content = await file.read()
        # Prova decodifica
        try:
            text = content.decode('utf-8')
        except:
            text = content.decode('latin-1')
        
        # Rileva separatore (punto e virgola o virgola)
        first_line = text.split('\n')[0]
        separator = ';' if ';' in first_line else ','
        
        # Parse CSV
        reader = csv.DictReader(io.StringIO(text), delimiter=separator)
        
        righe = []
        for row in reader:
            # Estrai campi (nomi colonne possono variare)
            beneficiario = row.get('Beneficiario', row.get('beneficiario', ''))
            importo_str = row.get('Importo', row.get('importo', '0'))
            data_esec = row.get('Data esecuzione', row.get('data_esecuzione', ''))
            causale = row.get('Causale', row.get('causale', ''))
            iban = row.get('IBAN', row.get('iban', ''))
            stato = row.get('Stato', row.get('stato', ''))
            
            importo = parse_importo(importo_str)
            data_iso = parse_date_it(data_esec)
            
            # Skip righe vuote o senza beneficiario
            if not beneficiario or importo == 0:
                continue
            
            # Determina se è uno stipendio (non acconto)
            causale_lower = causale.lower()
            is_acconto = 'acc' in causale_lower or 'acconto' in causale_lower
            
            righe.append({
                'beneficiario': beneficiario,
                'importo': importo,
                'data_esecuzione': data_iso,
                'causale': causale,
                'iban': iban,
                'stato_banca': stato,
                'is_acconto': is_acconto
            })
        
        if not righe:
            return {
                "success": False,
                "message": "Nessuna riga valida trovata nel file CSV"
            }
        
        # Carica tutte le buste paga DA_PAGARE
        buste_da_pagare = []
        async for b in db.buste_paga.find({"stato_pagamento": "DA_PAGARE"}):
            buste_da_pagare.append(b)
        
        # Risultati riconciliazione
        riconciliati = []
        non_trovati = []
        acconti_trovati = []
        
        for riga in righe:
            # Salta acconti per ora (li gestiamo separatamente)
            if riga['is_acconto']:
                acconti_trovati.append(riga)
                continue
            
            # Cerca busta paga corrispondente
            match_found = False
            for busta in buste_da_pagare:
                nome_busta = busta.get('dipendente_nome', '')
                netto_busta = busta.get('netto_mese', 0)
                
                # Match per nome
                if match_names(riga['beneficiario'], nome_busta):
                    # Verifica importo (con tolleranza 5€)
                    if abs(riga['importo'] - netto_busta) <= 5:
                        match_found = True
                        riconciliati.append({
                            'beneficiario': riga['beneficiario'],
                            'importo_distinta': riga['importo'],
                            'netto_busta': netto_busta,
                            'busta_id': str(busta.get('_id')),
                            'periodo': busta.get('periodo'),
                            'data_pagamento': riga['data_esecuzione']
                        })
                        
                        # Aggiorna busta paga (se non anteprima)
                        if not solo_anteprima:
                            await db.buste_paga.update_one(
                                {"_id": busta['_id']},
                                {
                                    "$set": {
                                        "stato_pagamento": "PAGATO",
                                        "data_pagamento": riga['data_esecuzione'],
                                        "riconciliato_da": "distinte_bpm",
                                        "riconciliato_at": datetime.now(timezone.utc).isoformat()
                                    }
                                }
                            )
                        
                        # Rimuovi dalla lista per non abbinare due volte
                        buste_da_pagare.remove(busta)
                        break
            
            if not match_found:
                non_trovati.append({
                    'beneficiario': riga['beneficiario'],
                    'importo': riga['importo'],
                    'data': riga['data_esecuzione'],
                    'causale': riga['causale']
                })
        
        # Prepara risposta
        totale_righe = len(righe)
        totale_riconciliati = len(riconciliati)
        totale_acconti = len(acconti_trovati)
        totale_non_trovati = len(non_trovati)
        
        return {
            "success": True,
            "anteprima": solo_anteprima,
            "message": f"{'Anteprima' if solo_anteprima else 'Importazione'}: {totale_riconciliati} pagamenti riconciliati su {totale_righe} righe",
            "stats": {
                "totale_righe": totale_righe,
                "riconciliati": totale_riconciliati,
                "acconti": totale_acconti,
                "non_trovati": totale_non_trovati
            },
            "riconciliati": riconciliati[:20],  # Max 20 per brevità
            "non_trovati": non_trovati[:20],
            "acconti": acconti_trovati[:10]
        }
        
    except Exception as e:
        logger.error(f"Errore import distinte BPM: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/riconcilia-pagamento-manuale")
async def riconcilia_pagamento_manuale(
    dipendente_nome: str,
    importo: float,
    data_pagamento: str
):
    """
    Riconcilia manualmente un pagamento con una busta paga.
    Utile quando il match automatico fallisce.
    """
    db = get_db()
    
    # Cerca busta paga per nome (fuzzy)
    busta = None
    async for b in db.buste_paga.find({"stato_pagamento": "DA_PAGARE"}):
        if match_names(dipendente_nome, b.get('dipendente_nome', '')):
            busta = b
            break
    
    if not busta:
        raise HTTPException(status_code=404, detail=f"Busta paga non trovata per {dipendente_nome}")
    
    # Aggiorna
    await db.buste_paga.update_one(
        {"_id": busta['_id']},
        {
            "$set": {
                "stato_pagamento": "PAGATO",
                "data_pagamento": data_pagamento,
                "importo_pagato": importo,
                "riconciliato_da": "manuale",
                "riconciliato_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    return {
        "success": True,
        "message": f"Pagamento riconciliato per {busta.get('dipendente_nome')}",
        "busta_id": str(busta['_id'])
    }
