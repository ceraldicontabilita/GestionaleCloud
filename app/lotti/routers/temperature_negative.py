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

from fastapi import APIRouter, Query, Depends, HTTPException
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
    pin: str = Query(default="", description="PIN personale di chi rileva: e' la firma"),
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
    # Chi firma lo decide il PIN, non la query: `operatore=` da solo e' una
    # stringa che chiunque puo' scrivere. Col PIN il nome arriva da HR ed e'
    # marcato `firma_verificata`; con un PIN sbagliato la rilevazione NON si
    # salva, perche' una firma falsa e' peggio di una registrazione mancante.
    from app.lotti.servizi.firma_operatore import firma_da_pin

    firma = await firma_da_pin(pin, operatore)
    record = {
        "temp": temperatura,
        "note": note,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "firma_verificata": firma["firma_verificata"],
    }
    if firma["operatore"]:
        record["operatore"] = firma["operatore"]
    if firma["operatore_id"]:
        record["operatore_id"] = firma["operatore_id"]

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
    raise HTTPException(
        status_code=410,
        detail="Bloccato: non e consentito generare temperature storiche o operatori fittizi.",
    )


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
