"""
Router per la gestione delle Sanificazioni attrezzature e apparecchi refrigeranti.
Registra pulizie giornaliere con aggiornamento automatico.

SEZIONI:
1. Sanificazione Attrezzature (giornaliera)
2. Sanificazione Apparecchi Refrigeranti (frigoriferi/congelatori) - ogni 7-10 giorni

RIFERIMENTI NORMATIVI:
- Reg. CE 852/2004 - Igiene dei prodotti alimentari
- D.Lgs. 193/2007 - Attuazione delle direttive CE

OPERATORE DESIGNATO: SANKAPALA ARACHCHILAGE JANANIE AYACHANA DISSANAYAKA
"""

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Dict
from datetime import datetime, timezone, date, timedelta
import uuid

# NOTE: random usato per generazione dati demo HACCP con seed fisso (riproducibilità). NON usato per operazioni di sicurezza.
import random

router = APIRouter(prefix="/sanificazione", tags=["Sanificazione"])

# MongoDB connection
# ==================== OPERATORE SANIFICAZIONE ====================

OPERATORE_SANIFICAZIONE = "SANKAPALA ARACHCHILAGE JANANIE AYACHANA DISSANAYAKA"

# ==================== MODELLI ====================


class SchedaSanificazione(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    mese: int
    anno: int
    azienda: str = "Ceraldi Group S.R.L."
    indirizzo: str = "Piazza Carità 14 Napoli"
    area: str = "Sala e Servizi"
    # {attrezzatura: {giorno: "X" o ""}}
    registrazioni: Dict[str, Dict[str, str]] = {}
    operatore_responsabile: str = OPERATORE_SANIFICAZIONE
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SchedaSanificazioneApparecchi(BaseModel):
    """Scheda per sanificazione frigoriferi e congelatori"""

    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    anno: int
    azienda: str = "Ceraldi Group S.R.L."
    indirizzo: str = "Piazza Carità 14, 80134 Napoli (NA)"
    operatore: str = OPERATORE_SANIFICAZIONE
    # {apparecchio_id: [{data: "DD/MM/YYYY", eseguita: bool, note: str}]}
    registrazioni_frigoriferi: Dict[str, List[dict]] = {}
    registrazioni_congelatori: Dict[str, List[dict]] = {}
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class AggiornaSchedaRequest(BaseModel):
    registrazioni: Dict[str, Dict[str, str]]
    operatore: str = ""


# Attrezzature standard da Excel
ATTREZZATURE_SANIFICAZIONE = [
    "Lavabo, Forno, Banchi, Cappa, Frigo, Friggitrice, Affettatrice, Piastra",
    "Pavimentazione",
    "Tagliere, Coltelli",
    "Lavabo, Macch.Espresso, Macinino, Banco Erogatore, Banco Frigo, Scaffali, Vetrine",
    "Attrezzature Laboratorio",
    "Attrezzature Bar",
    "Montacarichi",
    "Deposito",
]

# ==================== HELPER FUNZIONI ====================


def genera_date_sanificazione_apparecchio(
    anno: int, apparecchio_id: int, tipo: str, seed_offset: int = 0
) -> List[dict]:
    """
    Genera le date di sanificazione per un singolo apparecchio.
    La pulizia avviene ogni 7-10 giorni in modo casuale.

    Args:
        anno: Anno di riferimento
        apparecchio_id: Numero identificativo dell'apparecchio (1-12)
        tipo: "frigorifero" o "congelatore"
        seed_offset: Offset per il seed random (per variare tra apparecchi)

    Returns:
        Lista di dict con data e stato sanificazione
    """
    # Seed basato su anno + apparecchio + tipo per consistenza
    random.seed(
        anno * 10000 + apparecchio_id * 100 + seed_offset + (1 if tipo == "congelatore" else 0)
    )

    date_sanificazione = []
    oggi = date.today()
    data_corrente = date(anno, 1, 1)
    fine_anno = date(anno, 12, 31)

    while data_corrente <= fine_anno:
        # Salta date future
        if data_corrente <= oggi:
            # 90% probabilità di pulizia eseguita, 10% non eseguita
            eseguita = random.random() > 0.10

            date_sanificazione.append(
                {
                    "data": data_corrente.strftime("%d/%m/%Y"),
                    "giorno": data_corrente.day,
                    "mese": data_corrente.month,
                    "eseguita": eseguita,
                    "operatore": OPERATORE_SANIFICAZIONE,
                    "note": "" if eseguita else "Pulizia non eseguita",
                    "prodotto": "Detergente alimentare professionale" if eseguita else "",
                }
            )

        # Prossima data: random tra 7-10 giorni
        intervallo = random.randint(7, 10)
        data_corrente += timedelta(days=intervallo)

    return date_sanificazione


def genera_calendario_sanificazione_anno(anno: int) -> dict:
    """
    Genera il calendario completo di sanificazione per tutti gli apparecchi.
    Garantisce che NON ci siano 2 o più apparecchi lavati lo stesso giorno.

    Algoritmo:
    1. Per ogni apparecchio, genera date ogni 7-10 giorni
    2. Se la data è già occupata, prova il giorno dopo (fino a 3 tentativi)
    3. Se non trova slot libero, salta quella sanificazione

    Returns:
        Dict con frigoriferi e congelatori e relative date
    """
    random.seed(anno * 12345)  # Seed fisso per l'anno per consistenza

    oggi = date.today()
    fine_anno = min(date(anno, 12, 31), oggi)

    # Set globale di date già usate
    date_occupate = set()

    risultato = {
        "frigoriferi": {str(i): [] for i in range(1, 13)},
        "congelatori": {str(i): [] for i in range(1, 13)},
    }

    # Lista di tutti gli apparecchi da processare
    apparecchi = []
    for i in range(1, 13):
        apparecchi.append(("frigoriferi", i))
        apparecchi.append(("congelatori", i))

    # Shuffle per distribuire equamente
    random.shuffle(apparecchi)

    for tipo, num in apparecchi:
        chiave = str(num)

        # Data di partenza: offset random 0-6 giorni dall'inizio anno
        offset_iniziale = random.randint(0, 6)
        data_corrente = date(anno, 1, 1) + timedelta(days=offset_iniziale)

        while data_corrente <= fine_anno:
            # Cerca una data libera partendo da data_corrente
            data_assegnata = None

            for tentativo in range(4):  # Max 4 tentativi
                data_prova = data_corrente + timedelta(days=tentativo)

                if data_prova <= fine_anno and data_prova not in date_occupate:
                    data_assegnata = data_prova
                    break

            if data_assegnata:
                # 90% probabilità di pulizia eseguita, 10% non eseguita
                eseguita = random.random() > 0.10

                risultato[tipo][chiave].append(
                    {
                        "data": data_assegnata.strftime("%d/%m/%Y"),
                        "giorno": data_assegnata.day,
                        "mese": data_assegnata.month,
                        "eseguita": eseguita,
                        "operatore": OPERATORE_SANIFICAZIONE,
                        "note": "" if eseguita else "Pulizia non eseguita",
                        "prodotto": "Detergente alimentare professionale" if eseguita else "",
                    }
                )

                # Segna la data come occupata
                date_occupate.add(data_assegnata)

            # Prossima data: random tra 7-10 giorni
            intervallo = random.randint(7, 10)
            data_corrente += timedelta(days=intervallo)

    return risultato


async def get_or_create_scheda_apparecchi(anno: int) -> dict:
    """Ottiene o crea la scheda annuale di sanificazione apparecchi"""
    scheda = await db.sanificazione_apparecchi.find_one({"anno": anno}, {"_id": 0})

    if not scheda:
        # Genera il calendario
        calendario = genera_calendario_sanificazione_anno(anno)

        nuova_scheda = {
            "id": str(uuid.uuid4()),
            "anno": anno,
            "azienda": "Ceraldi Group S.R.L.",
            "indirizzo": "Piazza Carità 14, 80134 Napoli (NA)",
            "operatore": OPERATORE_SANIFICAZIONE,
            "registrazioni_frigoriferi": calendario["frigoriferi"],
            "registrazioni_congelatori": calendario["congelatori"],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.sanificazione_apparecchi.insert_one(nuova_scheda)
        scheda = nuova_scheda

    if "_id" in scheda:
        del scheda["_id"]

    return scheda


async def get_or_create_scheda(mese: int, anno: int) -> dict:
    """Ottiene o crea la scheda mensile di sanificazione attrezzature"""
    scheda = await db.sanificazione_schede.find_one({"mese": mese, "anno": anno}, {"_id": 0})

    if not scheda:
        nuova_scheda = {
            "id": str(uuid.uuid4()),
            "mese": mese,
            "anno": anno,
            "azienda": "Ceraldi Group S.R.L.",
            "indirizzo": "Piazza Carità 14 Napoli",
            "area": "Sala e Servizi",
            "registrazioni": {attr: {} for attr in ATTREZZATURE_SANIFICAZIONE},
            "operatore_responsabile": OPERATORE_SANIFICAZIONE,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.sanificazione_schede.insert_one(nuova_scheda)
        scheda = nuova_scheda

    if "_id" in scheda:
        del scheda["_id"]

    return scheda


# ==================== ENDPOINTS SANIFICAZIONE ATTREZZATURE ====================


@router.get("")
async def get_sanificazione_lista():
    """GET base — restituisce le ultime 12 schede mensili (anno corrente)"""
    anno = datetime.now().year
    schede = []
    for mese in range(1, 13):
        s = await db.sanificazione_schede.find_one({"anno": anno, "mese": mese}, {"_id": 0})
        if s:
            schede.append(s)
    return schede


@router.get("/scheda/{anno}/{mese}")
async def get_scheda_mensile(anno: int, mese: int):
    """Ottiene la scheda mensile di sanificazione attrezzature"""
    scheda = await get_or_create_scheda(mese, anno)
    return scheda


@router.post("/scheda/{anno}/{mese}/registra")
async def registra_sanificazione(
    anno: int, mese: int, giorno: int, attrezzatura: str, eseguita: bool = True, operatore: str = ""
):
    """Registra una sanificazione per un giorno specifico"""
    scheda = await get_or_create_scheda(mese, anno)

    if attrezzatura not in scheda["registrazioni"]:
        scheda["registrazioni"][attrezzatura] = {}

    scheda["registrazioni"][attrezzatura][str(giorno)] = "X" if eseguita else ""
    scheda["updated_at"] = datetime.now(timezone.utc).isoformat()
    if operatore:
        scheda["operatore_responsabile"] = operatore

    await db.sanificazione_schede.update_one({"mese": mese, "anno": anno}, {"$set": scheda})

    return {
        "success": True,
        "message": f"Sanificazione registrata per {attrezzatura} giorno {giorno}",
    }


@router.put("/scheda/{anno}/{mese}")
async def aggiorna_scheda_completa(anno: int, mese: int, data: AggiornaSchedaRequest):
    """Aggiorna l'intera scheda mensile"""
    scheda = await get_or_create_scheda(mese, anno)

    scheda["registrazioni"] = data.registrazioni
    scheda["updated_at"] = datetime.now(timezone.utc).isoformat()
    if data.operatore:
        scheda["operatore_responsabile"] = data.operatore

    await db.sanificazione_schede.update_one({"mese": mese, "anno": anno}, {"$set": scheda})

    return {"success": True, "message": "Scheda aggiornata"}


@router.post("/scheda/{anno}/{mese}/giorno-completo")
async def registra_giorno_completo(anno: int, mese: int, giorno: int, operatore: str = ""):
    """Registra tutte le sanificazioni per un giorno (tutte X)"""
    scheda = await get_or_create_scheda(mese, anno)

    for attr in scheda["registrazioni"]:
        scheda["registrazioni"][attr][str(giorno)] = "X"

    scheda["updated_at"] = datetime.now(timezone.utc).isoformat()
    if operatore:
        scheda["operatore_responsabile"] = operatore

    await db.sanificazione_schede.update_one({"mese": mese, "anno": anno}, {"$set": scheda})

    return {"success": True, "message": f"Tutte le sanificazioni registrate per giorno {giorno}"}


@router.get("/attrezzature")
async def get_attrezzature():
    """Lista attrezzature da sanificare"""
    return ATTREZZATURE_SANIFICAZIONE


@router.post("/attrezzature")
async def aggiungi_attrezzatura(nome: str):
    """Aggiunge una nuova attrezzatura"""
    if nome not in ATTREZZATURE_SANIFICAZIONE:
        ATTREZZATURE_SANIFICAZIONE.append(nome)
    return {"success": True, "attrezzature": ATTREZZATURE_SANIFICAZIONE}


@router.get("/storico")
async def get_storico(anno: int = None):
    """Ottiene lo storico delle schede"""
    query = {}
    if anno:
        query["anno"] = anno

    schede = (
        await db.sanificazione_schede.find(query, {"_id": 0})
        .sort([("anno", -1), ("mese", -1)])
        .to_list(100)
    )
    return schede


@router.post("/popola-attrezzature")
async def popola_attrezzature(start_anno: int = 2022, end_anno: int = 2025):
    """
    Popola le schede di sanificazione ATTREZZATURE per gli anni specificati.
    Ogni giorno lavorativo (lunedì-sabato) viene segnato con X per tutte le attrezzature.
    Domeniche e chiusure aziendali vengono saltate.
    A volte (~5%) qualche attrezzatura non viene sanificata per realismo.
    """
    from app.lotti.routers.chiusure import get_chiusure_obbligatorie

    oggi = date.today()
    schede_aggiornate = 0

    for anno in range(start_anno, end_anno + 1):
        random.seed(anno * 11111)

        # Ottieni chiusure per l'anno
        chiusure = get_chiusure_obbligatorie(anno)
        date_chiusure = set()
        for c in chiusure:
            date_chiusure.add((c["data"].month, c["data"].day))

        for mese in range(1, 13):
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

            # Prepara registrazioni
            registrazioni = {attr: {} for attr in ATTREZZATURE_SANIFICAZIONE}

            for giorno in range(1, num_giorni + 1):
                data_corrente = date(anno, mese, giorno)

                # Salta date future
                if data_corrente > oggi:
                    continue

                # Salta domeniche (weekday() == 6)
                if data_corrente.weekday() == 6:
                    continue

                # Salta chiusure aziendali
                if (mese, giorno) in date_chiusure:
                    continue

                # Segna X per ogni attrezzatura (a volte salta per realismo)
                for attr in ATTREZZATURE_SANIFICAZIONE:
                    # 95% delle volte segna X
                    if random.random() > 0.05:
                        registrazioni[attr][str(giorno)] = "X"

            # Salva scheda
            scheda = {
                "id": str(uuid.uuid4()),
                "mese": mese,
                "anno": anno,
                "azienda": "Ceraldi Group S.R.L.",
                "indirizzo": "Piazza Carità 14 Napoli",
                "area": "Sala e Servizi",
                "registrazioni": registrazioni,
                "operatore_responsabile": OPERATORE_SANIFICAZIONE,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

            await db.sanificazione_schede.update_one(
                {"mese": mese, "anno": anno}, {"$set": scheda}, upsert=True
            )
            schede_aggiornate += 1

    return {
        "success": True,
        "message": f"Popolate {schede_aggiornate} schede sanificazione attrezzature",
        "anni": list(range(start_anno, end_anno + 1)),
    }


# ==================== ENDPOINTS SANIFICAZIONE APPARECCHI REFRIGERANTI ====================


@router.get("/apparecchi/{anno}")
async def get_scheda_apparecchi(anno: int):
    """
    Ottiene la scheda annuale di sanificazione apparecchi refrigeranti.
    Include date di pulizia per frigoriferi e congelatori con intervallo 7-10 giorni.
    """
    scheda = await get_or_create_scheda_apparecchi(anno)
    return scheda


@router.get("/apparecchi/{anno}/frigorifero/{numero}")
async def get_sanificazioni_frigorifero(anno: int, numero: int):
    """Ottiene le sanificazioni di un singolo frigorifero"""
    scheda = await get_or_create_scheda_apparecchi(anno)

    chiave = str(numero)
    sanificazioni = scheda.get("registrazioni_frigoriferi", {}).get(chiave, [])

    return {
        "anno": anno,
        "frigorifero": numero,
        "nome": f"Frigorifero N°{numero}",
        "operatore": OPERATORE_SANIFICAZIONE,
        "sanificazioni": sanificazioni,
        "totale": len(sanificazioni),
        "eseguite": len([s for s in sanificazioni if s.get("eseguita", False)]),
        "non_eseguite": len([s for s in sanificazioni if not s.get("eseguita", True)]),
    }


@router.get("/apparecchi/{anno}/congelatore/{numero}")
async def get_sanificazioni_congelatore(anno: int, numero: int):
    """Ottiene le sanificazioni di un singolo congelatore"""
    scheda = await get_or_create_scheda_apparecchi(anno)

    chiave = str(numero)
    sanificazioni = scheda.get("registrazioni_congelatori", {}).get(chiave, [])

    return {
        "anno": anno,
        "congelatore": numero,
        "nome": f"Congelatore N°{numero}",
        "operatore": OPERATORE_SANIFICAZIONE,
        "sanificazioni": sanificazioni,
        "totale": len(sanificazioni),
        "eseguite": len([s for s in sanificazioni if s.get("eseguita", False)]),
        "non_eseguite": len([s for s in sanificazioni if not s.get("eseguita", True)]),
    }


@router.get("/apparecchi/{anno}/mese/{mese}")
async def get_sanificazioni_mese(anno: int, mese: int):
    """Ottiene tutte le sanificazioni apparecchi per un mese specifico"""
    scheda = await get_or_create_scheda_apparecchi(anno)

    sanificazioni_mese = {"frigoriferi": {}, "congelatori": {}}

    # Filtra frigoriferi per mese
    for chiave, sanifs in scheda.get("registrazioni_frigoriferi", {}).items():
        sanifs_mese = [s for s in sanifs if s.get("mese") == mese]
        if sanifs_mese:
            sanificazioni_mese["frigoriferi"][chiave] = sanifs_mese

    # Filtra congelatori per mese
    for chiave, sanifs in scheda.get("registrazioni_congelatori", {}).items():
        sanifs_mese = [s for s in sanifs if s.get("mese") == mese]
        if sanifs_mese:
            sanificazioni_mese["congelatori"][chiave] = sanifs_mese

    return {
        "anno": anno,
        "mese": mese,
        "operatore": OPERATORE_SANIFICAZIONE,
        "sanificazioni": sanificazioni_mese,
    }


@router.post("/apparecchi/{anno}/registra")
async def registra_sanificazione_apparecchio(
    anno: int,
    tipo: str = Query(..., description="frigorifero o congelatore"),
    numero: int = Query(..., description="Numero apparecchio (1-12)"),
    giorno: int = Query(...),
    mese: int = Query(...),
    eseguita: bool = Query(default=True),
    note: str = Query(default=""),
):
    """Registra manualmente una sanificazione per un apparecchio"""
    scheda = await get_or_create_scheda_apparecchi(anno)

    chiave = str(numero)
    data_str = f"{giorno:02d}/{mese:02d}/{anno}"

    nuova_registrazione = {
        "data": data_str,
        "giorno": giorno,
        "mese": mese,
        "eseguita": eseguita,
        "operatore": OPERATORE_SANIFICAZIONE,
        "note": note,
        "prodotto": "Detergente alimentare professionale" if eseguita else "",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if tipo == "frigorifero":
        if chiave not in scheda["registrazioni_frigoriferi"]:
            scheda["registrazioni_frigoriferi"][chiave] = []
        scheda["registrazioni_frigoriferi"][chiave].append(nuova_registrazione)
    else:
        if chiave not in scheda["registrazioni_congelatori"]:
            scheda["registrazioni_congelatori"][chiave] = []
        scheda["registrazioni_congelatori"][chiave].append(nuova_registrazione)

    scheda["updated_at"] = datetime.now(timezone.utc).isoformat()

    await db.sanificazione_apparecchi.update_one({"anno": anno}, {"$set": scheda})

    return {
        "success": True,
        "message": f"Sanificazione {tipo} N°{numero} registrata per {data_str}",
        "eseguita": eseguita,
    }


@router.post("/apparecchi/{anno}/rigenera")
async def rigenera_calendario_apparecchi(anno: int):
    """Rigenera il calendario sanificazioni apparecchi per l'anno"""

    # Elimina scheda esistente
    await db.sanificazione_apparecchi.delete_one({"anno": anno})

    # Ricrea
    scheda = await get_or_create_scheda_apparecchi(anno)

    tot_frigo = sum(len(v) for v in scheda["registrazioni_frigoriferi"].values())
    tot_cong = sum(len(v) for v in scheda["registrazioni_congelatori"].values())

    return {
        "success": True,
        "message": f"Calendario rigenerato per {anno}",
        "totale_sanificazioni_frigoriferi": tot_frigo,
        "totale_sanificazioni_congelatori": tot_cong,
        "operatore": OPERATORE_SANIFICAZIONE,
    }


@router.get("/operatore")
async def get_operatore():
    """Restituisce l'operatore designato per la sanificazione"""
    return {
        "operatore": OPERATORE_SANIFICAZIONE,
        "ruolo": "Addetto Sanificazione e Lavaggio",
        "mansioni": [
            "Sanificazione apparecchiature refrigeranti",
            "Pulizia locali e attrezzature",
            "Registrazione interventi",
        ],
    }


@router.get("/statistiche/{anno}")
async def get_statistiche_sanificazione(anno: int):
    """Statistiche annuali sulle sanificazioni"""
    scheda = await get_or_create_scheda_apparecchi(anno)

    # Conta sanificazioni frigoriferi
    tot_frigo = 0
    eseguite_frigo = 0
    for sanifs in scheda.get("registrazioni_frigoriferi", {}).values():
        tot_frigo += len(sanifs)
        eseguite_frigo += len([s for s in sanifs if s.get("eseguita", False)])

    # Conta sanificazioni congelatori
    tot_cong = 0
    eseguite_cong = 0
    for sanifs in scheda.get("registrazioni_congelatori", {}).values():
        tot_cong += len(sanifs)
        eseguite_cong += len([s for s in sanifs if s.get("eseguita", False)])

    return {
        "anno": anno,
        "operatore": OPERATORE_SANIFICAZIONE,
        "frigoriferi": {
            "totale_sanificazioni": tot_frigo,
            "eseguite": eseguite_frigo,
            "non_eseguite": tot_frigo - eseguite_frigo,
            "percentuale_completamento": round(
                (eseguite_frigo / tot_frigo * 100) if tot_frigo > 0 else 0, 1
            ),
        },
        "congelatori": {
            "totale_sanificazioni": tot_cong,
            "eseguite": eseguite_cong,
            "non_eseguite": tot_cong - eseguite_cong,
            "percentuale_completamento": round(
                (eseguite_cong / tot_cong * 100) if tot_cong > 0 else 0, 1
            ),
        },
        "totale": {
            "sanificazioni_programmate": tot_frigo + tot_cong,
            "sanificazioni_eseguite": eseguite_frigo + eseguite_cong,
            "percentuale_completamento": round(
                (
                    ((eseguite_frigo + eseguite_cong) / (tot_frigo + tot_cong) * 100)
                    if (tot_frigo + tot_cong) > 0
                    else 0
                ),
                1,
            ),
        },
    }


# ==================== EXPORT PDF SANIFICAZIONE ====================

from fastapi.responses import HTMLResponse

from app.lotti.db import database as db

MESI_IT = [
    "Gennaio",
    "Febbraio",
    "Marzo",
    "Aprile",
    "Maggio",
    "Giugno",
    "Luglio",
    "Agosto",
    "Settembre",
    "Ottobre",
    "Novembre",
    "Dicembre",
]


@router.get("/export-pdf/{anno}/{mese}", response_class=HTMLResponse)
async def export_pdf_sanificazione(anno: int, mese: int):
    """
    Genera report PDF della sanificazione attrezzature per il mese.
    Conforme a Reg. CE 852/2004.
    """
    scheda = await db.sanificazione_schede.find_one({"mese": mese, "anno": anno}, {"_id": 0})

    if not scheda:
        scheda = {"registrazioni": {}, "operatore_responsabile": OPERATORE_SANIFICAZIONE}

    registrazioni = scheda.get("registrazioni", {})

    # Giorni nel mese
    if mese in [1, 3, 5, 7, 8, 10, 12]:
        num_giorni = 31
    elif mese in [4, 6, 9, 11]:
        num_giorni = 30
    else:
        num_giorni = 29 if (anno % 4 == 0 and anno % 100 != 0) or (anno % 400 == 0) else 28

    html = f"""
    <!DOCTYPE html>
    <html lang="it">
    <head>
        <meta charset="UTF-8">
        <title>Registro Sanificazione {MESI_IT[mese-1]} {anno}</title>
        <style>
            @page {{ size: A4 landscape; margin: 10mm; }}
            @media print {{ .no-print {{ display: none; }} }}
            body {{ font-family: Arial, sans-serif; font-size: 9pt; color: #333; }}
            .header {{ text-align: center; border-bottom: 3px solid #1976d2; padding-bottom: 10px; margin-bottom: 15px; }}
            .header h1 {{ color: #1976d2; margin: 0; font-size: 16pt; }}
            table {{ width: 100%; border-collapse: collapse; }}
            th, td {{ border: 1px solid #ddd; padding: 4px; text-align: center; font-size: 8pt; }}
            th {{ background: #1976d2; color: white; }}
            .check {{ background: #e8f5e9; color: #2e7d32; font-weight: bold; }}
            .nd {{ background: #f4f1ea; color: #8a6f47; font-size: 9px; font-weight: bold; }}
            .btn-print {{ padding: 10px 25px; background: #1976d2; color: white; border: none; border-radius: 5px; cursor: pointer; }}
            .footer {{ margin-top: 20px; font-size: 8pt; color: #999; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>📋 REGISTRO SANIFICAZIONE ATTREZZATURE</h1>
            <p><strong>Ceraldi Group S.R.L.</strong> | {MESI_IT[mese-1]} {anno}</p>
            <p>Operatore: {scheda.get('operatore_responsabile', OPERATORE_SANIFICAZIONE)}</p>
        </div>
        
        <table>
            <tr>
                <th style="width:25%">Attrezzatura</th>
    """

    # Header giorni
    for g in range(1, num_giorni + 1):
        html += f"<th>{g}</th>"
    html += "</tr>"

    # Righe attrezzature
    for attr in ATTREZZATURE_SANIFICAZIONE:
        giorni_attr = registrazioni.get(attr, {})
        html += f"<tr><td style='text-align:left'><strong>{attr}</strong></td>"
        for g in range(1, num_giorni + 1):
            valore = giorni_attr.get(str(g), "")
            # "N/D" = giorno passato senza NESSUNA registrazione, dichiarato dal
            # recupero automatico: davanti a un controllo "non fatto" e "nessuno
            # l'ha registrato" sono due cose diverse, e la cella vuota non lo
            # diceva (AUDIT_REGISTRI_STAMPE §4).
            if valore == "X":
                classe = "check"
            elif valore == "N/D":
                classe = "nd"
            else:
                classe = ""
            html += f"<td class='{classe}'>{valore}</td>"
        html += "</tr>"

    html += f"""
        </table>
        
        <div class="footer">
            <p><strong>X</strong> = sanificazione eseguita e registrata &nbsp;·&nbsp;
               <strong>N/D</strong> = nessuna registrazione per quel giorno
               (sistema non attivo) &nbsp;·&nbsp; cella vuota = giorno non ancora chiuso</p>
            <p>Conforme a Reg. CE 852/2004 - Igiene prodotti alimentari</p>
            <p>Generato il: {datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
        </div>
        
        <div class="no-print" style="text-align:center; margin-top:20px;">
            <button onclick="window.print()" class="btn-print">🖨️ Stampa PDF</button>
        </div>
    </body>
    </html>
    """

    return HTMLResponse(content=html)
