"""
Router per la gestione delle Chiusure e Festività aziendali.
Gestisce giorni di chiusura, ferie, festività e stati speciali.

Chiusure fisse:
- 1 Gennaio (Capodanno)
- Pasqua (calcolata dinamicamente)
- 12-24 Agosto (Ferie estive)
"""

from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel
from typing import List, Optional, Dict
from datetime import datetime, timezone, date, timedelta
import logging
import uuid

# NOTE: random usato per generazione dati demo HACCP con seed fisso (riproducibilità). NON usato per operazioni di sicurezza.
import random

from app.lotti.db import database as db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chiusure", tags=["Chiusure e Festività"])

# MongoDB connection
# ==================== CALCOLO PASQUA ====================


def calcola_pasqua(anno: int) -> date:
    """
    Calcola la data di Pasqua usando l'algoritmo di Meeus/Jones/Butcher.
    Valido per anni dal 1583 in poi (calendario gregoriano).
    """
    a = anno % 19
    b = anno // 100
    c = anno % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mese = (h + l - 7 * m + 114) // 31
    giorno = ((h + l - 7 * m + 114) % 31) + 1
    return date(anno, mese, giorno)


def calcola_lunedi_pasqua(anno: int) -> date:
    """Calcola il Lunedì dell'Angelo (Pasquetta)"""
    pasqua = calcola_pasqua(anno)
    return pasqua + timedelta(days=1)


# ==================== FESTIVITÀ ITALIANE FISSE ====================


def get_festivita_fisse(anno: int) -> List[dict]:
    """Restituisce le festività fisse italiane"""
    return [
        {"data": date(anno, 1, 1), "nome": "Capodanno", "tipo": "festivita"},
        {"data": date(anno, 1, 6), "nome": "Epifania", "tipo": "festivita"},
        {"data": date(anno, 4, 25), "nome": "Festa della Liberazione", "tipo": "festivita"},
        {"data": date(anno, 5, 1), "nome": "Festa dei Lavoratori", "tipo": "festivita"},
        {"data": date(anno, 6, 2), "nome": "Festa della Repubblica", "tipo": "festivita"},
        {"data": date(anno, 8, 15), "nome": "Ferragosto", "tipo": "festivita"},
        {"data": date(anno, 11, 1), "nome": "Tutti i Santi", "tipo": "festivita"},
        {"data": date(anno, 12, 8), "nome": "Immacolata Concezione", "tipo": "festivita"},
        {"data": date(anno, 12, 25), "nome": "Natale", "tipo": "festivita"},
        {"data": date(anno, 12, 26), "nome": "Santo Stefano", "tipo": "festivita"},
    ]


def get_festivita_mobili(anno: int) -> List[dict]:
    """Restituisce le festività mobili (Pasqua e Pasquetta)"""
    pasqua = calcola_pasqua(anno)
    pasquetta = calcola_lunedi_pasqua(anno)
    return [
        {"data": pasqua, "nome": "Pasqua", "tipo": "festivita"},
        {"data": pasquetta, "nome": "Lunedì dell'Angelo", "tipo": "festivita"},
    ]


def get_ferie_aziendali(anno: int) -> List[dict]:
    """Restituisce i giorni di ferie aziendali (12-24 Agosto)"""
    ferie = []
    for giorno in range(12, 25):  # 12-24 agosto inclusi
        ferie.append({"data": date(anno, 8, giorno), "nome": "Ferie Estive", "tipo": "ferie"})
    return ferie


# ==================== CHIUSURE OBBLIGATORIE ====================


def get_chiusure_obbligatorie(anno: int) -> List[dict]:
    """
    Restituisce tutte le chiusure obbligatorie per l'anno specificato.
    Include: Capodanno, Pasqua, Ferie 12-24 Agosto.
    """
    chiusure = []

    # 1 Gennaio - Capodanno
    chiusure.append(
        {
            "data": date(anno, 1, 1),
            "nome": "Capodanno - CHIUSO",
            "tipo": "chiusura_obbligatoria",
            "motivo": "Misurazione non pervenuta - CHIUSI",
        }
    )

    # Pasqua e Pasquetta
    pasqua = calcola_pasqua(anno)
    pasquetta = calcola_lunedi_pasqua(anno)
    chiusure.append(
        {
            "data": pasqua,
            "nome": "Pasqua - CHIUSO",
            "tipo": "chiusura_obbligatoria",
            "motivo": "Misurazione non pervenuta - CHIUSI",
        }
    )
    chiusure.append(
        {
            "data": pasquetta,
            "nome": "Lunedì dell'Angelo - CHIUSO",
            "tipo": "chiusura_obbligatoria",
            "motivo": "Misurazione non pervenuta - CHIUSI",
        }
    )

    # Ferie 12-24 Agosto
    for giorno in range(12, 25):
        chiusure.append(
            {
                "data": date(anno, 8, giorno),
                "nome": "Ferie Estive - CHIUSO",
                "tipo": "ferie",
                "motivo": "Misurazione non pervenuta - CHIUSI",
            }
        )

    return chiusure


# ==================== STATI SPECIALI (MANUTENZIONE, NON USATO) ====================


def genera_stati_speciali_random(anno: int, seed: int = None) -> Dict[str, List[dict]]:
    """
    Genera stati speciali random per l'anno:
    - 2-3 periodi di "FRIGO SPENTO - MANUTENZIONE" (2-3 giorni ciascuno)
    - 1-2 periodi di "NON USATO" (max 5 giorni ciascuno)

    Returns: Dict con chiave "manutenzione" e "non_usato"
    """
    if seed:
        random.seed(seed)
    else:
        random.seed(anno * 1000)  # Seed basato sull'anno per consistenza

    stati = {"manutenzione": [], "non_usato": []}

    # Mesi disponibili (escluso agosto per ferie)
    mesi_disponibili = [1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12]

    # Genera 2-3 periodi di manutenzione
    num_manutenzioni = random.randint(2, 3)
    mesi_manutenzione = random.sample(mesi_disponibili, num_manutenzioni)

    for mese in mesi_manutenzione:
        durata = random.randint(2, 3)
        giorno_inizio = random.randint(5, 20)

        for i in range(durata):
            stati["manutenzione"].append(
                {
                    "data": date(anno, mese, giorno_inizio + i),
                    "nome": "FRIGO SPENTO - MANUTENZIONE",
                    "tipo": "manutenzione",
                    "motivo": "Frigo spento per manutenzione",
                }
            )

    # Genera 1-2 periodi di non usato
    mesi_rimanenti = [m for m in mesi_disponibili if m not in mesi_manutenzione]
    num_non_usato = random.randint(1, 2)
    mesi_non_usato = random.sample(mesi_rimanenti, min(num_non_usato, len(mesi_rimanenti)))

    for mese in mesi_non_usato:
        durata = random.randint(3, 5)
        giorno_inizio = random.randint(3, 18)

        for i in range(durata):
            stati["non_usato"].append(
                {
                    "data": date(anno, mese, giorno_inizio + i),
                    "nome": f"NON USATO dal {giorno_inizio}/{mese} al {giorno_inizio + durata - 1}/{mese}",
                    "tipo": "non_usato",
                    "motivo": "Apparecchio non utilizzato",
                }
            )

    return stati


# ==================== MODELLI ====================


class ChiusuraCustom(BaseModel):
    data: str  # formato DD/MM/YYYY
    nome: str
    motivo: Optional[str] = "Chiusura"


class ConfigChiusure(BaseModel):
    anno: int
    chiusure_custom: List[ChiusuraCustom] = []
    include_festivita: bool = True
    include_ferie_agosto: bool = True
    include_stati_speciali: bool = True


# ==================== ENDPOINTS ====================


@router.get("/anno/{anno}")
async def get_tutte_chiusure(anno: int):
    """
    Restituisce tutte le chiusure per l'anno specificato:
    - Chiusure obbligatorie (Capodanno, Pasqua, Ferie agosto)
    - Festività italiane
    - Stati speciali (manutenzione, non usato)
    - Chiusure custom salvate nel DB
    """

    # Chiusure obbligatorie
    chiusure_obbl = get_chiusure_obbligatorie(anno)

    # Festività
    festivita = get_festivita_fisse(anno) + get_festivita_mobili(anno)

    # Stati speciali
    stati_speciali = genera_stati_speciali_random(anno)

    # Chiusure custom dal DB
    chiusure_custom = await db.chiusure_custom.find({"anno": anno}, {"_id": 0}).to_list(100)

    # Prepara dizionario per lookup veloce
    chiusure_dict = {}

    # Aggiungi chiusure obbligatorie
    for c in chiusure_obbl:
        data_str = c["data"].strftime("%d/%m/%Y")
        chiusure_dict[data_str] = {
            "data": data_str,
            "nome": c["nome"],
            "tipo": c["tipo"],
            "motivo": c.get("motivo", "CHIUSO"),
            "is_chiuso": True,
        }

    # Aggiungi manutenzioni
    for m in stati_speciali["manutenzione"]:
        data_str = m["data"].strftime("%d/%m/%Y")
        if data_str not in chiusure_dict:  # Non sovrascrivere chiusure
            chiusure_dict[data_str] = {
                "data": data_str,
                "nome": m["nome"],
                "tipo": "manutenzione",
                "motivo": m["motivo"],
                "is_chiuso": False,
                "is_manutenzione": True,
            }

    # Aggiungi non usato
    for n in stati_speciali["non_usato"]:
        data_str = n["data"].strftime("%d/%m/%Y")
        if data_str not in chiusure_dict:
            chiusure_dict[data_str] = {
                "data": data_str,
                "nome": n["nome"],
                "tipo": "non_usato",
                "motivo": n["motivo"],
                "is_chiuso": False,
                "is_non_usato": True,
            }

    # Aggiungi custom
    for c in chiusure_custom:
        data_str = c.get("data", "")
        if data_str:
            chiusure_dict[data_str] = {
                "data": data_str,
                "nome": c.get("nome", "Chiusura"),
                "tipo": "custom",
                "motivo": c.get("motivo", "Chiusura custom"),
                "is_chiuso": True,
            }

    return {
        "anno": anno,
        "chiusure": list(chiusure_dict.values()),
        "chiusure_dict": chiusure_dict,
        "pasqua": calcola_pasqua(anno).strftime("%d/%m/%Y"),
        "pasquetta": calcola_lunedi_pasqua(anno).strftime("%d/%m/%Y"),
        "festivita": [
            {"data": f["data"].strftime("%d/%m/%Y"), "nome": f["nome"]} for f in festivita
        ],
        "ferie_agosto": "12/08 - 24/08",
        "stati_speciali": {
            "manutenzione": [
                {"data": m["data"].strftime("%d/%m/%Y"), "nome": m["nome"]}
                for m in stati_speciali["manutenzione"]
            ],
            "non_usato": [
                {"data": n["data"].strftime("%d/%m/%Y"), "nome": n["nome"]}
                for n in stati_speciali["non_usato"]
            ],
        },
    }


@router.get("/mese/{anno}/{mese}")
async def get_chiusure_mese(anno: int, mese: int):
    """Restituisce le chiusure per un mese specifico"""
    tutte = await get_tutte_chiusure(anno)

    chiusure_mese = {}
    for data_str, info in tutte["chiusure_dict"].items():
        try:
            parts = data_str.split("/")
            if len(parts) == 3 and int(parts[1]) == mese:
                giorno = int(parts[0])
                chiusure_mese[str(giorno)] = info
        except Exception as e:
            logging.exception(f"[chiusure] Errore non gestito: {e}")

    return {"anno": anno, "mese": mese, "chiusure": chiusure_mese}


@router.get("/giorno/{anno}/{mese}/{giorno}")
async def get_stato_giorno(anno: int, mese: int, giorno: int):
    """Verifica lo stato di un giorno specifico"""
    tutte = await get_tutte_chiusure(anno)
    data_str = f"{giorno:02d}/{mese:02d}/{anno}"

    if data_str in tutte["chiusure_dict"]:
        return {"is_chiuso": True, **tutte["chiusure_dict"][data_str]}

    return {"is_chiuso": False, "data": data_str, "tipo": "normale", "motivo": None}


@router.post("/custom")
async def aggiungi_chiusura_custom(chiusura: ChiusuraCustom, anno: int = Query(...)):
    """Aggiunge una chiusura custom"""
    doc = {
        "id": str(uuid.uuid4()),
        "anno": anno,
        "data": chiusura.data,
        "nome": chiusura.nome,
        "motivo": chiusura.motivo or "Chiusura",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    await db.chiusure_custom.insert_one(doc)
    del doc["_id"]

    return {"success": True, "chiusura": doc}


@router.delete("/custom/{data}")
async def rimuovi_chiusura_custom(data: str, anno: int = Query(...)):
    """Rimuove una chiusura custom"""
    result = await db.chiusure_custom.delete_one({"anno": anno, "data": data})

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Chiusura non trovata")

    return {"success": True, "message": f"Chiusura del {data} rimossa"}


@router.get("/festivita/{anno}")
async def get_festivita_anno(anno: int):
    """Restituisce tutte le festività italiane per l'anno"""
    festivita_fisse = get_festivita_fisse(anno)
    festivita_mobili = get_festivita_mobili(anno)

    return {
        "anno": anno,
        "festivita_fisse": [
            {"data": f["data"].strftime("%d/%m/%Y"), "nome": f["nome"]} for f in festivita_fisse
        ],
        "festivita_mobili": [
            {"data": f["data"].strftime("%d/%m/%Y"), "nome": f["nome"]} for f in festivita_mobili
        ],
        "pasqua": calcola_pasqua(anno).strftime("%d/%m/%Y"),
        "pasquetta": calcola_lunedi_pasqua(anno).strftime("%d/%m/%Y"),
    }


@router.get("/giorno-non-produttivo/oggi")
async def get_giorno_non_produttivo_oggi():
    """Controlla se oggi è marcato come giorno non produttivo."""
    oggi = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    doc = await db.giorni_non_produttivi.find_one({"data": oggi}, {"_id": 0})
    return {
        "data": oggi,
        "non_produttivo": bool(doc),
        "motivo": doc.get("motivo", "") if doc else "",
    }


@router.post("/giorno-non-produttivo/oggi")
async def segna_giorno_non_produttivo(payload: dict = Body(default={})):
    """Marca/demarks oggi come giorno non produttivo."""
    oggi = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    attivo = payload.get("attivo", True)
    motivo = payload.get("motivo", "Giorno non produttivo")

    if attivo:
        await db.giorni_non_produttivi.update_one(
            {"data": oggi},
            {
                "$set": {
                    "data": oggi,
                    "motivo": motivo,
                    "aggiornato": datetime.now(timezone.utc).isoformat(),
                }
            },
            upsert=True,
        )
        return {"success": True, "non_produttivo": True, "motivo": motivo}
    else:
        await db.giorni_non_produttivi.delete_one({"data": oggi})
        return {"success": True, "non_produttivo": False}


@router.get("/calendario/{anno}")
async def get_calendario_completo(anno: int):
    """
    Restituisce un calendario completo con tutti gli stati per ogni giorno dell'anno.
    Utile per popolare le schede temperature.
    """
    tutte = await get_tutte_chiusure(anno)

    calendario = {}
    for mese in range(1, 13):
        calendario[str(mese)] = {}

        # Determina giorni nel mese
        if mese in [1, 3, 5, 7, 8, 10, 12]:
            num_giorni = 31
        elif mese in [4, 6, 9, 11]:
            num_giorni = 30
        else:  # Febbraio
            if (anno % 4 == 0 and anno % 100 != 0) or (anno % 400 == 0):
                num_giorni = 29
            else:
                num_giorni = 28

        for giorno in range(1, num_giorni + 1):
            data_str = f"{giorno:02d}/{mese:02d}/{anno}"

            if data_str in tutte["chiusure_dict"]:
                info = tutte["chiusure_dict"][data_str]
                calendario[str(mese)][str(giorno)] = {
                    "stato": info.get("tipo", "chiuso"),
                    "motivo": info.get("motivo", "CHIUSO"),
                    "nome": info.get("nome", ""),
                    "is_chiuso": info.get("is_chiuso", True),
                    "is_manutenzione": info.get("is_manutenzione", False),
                    "is_non_usato": info.get("is_non_usato", False),
                }
            else:
                calendario[str(mese)][str(giorno)] = {
                    "stato": "normale",
                    "motivo": None,
                    "is_chiuso": False,
                    "is_manutenzione": False,
                    "is_non_usato": False,
                }

    return {"anno": anno, "calendario": calendario}
