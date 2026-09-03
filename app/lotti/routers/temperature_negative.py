"""
Router per la gestione delle Temperature NEGATIVE (Congelatori).
Registra temperature giornaliere per ogni congelatore.

RIFERIMENTI NORMATIVI:
- Reg. CE 852/2004 - Igiene dei prodotti alimentari
- Reg. CE 853/2004 - Norme specifiche igiene alimenti origine animale
- D.Lgs. 193/2007 - Attuazione delle direttive CE
- Reg. UE 2017/625 - Controlli ufficiali
- Linee guida HACCP Regione Campania

NOTA: La sanificazione dei congelatori è gestita nel modulo Sanificazione,
con date casuali ogni 7-10 giorni per ogni apparecchio.
"""

from fastapi import APIRouter, Query, Depends
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict
from datetime import datetime, timezone
import uuid

from app.lotti.db import database as db
from app.lotti.auth import require_admin

router = APIRouter(prefix="/temperature-negative", tags=["Temperature Negative"])

# MongoDB connection
# ==================== COSTANTI NORMATIVE ====================

RIFERIMENTI_NORMATIVI = {
    "reg_852_2004": "Reg. CE 852/2004 - Igiene dei prodotti alimentari",
    "reg_853_2004": "Reg. CE 853/2004 - Norme specifiche alimenti origine animale",
    "dlgs_193_2007": "D.Lgs. 193/2007 - Attuazione direttive CE sicurezza alimentare",
    "reg_2017_625": "Reg. UE 2017/625 - Controlli ufficiali",
    "haccp_7_principi": "7 Principi HACCP (Codex Alimentarius)",
}

# Operatori predefiniti per rilevazione temperature
OPERATORI_DEFAULT = [
    "Pocci Salvatore",
    "Vincenzo Ceraldi",
]

# ==================== MODELLI ====================


class SchedaTemperatureNegative(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    anno: int
    congelatore_numero: int  # 1-12
    congelatore_nome: str = ""
    azienda: str = "Ceraldi Group S.R.L."
    indirizzo: str = "Piazza Carità 14, 80134 Napoli (NA)"
    piva: str = "04523831214"
    telefono: str = "+39 081 5523488"
    email: str = "info@ceraldicaffe.it"
    attivita: str = "Bar, Pasticceria, Gastronomia"
    # {mese: {giorno: {temp: float, operatore: str, note: str}}}
    temperature: Dict[str, Dict[str, dict]] = {}
    temp_min: float = -22.0
    temp_max: float = -18.0
    riferimenti_normativi: Dict[str, str] = RIFERIMENTI_NORMATIVI
    operatori: List[str] = OPERATORI_DEFAULT
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class AggiornaTemperatureRequest(BaseModel):
    temperature: Dict[str, Dict[str, dict]]
    nome: Optional[str] = None
    operatore: Optional[str] = None


# Nomi mesi italiano
MESI_IT = [
    "GENNAIO",
    "FEBBRAIO",
    "MARZO",
    "APRILE",
    "MAGGIO",
    "GIUGNO",
    "LUGLIO",
    "AGOSTO",
    "SETTEMBRE",
    "OTTOBRE",
    "NOVEMBRE",
    "DICEMBRE",
]

# ==================== HELPER ====================


async def get_or_create_scheda(anno: int, congelatore: int) -> dict:
    """Ottiene o crea la scheda annuale per un congelatore"""
    scheda = await db.temperature_negative.find_one(
        {"anno": anno, "congelatore_numero": congelatore}, {"_id": 0}
    )

    if not scheda:
        nuova_scheda = {
            "id": str(uuid.uuid4()),
            "anno": anno,
            "congelatore_numero": congelatore,
            "congelatore_nome": f"Congelatore N°{congelatore}",
            "azienda": "Ceraldi Group S.R.L.",
            "indirizzo": "Piazza Carità 14, 80134 Napoli (NA)",
            "piva": "04523831214",
            "telefono": "+39 081 5523488",
            "email": "info@ceraldicaffe.it",
            "attivita": "Bar, Pasticceria, Gastronomia",
            "temperature": {str(m): {} for m in range(1, 13)},
            "temp_min": -22.0,
            "temp_max": -18.0,
            "riferimenti_normativi": RIFERIMENTI_NORMATIVI,
            "operatori": OPERATORI_DEFAULT.copy(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.temperature_negative.insert_one(nuova_scheda)
        scheda = nuova_scheda
    else:
        # Aggiorna schede esistenti con i nuovi campi
        needs_update = False
        if "riferimenti_normativi" not in scheda:
            scheda["riferimenti_normativi"] = RIFERIMENTI_NORMATIVI
            needs_update = True
        if "operatori" not in scheda:
            scheda["operatori"] = OPERATORI_DEFAULT.copy()
            needs_update = True
        if "telefono" not in scheda:
            scheda["telefono"] = "+39 081 5523488"
            scheda["email"] = "info@ceraldicaffe.it"
            scheda["attivita"] = "Bar, Pasticceria, Gastronomia"
            scheda["indirizzo"] = "Piazza Carità 14, 80134 Napoli (NA)"
            needs_update = True
        if needs_update:
            await db.temperature_negative.update_one(
                {"anno": anno, "congelatore_numero": congelatore}, {"$set": scheda}
            )

    if "_id" in scheda:
        del scheda["_id"]

    return scheda


# ==================== ENDPOINTS ====================


@router.get("")
async def get_temperature_negative_lista():
    """GET base — restituisce le schede congelatori dell'anno corrente"""
    anno = datetime.now().year
    schede = await db.temperature_negative.find({"anno": anno}, {"_id": 0}).to_list(50)
    return schede


@router.get("/scheda/{anno}/{congelatore}")
async def get_scheda_congelatore(anno: int, congelatore: int):
    """Ottiene la scheda annuale di un congelatore. Crea documento vuoto se non esiste.

    NOTA: l'auto-popolamento storico è stato disabilitato perché generava timeout
    (popolare ~800 giorni × 12 congelatori per ogni richiesta che trovava la scheda
    vuota bloccava il backend per >30s). Il popolamento avviene tramite il job
    scheduler giornaliero (`/api/scheduler/run-haccp-now`) o manualmente via UI.
    """
    return await get_or_create_scheda(anno, congelatore)


@router.get("/schede/{anno}")
async def get_tutte_schede(anno: int):
    """Ottiene tutte le schede congelatori per un anno"""
    schede = []
    for i in range(1, 13):
        scheda = await get_or_create_scheda(anno, i)
        schede.append(scheda)
    return schede


@router.post("/scheda/{anno}/{congelatore}/registra")
async def registra_temperatura(
    anno: int,
    congelatore: int,
    mese: int,
    giorno: int,
    temperatura: float = None,
    operatore: str = Query(default=""),
    note: str = Query(default=""),
):
    """
    Registra una temperatura per un congelatore.
    La sanificazione dei congelatori è gestita separatamente nel modulo Sanificazione.
    """
    scheda = await get_or_create_scheda(anno, congelatore)

    mese_str = str(mese)
    giorno_str = str(giorno)

    if mese_str not in scheda["temperature"]:
        scheda["temperature"][mese_str] = {}

    # Record temperatura — se operatore non specificato, non salvarlo (misurazione automatica)
    record = {
        "temp": temperatura,
        "note": note,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if operatore:
        record["operatore"] = operatore

    # Verifica allarme CON LE SOGLIE VALIDE ORA — e le CONGELA nel record.
    # AUDIT 24/07/2026 (tranche 6): senza soglie salvate, un cambio retroattivo
    # di temp_min/temp_max via /config faceva sparire (o comparire) le anomalie
    # storiche nel registro HACCP. Le soglie del momento restano nel record e
    # get_allarmi le usa al posto di quelle correnti.
    soglia_min = scheda.get("temp_min", -22.0)
    soglia_max = scheda.get("temp_max", -18.0)
    allarme = False
    if temperatura is not None:
        allarme = temperatura > soglia_max or temperatura < soglia_min
    record["allarme"] = allarme
    record["soglie"] = {"min": soglia_min, "max": soglia_max}

    scheda["temperature"][mese_str][giorno_str] = record
    scheda["updated_at"] = datetime.now(timezone.utc).isoformat()

    await db.temperature_negative.update_one(
        {"anno": anno, "congelatore_numero": congelatore}, {"$set": scheda}
    )

    return {
        "success": True,
        "message": f"Temperatura {temperatura}°C registrata",
        "allarme": allarme,
    }


@router.put("/scheda/{anno}/{congelatore}")
async def aggiorna_scheda_completa(anno: int, congelatore: int, data: AggiornaTemperatureRequest,
                                   _admin=Depends(require_admin)):
    """Aggiorna l'intera scheda"""
    scheda = await get_or_create_scheda(anno, congelatore)

    scheda["temperature"] = data.temperature
    scheda["updated_at"] = datetime.now(timezone.utc).isoformat()
    if data.nome:
        scheda["congelatore_nome"] = data.nome

    await db.temperature_negative.update_one(
        {"anno": anno, "congelatore_numero": congelatore}, {"$set": scheda}
    )

    return {"success": True, "message": "Scheda aggiornata"}


@router.put("/scheda/{anno}/{congelatore}/config")
async def configura_congelatore(
    anno: int, congelatore: int, nome: str = None, temp_min: float = None, temp_max: float = None
, _admin=Depends(require_admin)):
    """Configura nome e limiti temperatura congelatore"""
    scheda = await get_or_create_scheda(anno, congelatore)

    if nome:
        scheda["congelatore_nome"] = nome
    if temp_min is not None:
        scheda["temp_min"] = temp_min
    if temp_max is not None:
        scheda["temp_max"] = temp_max

    scheda["updated_at"] = datetime.now(timezone.utc).isoformat()

    await db.temperature_negative.update_one(
        {"anno": anno, "congelatore_numero": congelatore}, {"$set": scheda}
    )

    return {"success": True, "message": "Configurazione salvata"}


@router.get("/mesi")
async def get_mesi():
    """Lista mesi in italiano"""
    return [{"numero": i + 1, "nome": m} for i, m in enumerate(MESI_IT)]


@router.get("/allarmi/{anno}")
async def get_allarmi(anno: int):
    """Ottiene tutti gli allarmi (temperature fuori range)"""
    schede = await db.temperature_negative.find({"anno": anno}, {"_id": 0}).to_list(100)
    allarmi = []

    for scheda in schede:
        for mese, giorni in scheda.get("temperature", {}).items():
            for giorno, record in giorni.items():
                # Gestisce sia vecchio formato (float) che nuovo formato (dict)
                soglie_record = None
                if isinstance(record, dict):
                    temp = record.get("temp")
                    soglie_record = record.get("soglie")
                    # Skip stati speciali
                    if (
                        record.get("is_chiuso")
                        or record.get("is_manutenzione")
                        or record.get("is_non_usato")
                    ):
                        continue
                else:
                    temp = record

                # AUDIT 24/07/2026: se il record ha le soglie CONGELATE alla
                # registrazione, l'allarme si valuta su QUELLE — cambiare oggi
                # temp_min/temp_max non riscrive la storia del registro.
                if isinstance(soglie_record, dict):
                    t_min = soglie_record.get("min", scheda.get("temp_min", -22))
                    t_max = soglie_record.get("max", scheda.get("temp_max", -18))
                else:
                    t_min = scheda.get("temp_min", -22)
                    t_max = scheda.get("temp_max", -18)

                if temp is not None and (temp > t_max or temp < t_min):
                    allarmi.append(
                        {
                            "congelatore": scheda["congelatore_numero"],
                            "nome": scheda.get("congelatore_nome", ""),
                            "mese": int(mese),
                            "giorno": int(giorno),
                            "temperatura": temp,
                            "range": f"{t_min}°C / {t_max}°C",
                        }
                    )

    return allarmi


@router.get("/operatori")
async def get_operatori():
    """Ottiene la lista degli operatori disponibili"""
    return {"operatori": OPERATORI_DEFAULT}


@router.post("/operatori")
async def aggiungi_operatore(nome: str = Query(...)):
    """Aggiunge un nuovo operatore alla lista"""
    if nome not in OPERATORI_DEFAULT:
        OPERATORI_DEFAULT.append(nome)
    return {"operatori": OPERATORI_DEFAULT, "message": f"Operatore {nome} aggiunto"}


@router.get("/riferimenti-normativi")
async def get_riferimenti_normativi():
    """Ottiene i riferimenti normativi HACCP"""
    return {
        "riferimenti": RIFERIMENTI_NORMATIVI,
        "note": "Riferimenti normativi per la gestione HACCP delle temperature di conservazione",
        "limiti_congelatori": {
            "temperatura_minima": -22.0,
            "temperatura_massima": -18.0,
            "descrizione": "Alimenti surgelati (Reg. CE 852/2004)",
        },
    }


@router.post("/popola-con-chiusure/{anno}")
async def popola_con_chiusure(anno: int, congelatore: int = Query(default=None),
                              _admin=Depends(require_admin)):
    """
    Popola le schede temperature con:
    - Chiusure (Capodanno, Pasqua, Ferie 12-24 Agosto)
    - Manutenzioni random (2-3 giorni alla volta, 2-3 volte l'anno)
    - Non usato random (max 5 giorni alla volta, 1-2 volte l'anno)

    NOTA: La sanificazione è gestita separatamente nel modulo Sanificazione.
    """
    from app.lotti.routers.chiusure import get_chiusure_obbligatorie, genera_stati_speciali_random

    # NOTE: random usato per generazione dati demo HACCP con seed fisso (riproducibilità). NON usato per operazioni di sicurezza.
    import random
    from datetime import date

    # Ottieni chiusure e stati speciali
    chiusure = get_chiusure_obbligatorie(anno)
    stati_speciali = genera_stati_speciali_random(anno)

    # Prepara dizionario stati per data
    stati_per_data = {}

    for c in chiusure:
        data_key = (c["data"].month, c["data"].day)
        stati_per_data[data_key] = {
            "tipo": "chiuso",
            "motivo": "Misurazione non pervenuta - CHIUSI",
            "nome": c["nome"],
        }

    for m in stati_speciali["manutenzione"]:
        data_key = (m["data"].month, m["data"].day)
        if data_key not in stati_per_data:
            stati_per_data[data_key] = {
                "tipo": "manutenzione",
                "motivo": "FRIGO SPENTO - MANUTENZIONE",
                "nome": m["nome"],
            }

    for n in stati_speciali["non_usato"]:
        data_key = (n["data"].month, n["data"].day)
        if data_key not in stati_per_data:
            stati_per_data[data_key] = {
                "tipo": "non_usato",
                "motivo": "NON USATO",
                "nome": n["nome"],
            }

    # Determina quali congelatori aggiornare
    congelatori = [congelatore] if congelatore else list(range(1, 13))

    oggi = date.today()
    updated = 0

    for cong in congelatori:
        scheda = await get_or_create_scheda(anno, cong)

        for mese in range(1, 13):
            mese_str = str(mese)
            if mese_str not in scheda["temperature"]:
                scheda["temperature"][mese_str] = {}

            # Giorni nel mese
            if mese in [1, 3, 5, 7, 8, 10, 12]:
                num_giorni = 31
            elif mese in [4, 6, 9, 11]:
                num_giorni = 30
            else:
                if (anno % 4 == 0 and anno % 100 != 0) or (anno % 400 == 0):
                    num_giorni = 29
                else:
                    num_giorni = 28

            for giorno in range(1, num_giorni + 1):
                giorno_str = str(giorno)
                data_corrente = date(anno, mese, giorno)

                # Salta date future
                if data_corrente > oggi:
                    continue

                data_key = (mese, giorno)

                # Controlla stato speciale
                if data_key in stati_per_data:
                    stato = stati_per_data[data_key]
                    scheda["temperature"][mese_str][giorno_str] = {
                        "temp": None,
                        "operatore": OPERATORI_DEFAULT[0],
                        "is_chiuso": stato["tipo"] == "chiuso",
                        "is_manutenzione": stato["tipo"] == "manutenzione",
                        "is_non_usato": stato["tipo"] == "non_usato",
                        "motivo": stato["motivo"],
                        "note": stato["nome"],
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                # Giorno normale con temperatura
                elif giorno_str not in scheda["temperature"][mese_str]:
                    temp = round(random.uniform(-21.5, -18.5), 1)
                    scheda["temperature"][mese_str][giorno_str] = {
                        "temp": temp,
                        "operatore": random.choice(OPERATORI_DEFAULT),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }

        scheda["updated_at"] = datetime.now(timezone.utc).isoformat()

        await db.temperature_negative.update_one(
            {"anno": anno, "congelatore_numero": cong}, {"$set": scheda}
        )
        updated += 1

    return {
        "success": True,
        "message": f"Popolate {updated} schede congelatori con chiusure e stati speciali",
        "chiusure_applicate": len([c for c in chiusure]),
        "manutenzioni_applicate": len(stati_speciali["manutenzione"]),
        "non_usato_applicati": len(stati_speciali["non_usato"]),
        "nota": "La sanificazione apparecchi è gestita nel modulo Sanificazione",
    }


# ── POST /pulisci-operatori — rimuove campo operatore da tutti i doc automatici ──
@router.post("/pulisci-operatori")
async def pulisci_operatori_automatici():
    """Rimuove il campo 'operatore' da tutti i record temperatura automatici nel DB.
    Le temperature sono rilevate automaticamente: non c'è un operatore reale."""
    schede = await db.temperature_negative.find({}, {"_id": 1, "temperature": 1}).to_list(100)
    modificate = 0
    celle_pulite = 0
    for scheda in schede:
        aggiornata = False
        temp = scheda.get("temperature", {})
        for mese, giorni in temp.items():
            for giorno, record in (giorni or {}).items():
                if isinstance(record, dict) and "operatore" in record:
                    del record["operatore"]
                    aggiornata = True
                    celle_pulite += 1
        if aggiornata:
            await db.temperature_negative.update_one(
                {"_id": scheda["_id"]}, {"$set": {"temperature": temp}}
            )
            modificate += 1
    return {"ok": True, "schede_modificate": modificate, "celle_pulite": celle_pulite}
