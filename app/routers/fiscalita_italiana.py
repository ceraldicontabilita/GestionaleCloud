"""
Fiscalità Italiana Completa per SRL
====================================

1. AGEVOLAZIONI E DETRAZIONI FISCALI SRL
   - Crediti d'imposta
   - Super/Iper ammortamento
   - Patent Box
   - ACE (Aiuto Crescita Economica)
   - Bonus investimenti
   - Credito R&D

2. CALENDARIO FISCALE COMPLETO
   - Scadenze IVA (liquidazioni, dichiarazione)
   - F24 (versamenti)
   - Dichiarazioni (Redditi, IRAP, 770)
   - IMU/TASI
   - Bilancio e assemblee
   - Tutti gli adempimenti societari

3. CHIUSURA/APERTURA ESERCIZIO
   - Epilogo conti
   - Determinazione utile/perdita
   - Riapertura conti

4. GESTIONE F24
   - Registrazione versamenti
   - Compensazioni
   - Ravvedimento operoso
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel, Field

from app.database import Database

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================
# AGEVOLAZIONI FISCALI SRL 2025
# ============================================

AGEVOLAZIONI_FISCALI_SRL = [
    # === CREDITI D'IMPOSTA ===
    {
        "id": "credito_ricerca_sviluppo",
        "nome": "Credito d'imposta Ricerca e Sviluppo",
        "categoria": "credito_imposta",
        "descrizione": "Credito per attività di R&S, innovazione tecnologica, design",
        "aliquota": 10,  # % sul costo
        "massimale": 5000000,
        "requisiti": [
            "Attività di ricerca fondamentale, industriale o sviluppo sperimentale",
            "Personale qualificato impiegato in R&S",
            "Documentazione tecnica e contabile"
        ],
        "normativa": "Art. 1, commi 198-209, L. 160/2019 - Legge di Bilancio 2020",
        "scadenza_fruizione": "Compensazione in 3 quote annuali",
        "codice_tributo_f24": "6938",
        "anno_validita": 2025,
        "attivo": True
    },
    {
        "id": "credito_innovazione_tecnologica",
        "nome": "Credito Innovazione Tecnologica",
        "categoria": "credito_imposta",
        "descrizione": "Per innovazione tecnologica finalizzata a prodotti/processi nuovi",
        "aliquota": 10,
        "massimale": 2000000,
        "requisiti": [
            "Progetti di innovazione tecnologica",
            "Obiettivi di transizione ecologica o digitale 4.0"
        ],
        "normativa": "Art. 1, commi 198-209, L. 160/2019",
        "codice_tributo_f24": "6939",
        "anno_validita": 2025,
        "attivo": True
    },
    {
        "id": "credito_formazione_40",
        "nome": "Credito Formazione 4.0",
        "categoria": "credito_imposta",
        "descrizione": "Per formazione del personale su tecnologie 4.0",
        "aliquota": 50,  # Piccole imprese
        "aliquota_medie": 40,
        "aliquota_grandi": 30,
        "massimale": 300000,
        "requisiti": [
            "Formazione su tecnologie Industry 4.0",
            "Accordo sindacale o contratto collettivo",
            "Certificazione delle competenze acquisite"
        ],
        "normativa": "Art. 1, commi 46-56, L. 205/2017",
        "codice_tributo_f24": "6897",
        "anno_validita": 2025,
        "attivo": True
    },
    {
        "id": "credito_investimenti_mezzogiorno",
        "nome": "Credito Investimenti Sud",
        "categoria": "credito_imposta",
        "descrizione": "Per investimenti in beni strumentali nel Mezzogiorno",
        "aliquota": 45,  # Piccole imprese
        "aliquota_medie": 35,
        "aliquota_grandi": 25,
        "regioni": ["Campania", "Puglia", "Basilicata", "Calabria", "Sicilia", "Sardegna", "Molise", "Abruzzo"],
        "requisiti": [
            "Investimenti in macchinari, impianti, attrezzature",
            "Struttura produttiva nel Mezzogiorno"
        ],
        "normativa": "Art. 1, commi 98-108, L. 208/2015",
        "codice_tributo_f24": "6869",
        "anno_validita": 2025,
        "attivo": True
    },
    {
        "id": "credito_beni_strumentali",
        "nome": "Credito Beni Strumentali 4.0",
        "categoria": "credito_imposta",
        "descrizione": "Ex Super/Iper ammortamento - beni materiali e immateriali 4.0",
        "aliquota_materiali_40": 20,  # Fino a 2,5M
        "aliquota_materiali_41": 10,  # Da 2,5M a 10M
        "aliquota_materiali_42": 5,   # Da 10M a 20M
        "aliquota_immateriali": 20,
        "massimale_materiali": 20000000,
        "massimale_immateriali": 1000000,
        "requisiti": [
            "Beni inclusi in Allegato A o B L. 232/2016",
            "Interconnessione al sistema aziendale",
            "Perizia tecnica per beni > €300.000"
        ],
        "normativa": "Art. 1, commi 1051-1063, L. 178/2020",
        "codice_tributo_f24": "6936",
        "anno_validita": 2025,
        "attivo": True
    },
    
    # === AGEVOLAZIONI IRES/IRAP ===
    {
        "id": "ace",
        "nome": "ACE - Aiuto alla Crescita Economica",
        "categoria": "deduzione_ires",
        "descrizione": "Deduzione dal reddito del rendimento nozionale del capitale proprio",
        "coefficiente_rendimento": 1.3,  # % 2025
        "requisiti": [
            "Incrementi di capitale proprio",
            "Utili non distribuiti",
            "Conferimenti in denaro"
        ],
        "normativa": "Art. 1, D.L. 201/2011",
        "anno_validita": 2025,
        "attivo": True
    },
    {
        "id": "patent_box",
        "nome": "Patent Box",
        "categoria": "deduzione_ires",
        "descrizione": "Esclusione dal reddito del 50% dei proventi da beni immateriali",
        "esclusione_percentuale": 110,  # Super deduzione 110%
        "beni_agevolabili": ["Software", "Brevetti", "Disegni e modelli", "Know-how"],
        "requisiti": [
            "Attività di R&S sui beni immateriali",
            "Documentazione idonea",
            "Opzione irrevocabile 5 anni"
        ],
        "normativa": "Art. 6, D.L. 146/2021",
        "anno_validita": 2025,
        "attivo": True
    },
    {
        "id": "deduzione_irap_personale",
        "nome": "Deduzione IRAP Costo Lavoro",
        "categoria": "deduzione_irap",
        "descrizione": "Deduzione integrale del costo del lavoro dipendente",
        "deduzione_percentuale": 100,
        "requisiti": ["Contratti di lavoro dipendente a tempo indeterminato"],
        "normativa": "Art. 11, D.Lgs. 446/1997",
        "anno_validita": 2025,
        "attivo": True
    },
    
    # === STARTUP E PMI INNOVATIVE ===
    {
        "id": "startup_innovative",
        "nome": "Agevolazioni Startup Innovative",
        "categoria": "startup",
        "descrizione": "Pacchetto agevolazioni per startup innovative",
        "benefici": [
            "Esonero diritti camerali e bolli",
            "Deroghe diritto societario",
            "Incentivi fiscali per investitori (30% detrazione IRPEF/deduzione IRES)",
            "Accesso semplificato al Fondo Garanzia PMI",
            "Credito d'imposta R&S maggiorato"
        ],
        "requisiti": [
            "Iscrizione sezione speciale Registro Imprese",
            "Costituita da meno di 5 anni",
            "Fatturato < €5M",
            "Oggetto sociale innovativo"
        ],
        "normativa": "D.L. 179/2012 e successive modifiche",
        "anno_validita": 2025,
        "attivo": True
    },
    {
        "id": "pmi_innovative",
        "nome": "Agevolazioni PMI Innovative",
        "categoria": "pmi",
        "descrizione": "Agevolazioni per PMI innovative",
        "benefici": [
            "Incentivi fiscali investitori",
            "Equity crowdfunding",
            "Accesso Fondo Garanzia",
            "Remunerazione in equity"
        ],
        "requisiti": [
            "PMI con bilancio certificato",
            "Requisiti di innovazione",
            "Iscrizione sezione speciale"
        ],
        "normativa": "D.L. 3/2015",
        "anno_validita": 2025,
        "attivo": True
    },
    
    # === CREDITI PER ENERGIA E AMBIENTE ===
    {
        "id": "credito_energia",
        "nome": "Credito Energia e Gas",
        "categoria": "credito_imposta",
        "descrizione": "Credito per imprese energivore e gasivore",
        "aliquota_energivore": 45,
        "aliquota_non_energivore": 35,
        "aliquota_gas": 45,
        "requisiti": [
            "Incremento costi energia >30% rispetto 2019",
            "Contatori di energia"
        ],
        "normativa": "D.L. 17/2022 e successive proroghe",
        "codice_tributo_f24": "6968",
        "anno_validita": 2025,
        "attivo": True
    },
    {
        "id": "credito_transizione_ecologica",
        "nome": "Credito Transizione 5.0",
        "categoria": "credito_imposta",
        "descrizione": "Per investimenti in transizione ecologica e digitale",
        "aliquota": 45,  # Max per piccole imprese
        "massimale": 50000000,
        "requisiti": [
            "Investimenti in beni 4.0",
            "Riduzione consumi energetici certificata",
            "Autoproduzione energia rinnovabile"
        ],
        "normativa": "D.L. 19/2024 - Piano Transizione 5.0",
        "anno_validita": 2025,
        "attivo": True
    },
    
    # === ZES E ZONE SPECIALI ===
    {
        "id": "zes_unica",
        "nome": "ZES Unica Mezzogiorno",
        "categoria": "credito_imposta",
        "descrizione": "Credito per investimenti nella ZES Unica",
        "aliquota": 60,  # Piccole imprese
        "aliquota_medie": 50,
        "aliquota_grandi": 40,
        "massimale": 100000000,
        "regioni": ["Abruzzo", "Basilicata", "Calabria", "Campania", "Molise", "Puglia", "Sardegna", "Sicilia"],
        "requisiti": [
            "Investimenti in immobili strumentali",
            "Macchinari e attrezzature",
            "Struttura produttiva nella ZES"
        ],
        "normativa": "D.L. 124/2023",
        "codice_tributo_f24": "7034",
        "anno_validita": 2025,
        "attivo": True
    }
]


# ============================================
# CALENDARIO FISCALE COMPLETO SRL
# ============================================

def genera_scadenze_anno(anno: int) -> List[Dict]:
    """Genera tutte le scadenze fiscali per l'anno"""
    
    scadenze = []
    
    # === IVA ===
    # Liquidazioni mensili (contribuenti con volume affari > €400.000)
    for mese in range(1, 13):
        giorno = 16
        mese_liquidazione = mese + 1 if mese < 12 else 1
        anno_liq = anno if mese < 12 else anno + 1
        
        scadenze.append({
            "id": f"iva_liq_{anno}_{mese:02d}",
            "tipo": "IVA",
            "descrizione": f"Liquidazione IVA {mese:02d}/{anno}",
            "data": f"{anno_liq}-{mese_liquidazione:02d}-{giorno:02d}",
            "periodicita": "mensile",
            "codice_tributo": "6001" if mese == 1 else f"60{mese:02d}",
            "note": "Versamento IVA mese precedente",
            "categoria": "versamento"
        })
    
    # Liquidazioni trimestrali
    scadenze_trim = [
        (f"{anno}-05-16", "1° trimestre", "6031"),
        (f"{anno}-08-20", "2° trimestre", "6032"),  # 20 agosto
        (f"{anno}-11-16", "3° trimestre", "6033"),
        (f"{anno+1}-02-16", "4° trimestre", "6034"),
    ]
    for data, periodo, codice in scadenze_trim:
        scadenze.append({
            "id": f"iva_trim_{codice}",
            "tipo": "IVA",
            "descrizione": f"Liquidazione IVA trimestrale {periodo} {anno}",
            "data": data,
            "periodicita": "trimestrale",
            "codice_tributo": codice,
            "categoria": "versamento"
        })
    
    # Acconto IVA
    scadenze.append({
        "id": f"iva_acconto_{anno}",
        "tipo": "IVA",
        "descrizione": f"Acconto IVA {anno}",
        "data": f"{anno}-12-27",
        "codice_tributo": "6013",
        "note": "88% dell'IVA versata ultimo mese/trimestre anno precedente",
        "categoria": "versamento"
    })
    
    # Dichiarazione IVA annuale
    scadenze.append({
        "id": f"dich_iva_{anno}",
        "tipo": "IVA",
        "descrizione": f"Dichiarazione IVA annuale {anno}",
        "data": f"{anno+1}-04-30",
        "note": "Termine presentazione dichiarazione IVA",
        "categoria": "dichiarazione"
    })
    
    # Comunicazione LIPE
    scadenze_lipe = [
        (f"{anno}-05-31", "1° trimestre"),
        (f"{anno}-09-30", "2° trimestre"),
        (f"{anno}-11-30", "3° trimestre"),
        (f"{anno+1}-02-28", "4° trimestre"),
    ]
    for data, periodo in scadenze_lipe:
        scadenze.append({
            "id": f"lipe_{anno}_{periodo[:1]}",
            "tipo": "LIPE",
            "descrizione": f"Comunicazione LIPE {periodo} {anno}",
            "data": data,
            "categoria": "comunicazione"
        })
    
    # === IMPOSTE DIRETTE ===
    # Saldo + acconto IRES/IRAP
    scadenze.append({
        "id": f"ires_saldo_{anno-1}",
        "tipo": "IRES",
        "descrizione": f"Saldo IRES {anno-1} + 1° acconto {anno}",
        "data": f"{anno}-06-30",
        "codice_tributo": "2003",
        "note": "Saldo anno precedente + 40% acconto anno corrente",
        "categoria": "versamento"
    })
    
    scadenze.append({
        "id": f"irap_saldo_{anno-1}",
        "tipo": "IRAP",
        "descrizione": f"Saldo IRAP {anno-1} + 1° acconto {anno}",
        "data": f"{anno}-06-30",
        "codice_tributo": "3800",
        "categoria": "versamento"
    })
    
    # Secondo acconto
    scadenze.append({
        "id": f"ires_acconto2_{anno}",
        "tipo": "IRES",
        "descrizione": f"2° acconto IRES {anno}",
        "data": f"{anno}-11-30",
        "codice_tributo": "2002",
        "note": "60% dell'acconto totale",
        "categoria": "versamento"
    })
    
    scadenze.append({
        "id": f"irap_acconto2_{anno}",
        "tipo": "IRAP",
        "descrizione": f"2° acconto IRAP {anno}",
        "data": f"{anno}-11-30",
        "codice_tributo": "3813",
        "categoria": "versamento"
    })
    
    # Dichiarazione Redditi SC
    scadenze.append({
        "id": f"redditi_sc_{anno-1}",
        "tipo": "REDDITI",
        "descrizione": f"Dichiarazione Redditi SC {anno-1}",
        "data": f"{anno}-10-31",
        "note": "Modello Redditi Società di Capitali",
        "categoria": "dichiarazione"
    })
    
    # === RITENUTE E 770 ===
    # Versamento ritenute mensili
    for mese in range(1, 13):
        scadenze.append({
            "id": f"ritenute_{anno}_{mese:02d}",
            "tipo": "RITENUTE",
            "descrizione": f"Versamento ritenute {mese:02d}/{anno}",
            "data": f"{anno}-{mese:02d}-16",
            "codice_tributo": "1040",  # Lavoro dipendente
            "note": "Ritenute su lavoro dipendente, autonomo, provvigioni",
            "categoria": "versamento"
        })
    
    # Modello 770
    scadenze.append({
        "id": f"mod_770_{anno-1}",
        "tipo": "770",
        "descrizione": f"Dichiarazione 770/{anno} (anno {anno-1})",
        "data": f"{anno}-10-31",
        "categoria": "dichiarazione"
    })
    
    # CU - Certificazione Unica
    scadenze.append({
        "id": f"cu_{anno-1}",
        "tipo": "CU",
        "descrizione": f"Certificazione Unica {anno} (redditi {anno-1})",
        "data": f"{anno}-03-16",
        "note": "Invio telematico all'Agenzia Entrate",
        "categoria": "dichiarazione"
    })
    
    scadenze.append({
        "id": f"cu_consegna_{anno-1}",
        "tipo": "CU",
        "descrizione": f"Consegna CU ai percipienti",
        "data": f"{anno}-03-16",
        "categoria": "adempimento"
    })
    
    # === IMU ===
    scadenze.append({
        "id": f"imu_acconto_{anno}",
        "tipo": "IMU",
        "descrizione": f"Acconto IMU {anno}",
        "data": f"{anno}-06-16",
        "codice_tributo": "3918",  # Fabbricati D
        "note": "50% dell'imposta annua",
        "categoria": "versamento"
    })
    
    scadenze.append({
        "id": f"imu_saldo_{anno}",
        "tipo": "IMU",
        "descrizione": f"Saldo IMU {anno}",
        "data": f"{anno}-12-16",
        "codice_tributo": "3918",
        "categoria": "versamento"
    })
    
    # === CONTRIBUTI INPS ===
    for mese in range(1, 13):
        scadenze.append({
            "id": f"inps_{anno}_{mese:02d}",
            "tipo": "INPS",
            "descrizione": f"Contributi INPS dipendenti {mese:02d}/{anno}",
            "data": f"{anno}-{mese:02d}-16",
            "note": "Contributi mese precedente",
            "categoria": "versamento"
        })
    
    # === BILANCIO E ASSEMBLEE ===
    scadenze.append({
        "id": f"bilancio_approv_{anno-1}",
        "tipo": "BILANCIO",
        "descrizione": f"Approvazione bilancio {anno-1}",
        "data": f"{anno}-04-30",
        "note": "Entro 120 giorni dalla chiusura esercizio (prorogabile a 180)",
        "categoria": "assemblea"
    })
    
    scadenze.append({
        "id": f"bilancio_deposito_{anno-1}",
        "tipo": "BILANCIO",
        "descrizione": f"Deposito bilancio {anno-1} al Registro Imprese",
        "data": f"{anno}-05-30",
        "note": "Entro 30 giorni dall'approvazione",
        "categoria": "adempimento"
    })
    
    # === INTRASTAT ===
    for mese in range(1, 13):
        scadenze.append({
            "id": f"intrastat_{anno}_{mese:02d}",
            "tipo": "INTRASTAT",
            "descrizione": f"Intrastat {mese:02d}/{anno}",
            "data": f"{anno}-{mese:02d}-25",
            "note": "Operazioni intracomunitarie mese precedente",
            "categoria": "comunicazione"
        })
    
    # === ALTRI ADEMPIMENTI ===
    # Libro inventari
    scadenze.append({
        "id": f"libro_inventari_{anno-1}",
        "tipo": "INVENTARI",
        "descrizione": f"Stampa/archiviazione libro inventari {anno-1}",
        "data": f"{anno}-12-31",
        "note": "Entro 3 mesi dal termine dichiarazione",
        "categoria": "adempimento"
    })
    
    # Conservazione documenti
    scadenze.append({
        "id": f"conservazione_{anno-1}",
        "tipo": "CONSERVAZIONE",
        "descrizione": f"Conservazione digitale documenti {anno-1}",
        "data": f"{anno}-12-31",
        "note": "Entro 3 mesi dal termine dichiarazione",
        "categoria": "adempimento"
    })
    
    # Diritto annuale CCIAA
    scadenze.append({
        "id": f"cciaa_{anno}",
        "tipo": "CCIAA",
        "descrizione": f"Diritto annuale Camera di Commercio {anno}",
        "data": f"{anno}-06-30",
        "categoria": "versamento"
    })
    
    # Vidimazione libri sociali
    scadenze.append({
        "id": f"vidimazione_{anno}",
        "tipo": "LIBRI_SOCIALI",
        "descrizione": f"Vidimazione libri sociali {anno}",
        "data": f"{anno}-03-16",
        "note": "Tassa annuale vidimazione libri €309,87 (o €516,46)",
        "codice_tributo": "7085",
        "categoria": "versamento"
    })
    
    return scadenze


# ============================================
# MODELLI PYDANTIC
# ============================================

class F24Create(BaseModel):
    """Registrazione F24"""
    data_versamento: str
    data_scadenza: str
    tributi: List[Dict[str, Any]]  # [{codice_tributo, importo, periodo_riferimento, anno}]
    crediti_compensati: Optional[List[Dict[str, Any]]] = None
    totale_versato: float
    modalita: str = "telematico"  # telematico, banca
    note: Optional[str] = None


class ChiusuraEsercizioParams(BaseModel):
    """Parametri chiusura esercizio"""
    anno: int
    data_chiusura: str = None  # Default 31/12


# ============================================
# HELPER
# ============================================

def round_currency(amount: float) -> float:
    return float(Decimal(str(amount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


async def crea_scrittura(db, data: str, ref: str, righe: List[Dict], tipo: str = "general") -> str:
    """Crea scrittura contabile"""
    move_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    total_dare = sum(r.get('dare', 0) for r in righe)
    total_avere = sum(r.get('avere', 0) for r in righe)
    
    if abs(total_dare - total_avere) > 0.01:
        raise HTTPException(status_code=400, detail=f"Non bilanciato: DARE {total_dare} ≠ AVERE {total_avere}")
    
    await db["prima_nota"].insert_one({
        "id": move_id, "date": data, "ref": ref, "journal_type": tipo,
        "total_debit": round_currency(total_dare), "total_credit": round_currency(total_avere),
        "state": "posted", "created_at": now
    })
    
    for i, r in enumerate(righe):
        await db["prima_nota_righe"].insert_one({
            "id": str(uuid.uuid4()), "move_id": move_id, "sequence": i + 1,
            "account_code": r['conto'], "account_name": r.get('nome_conto', ''),
            "debit": round_currency(r.get('dare', 0)), "credit": round_currency(r.get('avere', 0)),
            "name": r.get('descrizione', ''), "date": data, "created_at": now
        })
    
    return move_id


# ============================================
# ENDPOINTS AGEVOLAZIONI
# ============================================

@router.get("/agevolazioni")
async def lista_agevolazioni(
    categoria: str = Query(None),
    attivo: bool = Query(True)
) -> Dict[str, Any]:
    """Lista tutte le agevolazioni fiscali per SRL"""
    db = Database.get_db()
    
    # Carica da database se presenti, altrimenti usa default
    agevolazioni = await db["agevolazioni_fiscali"].find(
        {"attivo": attivo} if attivo else {},
        {"_id": 0}
    ).to_list(100)
    
    if not agevolazioni:
        # Inizializza database con copie dei dati default
        for ag in AGEVOLAZIONI_FISCALI_SRL:
            ag_copy = dict(ag)  # Copia per evitare mutazione con _id
            ag_copy["created_at"] = datetime.now(timezone.utc).isoformat()
            await db["agevolazioni_fiscali"].insert_one(ag_copy)
        # Ricarica dal database senza _id
        agevolazioni = await db["agevolazioni_fiscali"].find({}, {"_id": 0}).to_list(100)
    
    if categoria:
        agevolazioni = [a for a in agevolazioni if a.get("categoria") == categoria]
    
    return {
        "success": True,
        "totale": len(agevolazioni),
        "categorie": list(set(a.get("categoria") for a in agevolazioni)),
        "agevolazioni": agevolazioni
    }


@router.get("/agevolazioni/{agevolazione_id}")
async def dettaglio_agevolazione(agevolazione_id: str) -> Dict[str, Any]:
    """Dettaglio singola agevolazione"""
    db = Database.get_db()
    
    ag = await db["agevolazioni_fiscali"].find_one({"id": agevolazione_id}, {"_id": 0})
    if not ag:
        # Cerca nei default
        ag = next((a for a in AGEVOLAZIONI_FISCALI_SRL if a["id"] == agevolazione_id), None)
    
    if not ag:
        raise HTTPException(status_code=404, detail="Agevolazione non trovata")
    
    return {"success": True, "agevolazione": ag}


@router.post("/agevolazioni/simula")
async def simula_agevolazione(
    agevolazione_id: str = Query(...),
    importo_investimento: float = Query(...),
    dimensione_impresa: str = Query("piccola")  # piccola, media, grande
) -> Dict[str, Any]:
    """Simula il beneficio di un'agevolazione"""
    db = Database.get_db()
    
    ag = await db["agevolazioni_fiscali"].find_one({"id": agevolazione_id}, {"_id": 0})
    if not ag:
        ag = next((a for a in AGEVOLAZIONI_FISCALI_SRL if a["id"] == agevolazione_id), None)
    
    if not ag:
        raise HTTPException(status_code=404, detail="Agevolazione non trovata")
    
    # Determina aliquota
    if dimensione_impresa == "piccola":
        aliquota = ag.get("aliquota", 0)
    elif dimensione_impresa == "media":
        aliquota = ag.get("aliquota_medie", ag.get("aliquota", 0))
    else:
        aliquota = ag.get("aliquota_grandi", ag.get("aliquota", 0))
    
    # Calcola beneficio
    beneficio_lordo = round_currency(importo_investimento * aliquota / 100)
    
    # Applica massimale
    massimale = ag.get("massimale", float('inf'))
    beneficio_netto = min(beneficio_lordo, massimale)
    
    return {
        "success": True,
        "agevolazione": ag["nome"],
        "importo_investimento": importo_investimento,
        "dimensione_impresa": dimensione_impresa,
        "aliquota_applicata": aliquota,
        "beneficio_lordo": beneficio_lordo,
        "massimale": massimale,
        "beneficio_netto": beneficio_netto,
        "codice_tributo": ag.get("codice_tributo_f24"),
        "note": ag.get("note", "")
    }


# ============================================
# ENDPOINTS CALENDARIO FISCALE
# ============================================

@router.get("/calendario/scadenze-imminenti")
async def scadenze_imminenti(giorni: int = Query(30)) -> Dict[str, Any]:
    """Scadenze nei prossimi N giorni"""
    db = Database.get_db()
    
    oggi = datetime.now()
    limite = (oggi + timedelta(days=giorni)).strftime("%Y-%m-%d")
    oggi_str = oggi.strftime("%Y-%m-%d")
    
    scadenze = await db["calendario_fiscale"].find(
        {
            "data": {"$gte": oggi_str, "$lte": limite},
            "completato": False
        },
        {"_id": 0}
    ).sort("data", 1).to_list(100)
    
    # Raggruppa per urgenza
    urgenti = []  # Entro 7 giorni
    prossime = []  # 8-14 giorni
    future = []  # 15+ giorni
    
    for s in scadenze:
        try:
            data_scad = datetime.strptime(s["data"], "%Y-%m-%d")
            diff = (data_scad - oggi).days
            
            if diff <= 7:
                urgenti.append(s)
            elif diff <= 14:
                prossime.append(s)
            else:
                future.append(s)
        except (ValueError, KeyError):
            future.append(s)  # In caso di errore, metti nelle future
    
    return {
        "success": True,
        "periodo": f"{oggi_str} - {limite}",
        "urgenti_7_giorni": urgenti,
        "prossime_8_14_giorni": prossime,
        "future_15_plus": future,
        "totale": len(scadenze)
    }


@router.get("/calendario/{anno}")
async def calendario_fiscale(anno: int) -> Dict[str, Any]:
    """Genera calendario fiscale completo per l'anno"""
    db = Database.get_db()
    
    # Verifica se già generato
    existing = await db["calendario_fiscale"].find(
        {"anno": anno},
        {"_id": 0}
    ).to_list(500)
    
    if not existing:
        # Genera e salva
        scadenze = genera_scadenze_anno(anno)
        for s in scadenze:
            s_copy = dict(s)  # Copia per evitare mutazione con _id
            s_copy["anno"] = anno
            s_copy["completato"] = False
            s_copy["created_at"] = datetime.now(timezone.utc).isoformat()
            await db["calendario_fiscale"].insert_one(s_copy)
        # Ricarica senza _id
        existing = await db["calendario_fiscale"].find({"anno": anno}, {"_id": 0}).to_list(500)
    
    # Raggruppa per mese
    per_mese = {}
    for s in existing:
        mese = s["data"][5:7] if s.get("data") else "00"
        if mese not in per_mese:
            per_mese[mese] = []
        per_mese[mese].append(s)
    
    # Ordina per data
    for mese in per_mese:
        per_mese[mese].sort(key=lambda x: x.get("data", ""))
    
    # Prossime scadenze
    oggi = datetime.now().strftime("%Y-%m-%d")
    prossime = [s for s in existing if s.get("data", "") >= oggi and not s.get("completato")]
    prossime.sort(key=lambda x: x.get("data", ""))
    
    return {
        "success": True,
        "anno": anno,
        "totale_scadenze": len(existing),
        "completate": len([s for s in existing if s.get("completato")]),
        "scadenze_per_mese": per_mese,
        "prossime_5": prossime[:5],
        "scadenze": existing  # Aggiungi lista completa
    }


@router.post("/calendario/completa/{scadenza_id}")
async def completa_scadenza(scadenza_id: str, note: str = Query(None)) -> Dict[str, Any]:
    """Marca una scadenza come completata"""
    db = Database.get_db()
    
    result = await db["calendario_fiscale"].update_one(
        {"id": scadenza_id},
        {"$set": {
            "completato": True,
            "data_completamento": datetime.now(timezone.utc).isoformat(),
            "note_completamento": note
        }}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Scadenza non trovata")
    
    return {"success": True, "message": "Scadenza completata"}


@router.get("/notifiche-scadenze")
async def get_notifiche_scadenze_imminenti(
    giorni: int = Query(7, ge=1, le=30),
    anno: int = Query(None)
) -> Dict[str, Any]:
    """
    Recupera le scadenze imminenti per notifiche.
    Utile per sistemi di alert e dashboard.
    """
    db = Database.get_db()
    
    if not anno:
        anno = datetime.now().year
    
    oggi = datetime.now().strftime("%Y-%m-%d")
    data_limite = (datetime.now() + timedelta(days=giorni)).strftime("%Y-%m-%d")
    
    scadenze = await db["calendario_fiscale"].find(
        {
            "anno": anno,
            "completato": {"$ne": True},
            "data": {"$gte": oggi, "$lte": data_limite}
        },
        {"_id": 0}
    ).sort("data", 1).to_list(50)
    
    # Raggruppa per urgenza
    urgenti = []  # entro 3 giorni
    prossime = []  # 4-7 giorni
    pianificabili = []  # oltre 7 giorni
    
    oggi_dt = datetime.now()
    for s in scadenze:
        try:
            data_scad = datetime.strptime(s.get("data", ""), "%Y-%m-%d") if s.get("data") else None
            if data_scad:
                diff = (data_scad - oggi_dt).days
                if diff <= 3:
                    s["urgenza"] = "critica"
                    urgenti.append(s)
                elif diff <= 7:
                    s["urgenza"] = "alta"
                    prossime.append(s)
                else:
                    s["urgenza"] = "normale"
                    pianificabili.append(s)
        except ValueError:
            s["urgenza"] = "normale"
            pianificabili.append(s)
    
    return {
        "success": True,
        "anno": anno,
        "giorni_analizzati": giorni,
        "data_riferimento": oggi,
        "totale_imminenti": len(scadenze),
        "urgenti": urgenti,
        "prossime": prossime,
        "pianificabili": pianificabili,
        "riepilogo": {
            "critiche": len(urgenti),
            "alta_priorita": len(prossime),
            "normali": len(pianificabili)
        }
    }


@router.post("/notifiche-scadenze/invia")
async def invia_notifica_scadenza(
    scadenza_id: str = Query(...),
    tipo_notifica: str = Query("dashboard", enum=["dashboard", "email"])
) -> Dict[str, Any]:
    """
    Crea una notifica per una scadenza specifica.
    
    Tipi:
    - dashboard: Notifica visibile in app
    - email: Prepara email (richiede integrazione email)
    """
    db = Database.get_db()
    
    # Recupera scadenza
    scadenza = await db["calendario_fiscale"].find_one({"id": scadenza_id}, {"_id": 0})
    if not scadenza:
        raise HTTPException(status_code=404, detail="Scadenza non trovata")
    
    now = datetime.now(timezone.utc).isoformat()
    
    if tipo_notifica == "dashboard":
        # Crea notifica in app
        notifica = {
            "id": str(uuid.uuid4()),
            "tipo": "scadenza_fiscale",
            "titolo": f"Scadenza: {scadenza.get('descrizione', 'N/A')}",
            "messaggio": f"Scadenza il {scadenza.get('data', 'N/A')} - {scadenza.get('tipo', '').upper()}",
            "data": scadenza.get("data"),
            "scadenza_id": scadenza_id,
            "letta": False,
            "created_at": now
        }
        await db["notifications"].insert_one(notifica)
        
        return {
            "success": True,
            "tipo": "dashboard",
            "notifica_id": notifica["id"],
            "message": "Notifica creata in dashboard"
        }
    
    elif tipo_notifica == "email":
        # Prepara template email (non invia, serve integrazione)
        email_data = {
            "oggetto": f"[SCADENZA FISCALE] {scadenza.get('descrizione', '')}",
            "corpo": f"""
Promemoria scadenza fiscale:

Descrizione: {scadenza.get('descrizione', 'N/A')}
Data scadenza: {scadenza.get('data', 'N/A')}
Tipo: {scadenza.get('tipo', 'N/A').upper()}
Note: {scadenza.get('note', '-')}

---
Questo promemoria è stato generato automaticamente dal sistema.
            """.strip(),
            "scadenza": scadenza,
            "prepared_at": now
        }
        
        return {
            "success": True,
            "tipo": "email",
            "email_data": email_data,
            "message": "Email preparata (richiede integrazione email per invio)"
        }
    
    return {"success": False, "error": "Tipo notifica non valido"}


# ============================================
# ENDPOINTS F24
# ============================================

@router.post("/f24/registra")
async def registra_f24(f24: F24Create) -> Dict[str, Any]:
    """
    Registra versamento F24.
    
    Scrittura contabile:
    - DARE: Debiti tributari/previdenziali (chiusura debito)
    - AVERE: Banca (uscita denaro)
    - Se compensazione: DARE Banca, AVERE Crediti tributari
    """
    db = Database.get_db()
    
    f24_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    righe_contabili = []
    
    # Tributi versati (chiusura debiti)
    for tributo in f24.tributi:
        codice = tributo.get("codice_tributo", "")
        importo = tributo.get("importo", 0)
        
        # Determina conto debito in base al codice tributo
        if codice.startswith("10"):  # Ritenute
            conto = "231200"
            nome = "Debiti tributari"
        elif codice.startswith("60"):  # IVA
            conto = "231200"
            nome = "Erario c/IVA"
        elif codice.startswith("20"):  # IRES
            conto = "231200"
            nome = "Debiti IRES"
        elif codice.startswith("38"):  # IRAP
            conto = "231200"
            nome = "Debiti IRAP"
        elif codice in ["DM10", "DMRA"]:  # INPS
            conto = "231300"
            nome = "Debiti INPS"
        else:
            conto = "231200"
            nome = "Altri debiti tributari"
        
        righe_contabili.append({
            'conto': conto,
            'nome_conto': nome,
            'dare': importo,
            'avere': 0,
            'descrizione': f"F24 - {codice} - {tributo.get('periodo_riferimento', '')}"
        })
    
    # Crediti compensati (se presenti)
    totale_compensato = 0
    if f24.crediti_compensati:
        for credito in f24.crediti_compensati:
            importo_comp = credito.get("importo", 0)
            totale_compensato += importo_comp
            
            righe_contabili.append({
                'conto': '140500',  # Crediti tributari
                'nome_conto': 'Crediti tributari',
                'dare': 0,
                'avere': importo_comp,
                'descrizione': f"Compensazione {credito.get('codice_tributo', '')}"
            })
    
    # Uscita banca (netto versato)
    netto_versato = f24.totale_versato
    if netto_versato > 0:
        righe_contabili.append({
            'conto': '160100',
            'nome_conto': 'Banca c/c',
            'dare': 0,
            'avere': netto_versato,
            'descrizione': f"Versamento F24 {f24.data_versamento}"
        })
    
    # Crea scrittura
    move_id = await crea_scrittura(db, f24.data_versamento, f"F24/{f24.data_versamento}", righe_contabili, "bank")
    
    # Salva F24
    doc = {
        "id": f24_id,
        "data_versamento": f24.data_versamento,
        "data_scadenza": f24.data_scadenza,
        "tributi": f24.tributi,
        "crediti_compensati": f24.crediti_compensati,
        "totale_tributi": sum(t.get("importo", 0) for t in f24.tributi),
        "totale_compensato": totale_compensato,
        "totale_versato": netto_versato,
        "modalita": f24.modalita,
        "note": f24.note,
        "move_id": move_id,
        "created_at": now
    }
    await db["f24"].insert_one(doc)
    
    # Aggiorna scadenze calendario
    for tributo in f24.tributi:
        codice = tributo.get("codice_tributo", "")
        await db["calendario_fiscale"].update_many(
            {"codice_tributo": codice, "completato": False},
            {"$set": {"completato": True, "f24_id": f24_id}}
        )
    
    return {
        "success": True,
        "f24_id": f24_id,
        "totale_tributi": doc["totale_tributi"],
        "totale_compensato": totale_compensato,
        "totale_versato": netto_versato,
        "move_id": move_id
    }


@router.get("/f24/storico")
async def storico_f24(anno: int = Query(None)) -> Dict[str, Any]:
    """Storico F24 versati"""
    db = Database.get_db()
    
    query = {}
    if anno:
        query["data_versamento"] = {"$regex": f"^{anno}"}
    
    f24s = await db["f24"].find(query, {"_id": 0}).sort("data_versamento", -1).to_list(500)
    
    totale_versato = sum(f.get("totale_versato", 0) for f in f24s)
    totale_compensato = sum(f.get("totale_compensato", 0) for f in f24s)
    
    return {
        "success": True,
        "anno": anno,
        "totale_f24": len(f24s),
        "totale_versato": round_currency(totale_versato),
        "totale_compensato": round_currency(totale_compensato),
        "f24": f24s
    }


# ============================================
# CHIUSURA/APERTURA ESERCIZIO
# ============================================

@router.post("/chiusura-esercizio")
async def esegui_chiusura_esercizio(params: ChiusuraEsercizioParams) -> Dict[str, Any]:
    """
    Esegue la chiusura contabile dell'esercizio.
    
    Operazioni:
    1. Epilogo conti economici (ricavi e costi → Conto Economico)
    2. Rilevazione utile/perdita
    3. Chiusura conti patrimoniali (giro a Stato Patrimoniale Finale)
    """
    db = Database.get_db()
    
    anno = params.anno
    data_chiusura = params.data_chiusura or f"{anno}-12-31"
    
    # 1. Calcola saldi conti economici
    pipeline = [
        {"$match": {"date": {"$gte": f"{anno}-01-01", "$lte": data_chiusura}}},
        {
            "$group": {
                "_id": "$account_code",
                "account_name": {"$first": "$account_name"},
                "totale_dare": {"$sum": "$debit"},
                "totale_avere": {"$sum": "$credit"}
            }
        }
    ]
    
    saldi = await db["prima_nota_righe"].aggregate(pipeline).to_list(500)
    
    # Separa ricavi e costi
    ricavi = []
    costi = []
    
    for s in saldi:
        code = s["_id"]
        if not code:
            continue
        
        saldo_dare = round_currency(s["totale_dare"])
        saldo_avere = round_currency(s["totale_avere"])
        
        # Ricavi (3xx, 5xx) - saldo AVERE
        if code and (code.startswith('3') or code.startswith('5')):
            if saldo_avere > saldo_dare:
                ricavi.append({
                    "conto": code,
                    "nome": s.get("account_name", ""),
                    "saldo": round_currency(saldo_avere - saldo_dare)
                })
        
        # Costi (4xx) - saldo DARE
        elif code and code.startswith('4'):
            if saldo_dare > saldo_avere:
                costi.append({
                    "conto": code,
                    "nome": s.get("account_name", ""),
                    "saldo": round_currency(saldo_dare - saldo_avere)
                })
    
    totale_ricavi = sum(r["saldo"] for r in ricavi)
    totale_costi = sum(c["saldo"] for c in costi)
    risultato = round_currency(totale_ricavi - totale_costi)
    
    # 2. Scrittura epilogo ricavi → Conto Economico
    righe_epilogo_ricavi = []
    for r in ricavi:
        righe_epilogo_ricavi.append({
            'conto': r["conto"],
            'nome_conto': r["nome"],
            'dare': r["saldo"],  # Chiudo il ricavo (AVERE) con DARE
            'avere': 0,
            'descrizione': f'Epilogo {r["nome"]}'
        })
    
    if righe_epilogo_ricavi:
        righe_epilogo_ricavi.append({
            'conto': '200900',  # Conto Economico / Utile esercizio
            'nome_conto': 'Conto Economico',
            'dare': 0,
            'avere': totale_ricavi,
            'descrizione': 'Totale ricavi a C/E'
        })
        
        await crea_scrittura(db, data_chiusura, f"CHIUS/RICAVI/{anno}", righe_epilogo_ricavi, "general")
    
    # 3. Scrittura epilogo costi → Conto Economico
    righe_epilogo_costi = []
    for c in costi:
        righe_epilogo_costi.append({
            'conto': c["conto"],
            'nome_conto': c["nome"],
            'dare': 0,
            'avere': c["saldo"],  # Chiudo il costo (DARE) con AVERE
            'descrizione': f'Epilogo {c["nome"]}'
        })
    
    if righe_epilogo_costi:
        righe_epilogo_costi.append({
            'conto': '200900',
            'nome_conto': 'Conto Economico',
            'dare': totale_costi,
            'avere': 0,
            'descrizione': 'Totale costi a C/E'
        })
        
        await crea_scrittura(db, data_chiusura, f"CHIUS/COSTI/{anno}", righe_epilogo_costi, "general")
    
    # 4. Rilevazione utile/perdita
    if risultato > 0:
        # Utile
        righe_utile = [
            {'conto': '200900', 'nome_conto': 'Conto Economico', 'dare': risultato, 'avere': 0, 'descrizione': f'Utile esercizio {anno}'},
            {'conto': '200900', 'nome_conto': 'Utile dell\'esercizio', 'dare': 0, 'avere': risultato, 'descrizione': f'Utile {anno}'}
        ]
    else:
        # Perdita
        perdita = abs(risultato)
        righe_utile = [
            {'conto': '200900', 'nome_conto': 'Perdita dell\'esercizio', 'dare': perdita, 'avere': 0, 'descrizione': f'Perdita {anno}'},
            {'conto': '200900', 'nome_conto': 'Conto Economico', 'dare': 0, 'avere': perdita, 'descrizione': f'Perdita esercizio {anno}'}
        ]
    
    move_risultato = await crea_scrittura(db, data_chiusura, f"CHIUS/RISULTATO/{anno}", righe_utile, "general")
    
    # Salva chiusura
    await db["chiusure_esercizio"].insert_one({
        "id": str(uuid.uuid4()),
        "anno": anno,
        "data_chiusura": data_chiusura,
        "totale_ricavi": totale_ricavi,
        "totale_costi": totale_costi,
        "risultato": risultato,
        "tipo_risultato": "utile" if risultato >= 0 else "perdita",
        "ricavi_dettaglio": ricavi,
        "costi_dettaglio": costi,
        "move_id_risultato": move_risultato,
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    
    return {
        "success": True,
        "anno": anno,
        "data_chiusura": data_chiusura,
        "totale_ricavi": totale_ricavi,
        "totale_costi": totale_costi,
        "risultato": risultato,
        "tipo": "UTILE" if risultato >= 0 else "PERDITA",
        "conti_ricavi_chiusi": len(ricavi),
        "conti_costi_chiusi": len(costi)
    }


@router.post("/apertura-esercizio")
async def esegui_apertura_esercizio(anno: int = Query(...)) -> Dict[str, Any]:
    """
    Esegue l'apertura dei conti per il nuovo esercizio.
    
    Riapre i conti patrimoniali (Stato Patrimoniale) con i saldi
    di chiusura dell'esercizio precedente.
    """
    db = Database.get_db()
    
    anno_prec = anno - 1
    data_apertura = f"{anno}-01-01"
    
    # Recupera saldi patrimoniali al 31/12 anno precedente
    pipeline = [
        {"$match": {"date": {"$lte": f"{anno_prec}-12-31"}}},
        {
            "$group": {
                "_id": "$account_code",
                "account_name": {"$first": "$account_name"},
                "totale_dare": {"$sum": "$debit"},
                "totale_avere": {"$sum": "$credit"}
            }
        }
    ]
    
    saldi = await db["prima_nota_righe"].aggregate(pipeline).to_list(500)
    
    # Filtra solo conti patrimoniali (1xx, 2xx)
    righe_apertura = []
    
    for s in saldi:
        code = s["_id"]
        if not code or not (code.startswith('1') or code.startswith('2')):
            continue
        
        saldo = round_currency(s["totale_dare"] - s["totale_avere"])
        
        if abs(saldo) < 0.01:
            continue
        
        if saldo > 0:
            # Saldo DARE - attività
            righe_apertura.append({
                'conto': code,
                'nome_conto': s.get("account_name", ""),
                'dare': saldo,
                'avere': 0,
                'descrizione': f'Apertura {anno}'
            })
        else:
            # Saldo AVERE - passività
            righe_apertura.append({
                'conto': code,
                'nome_conto': s.get("account_name", ""),
                'dare': 0,
                'avere': abs(saldo),
                'descrizione': f'Apertura {anno}'
            })
    
    if not righe_apertura:
        return {
            "success": True,
            "anno": anno,
            "message": "Nessun conto patrimoniale da riaprire",
            "conti_aperti": 0
        }
    
    # Le scritture di apertura devono bilanciare
    # Usiamo un conto transitorio "Bilancio di apertura"
    totale_dare = sum(r['dare'] for r in righe_apertura)
    totale_avere = sum(r['avere'] for r in righe_apertura)
    differenza = round_currency(totale_dare - totale_avere)
    
    if abs(differenza) > 0.01:
        if differenza > 0:
            righe_apertura.append({
                'conto': '200800',
                'nome_conto': 'Utili portati a nuovo',
                'dare': 0,
                'avere': differenza,
                'descrizione': f'Saldo apertura {anno}'
            })
        else:
            righe_apertura.append({
                'conto': '200800',
                'nome_conto': 'Perdite portate a nuovo',
                'dare': abs(differenza),
                'avere': 0,
                'descrizione': f'Saldo apertura {anno}'
            })
    
    move_id = await crea_scrittura(db, data_apertura, f"APER/{anno}", righe_apertura, "general")
    
    return {
        "success": True,
        "anno": anno,
        "data_apertura": data_apertura,
        "conti_aperti": len(righe_apertura),
        "totale_attivita": totale_dare,
        "totale_passivita": totale_avere,
        "move_id": move_id
    }
