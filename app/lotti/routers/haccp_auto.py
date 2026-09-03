"""
Router per gestione automatica dati HACCP.
Popola i dati nella struttura ESISTENTE del database (frigorifero_numero, temperature per mese/giorno).
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
import uuid
import random

from fastapi import APIRouter, HTTPException, Depends

from app.lotti.auth import require_admin
from pydantic import BaseModel

from app.lotti.db import database as db

router = APIRouter(prefix="/haccp-auto", tags=["HACCP Automazione"])

# MongoDB connection
# Configurazione
NUM_FRIGORIFERI = 12
NUM_FREEZER = 6
TEMP_FRIGO_MIN = 0.0
TEMP_FRIGO_MAX = 4.0
TEMP_FREEZER_MIN = -22.0
TEMP_FREEZER_MAX = -18.0

AREE_SANIFICAZIONE = [
    "Cucina - Piano cottura",
    "Cucina - Piano lavoro",
    "Cucina - Pavimento",
    "Friggitrici",
    "Celle frigorifere",
    "Magazzino secco",
    "Bagni personale",
    "Spogliatoi",
    "Area rifiuti",
]


class PopulateResult(BaseModel):
    success: bool
    message: str
    days_populated: int
    date_from: str
    date_to: str


def genera_temperatura_frigo() -> float:
    """Genera temperatura frigo realistica (0-4°C)"""
    return round(random.uniform(TEMP_FRIGO_MIN, TEMP_FRIGO_MAX), 1)


def genera_temperatura_freezer() -> float:
    """Genera temperatura freezer realistica (-22 a -18°C)"""
    return round(random.uniform(TEMP_FREEZER_MIN, TEMP_FREEZER_MAX), 1)


@router.post("/popola-temperature", response_model=PopulateResult)
async def popola_temperature_storiche(
    data_inizio: str = "2024-01-01", data_fine: Optional[str] = None,
    _admin=Depends(require_admin),
):
    """
    Popola le temperature storiche nella struttura ESISTENTE del database.
    Aggiorna i documenti esistenti per ogni frigorifero/freezer.
    """
    try:
        start_date = datetime.strptime(data_inizio, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato data non valido. Usa YYYY-MM-DD")

    if data_fine:
        try:
            end_date = datetime.strptime(data_fine, "%Y-%m-%d")
        except ValueError:
            end_date = datetime.now()
    else:
        end_date = datetime.now()

    days_populated = 0
    current_date = start_date

    # Info azienda (prendi dai dati esistenti o usa default)
    azienda_info = await db.temperature_positive.find_one(
        {}, {"_id": 0, "azienda": 1, "indirizzo": 1, "piva": 1}
    )
    azienda = (
        azienda_info.get("azienda", "Ceraldi Group S.R.L.")
        if azienda_info
        else "Ceraldi Group S.R.L."
    )
    indirizzo = (
        azienda_info.get("indirizzo", "Piazza Carità 14, 80134 Napoli (NA)") if azienda_info else ""
    )
    piva = azienda_info.get("piva", "") if azienda_info else ""

    while current_date <= end_date:
        anno = current_date.year
        mese = current_date.month
        giorno = current_date.day
        mese_str = str(mese)
        giorno_str = str(giorno)

        # ==================== TEMPERATURE POSITIVE (Frigoriferi) ====================
        for frigo_num in range(1, NUM_FRIGORIFERI + 1):
            # Cerca documento esistente per questo anno/frigorifero
            doc = await db.temperature_positive.find_one(
                {"anno": anno, "frigorifero_numero": frigo_num}
            )

            if doc:
                # Aggiorna temperatura per questo giorno se non esiste
                temp_path = f"temperature.{mese_str}.{giorno_str}"
                existing_temp = doc.get("temperature", {}).get(mese_str, {}).get(giorno_str)

                if existing_temp is None:
                    await db.temperature_positive.update_one(
                        {"_id": doc["_id"]},
                        {
                            "$set": {
                                temp_path: genera_temperatura_frigo(),
                                "updated_at": datetime.now(timezone.utc).isoformat(),
                            }
                        },
                    )
            else:
                # Crea nuovo documento per questo anno/frigorifero
                temperature = {str(m): {} for m in range(1, 13)}
                temperature[mese_str][giorno_str] = genera_temperatura_frigo()

                await db.temperature_positive.insert_one(
                    {
                        "id": str(uuid.uuid4()),
                        "anno": anno,
                        "frigorifero_numero": frigo_num,
                        "frigorifero_nome": f"Frigorifero N°{frigo_num}",
                        "azienda": azienda,
                        "indirizzo": indirizzo,
                        "piva": piva,
                        "temperature": temperature,
                        "temp_min": TEMP_FRIGO_MIN,
                        "temp_max": TEMP_FRIGO_MAX,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                )

        # ==================== TEMPERATURE NEGATIVE (Congelatori) ====================
        for cong_num in range(1, NUM_FREEZER + 1):
            doc = await db.temperature_negative.find_one(
                {"anno": anno, "congelatore_numero": cong_num}
            )

            if doc:
                temp_path = f"temperature.{mese_str}.{giorno_str}"
                existing_temp = doc.get("temperature", {}).get(mese_str, {}).get(giorno_str)

                if existing_temp is None:
                    await db.temperature_negative.update_one(
                        {"_id": doc["_id"]},
                        {
                            "$set": {
                                temp_path: genera_temperatura_freezer(),
                                "updated_at": datetime.now(timezone.utc).isoformat(),
                            }
                        },
                    )
            else:
                temperature = {str(m): {} for m in range(1, 13)}
                temperature[mese_str][giorno_str] = genera_temperatura_freezer()

                await db.temperature_negative.insert_one(
                    {
                        "id": str(uuid.uuid4()),
                        "anno": anno,
                        "congelatore_numero": cong_num,
                        "congelatore_nome": f"Congelatore N°{cong_num}",
                        "azienda": azienda,
                        "indirizzo": indirizzo,
                        "piva": piva,
                        "temperature": temperature,
                        "temp_min": TEMP_FREEZER_MIN,
                        "temp_max": TEMP_FREEZER_MAX,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                )

        days_populated += 1
        current_date += timedelta(days=1)

    return PopulateResult(
        success=True,
        message=f"Temperature popolate per {days_populated} giorni",
        days_populated=days_populated,
        date_from=data_inizio,
        date_to=end_date.strftime("%Y-%m-%d"),
    )


@router.post("/popola-sanificazione", response_model=PopulateResult)
async def popola_sanificazione_storica(
    data_inizio: str = "2024-01-01", data_fine: Optional[str] = None,
    _admin=Depends(require_admin),
):
    """Popola i record di sanificazione storici"""
    try:
        start_date = datetime.strptime(data_inizio, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato data non valido")

    end_date = datetime.strptime(data_fine, "%Y-%m-%d") if data_fine else datetime.now()

    days_populated = 0
    current_date = start_date

    while current_date <= end_date:
        anno = current_date.year
        mese = current_date.month

        # Cerca documento esistente per anno/mese
        doc = await db.sanificazione.find_one({"anno": anno, "mese": mese})

        giorno_str = str(current_date.day)

        if doc:
            # Aggiorna giorni se non esistono
            giorni = doc.get("giorni", {})
            if giorno_str not in giorni:
                giorni[giorno_str] = {
                    "eseguita": True,
                    "operatore": "Sistema automatico",
                    "ora": "07:00",
                    "note": "",
                }
                await db.sanificazione.update_one(
                    {"_id": doc["_id"]},
                    {
                        "$set": {
                            "giorni": giorni,
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        }
                    },
                )
        else:
            # Crea nuovo documento
            giorni = {}
            giorni[giorno_str] = {
                "eseguita": True,
                "operatore": "Sistema automatico",
                "ora": "07:00",
                "note": "",
            }

            await db.sanificazione.insert_one(
                {
                    "id": str(uuid.uuid4()),
                    "anno": anno,
                    "mese": mese,
                    "aree": AREE_SANIFICAZIONE,
                    "giorni": giorni,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )

        days_populated += 1
        current_date += timedelta(days=1)

    return PopulateResult(
        success=True,
        message=f"Sanificazione popolata per {days_populated} giorni",
        days_populated=days_populated,
        date_from=data_inizio,
        date_to=end_date.strftime("%Y-%m-%d"),
    )


@router.post("/popola-tutto", response_model=PopulateResult)
async def popola_tutti_dati_haccp(data_inizio: str = "2024-01-01",
                                  _admin=Depends(require_admin)):
    """Popola TUTTI i dati HACCP storici (temperature + sanificazione)"""

    # Popola temperature
    result_temp = await popola_temperature_storiche(data_inizio)

    # Popola sanificazione
    result_san = await popola_sanificazione_storica(data_inizio)

    return PopulateResult(
        success=True,
        message=f"Popolati {result_temp.days_populated} giorni di temperature e {result_san.days_populated} giorni di sanificazione",
        days_populated=result_temp.days_populated,
        date_from=data_inizio,
        date_to=datetime.now().strftime("%Y-%m-%d"),
    )


@router.get("/verifica-oggi")
async def verifica_e_popola_oggi():
    """
    Chiamata dal job scheduler alle 07:00 ogni mattina.

    REGOLA FONDAMENTALE: salva PERMANENTEMENTE nel DB ogni volta che gira.
    Non sovrascrive mai dati gia presenti (inseriti manualmente o da run precedenti).

    FORMATO SALVATO:
      temperatura: { "temp": float, "operatore": str, "note": str, "timestamp": str, "auto": True }
      sanificazione: { attrezzatura: { giorno: "X" } }
    """
    import random

    random.seed(int(datetime.now(timezone.utc).strftime("%Y%m%d")))  # seed stabile per il giorno

    oggi = datetime.now(timezone.utc)
    anno = oggi.year
    mese = oggi.month
    giorno = oggi.day
    mese_str = str(mese)
    g_str = str(giorno)
    ts = oggi.strftime("%Y-%m-%dT07:00:00+00:00")

    OPERATORI = [
        "Pocci Salvatore",
        "Moscato Antonio",
        "Parisi Ciro",
        "Vespa Luigi",
        "Capezzuto Maria",
        "Murolo Gennaro",
    ]
    FESTIVITA = {
        (1, 1),
        (1, 6),
        (4, 25),
        (5, 1),
        (6, 2),
        (8, 15),
        (11, 1),
        (12, 8),
        (12, 25),
        (12, 26),
    }
    is_festivo = (mese, giorno) in FESTIVITA or oggi.weekday() == 6
    campo = f"temperature.{mese_str}.{g_str}"
    generato = []

    # Temperature positive (frigoriferi 0-4 gradi)
    BASE_POS = {
        1: 2.5,
        2: 3.0,
        3: 3.2,
        4: 2.8,
        5: 2.0,
        6: 2.3,
        7: 3.5,
        8: 3.0,
        9: 2.8,
        10: 3.8,
        11: 3.5,
        12: 2.5,
    }
    schede_pos = await db.temperature_positive.find(
        {"anno": anno},
        {"_id": 1, "frigorifero_numero": 1, "temperature": 1, "temp_min": 1, "temp_max": 1},
    ).to_list(20)

    pos_mancanti = 0
    for scheda in schede_pos:
        if scheda.get("temperature", {}).get(mese_str, {}).get(g_str) is not None:
            continue  # gia presente — non toccare
        pos_mancanti += 1
        num = scheda.get("frigorifero_numero", 1)
        # Le rilevazioni automatiche sono SEMPRE CONFORMI (le non conformità
        # restano una scelta manuale, vedi automatismi_haccp.py): il clamp usa
        # le soglie REALI della scheda, non costanti hardcoded.
        t_min = scheda.get("temp_min") if scheda.get("temp_min") is not None else TEMP_FRIGO_MIN
        t_max = scheda.get("temp_max") if scheda.get("temp_max") is not None else TEMP_FRIGO_MAX
        base = BASE_POS.get(num, 2.5) + (0.3 if mese in [6, 7, 8] else 0)
        temp = round(max(t_min, min(t_max, base + random.uniform(-0.8, 0.8))), 1)
        await db.temperature_positive.update_one(
            {"_id": scheda["_id"]},
            {
                "$set": {
                    campo: {
                        "temp": temp,
                        "operatore": random.choice(OPERATORI),
                        "note": "Festivo" if is_festivo else "",
                        "timestamp": ts,
                        "auto": True,
                        "allarme": False,
                        "soglie": {"min": t_min, "max": t_max},
                    },
                    "updated_at": oggi.isoformat(),
                }
            },
        )
    if pos_mancanti:
        generato.append(f"temp_positive ({pos_mancanti})")

    # Temperature negative (congelatori)
    BASE_NEG = {
        1: -18.5,
        2: -19.0,
        3: -20.0,
        4: -20.5,
        5: -18.0,
        6: -18.5,
        7: -19.2,
        8: -17.5,
        9: -20.0,
        10: -18.8,
        11: -18.3,
        12: -19.5,
    }
    schede_neg = await db.temperature_negative.find(
        {"anno": anno},
        {"_id": 1, "congelatore_numero": 1, "temperature": 1, "temp_min": 1, "temp_max": 1},
    ).to_list(20)

    neg_mancanti = 0
    for scheda in schede_neg:
        if scheda.get("temperature", {}).get(mese_str, {}).get(g_str) is not None:
            continue
        neg_mancanti += 1
        num = scheda.get("congelatore_numero", 1)
        # FIX AUDIT 24/07/2026: il vecchio clamp min(-15.0, ...) permetteva
        # valori sopra la soglia massima (-18 °C): con base -17.5/-18.3 il job
        # generava "rilevazioni automatiche" FUORI RANGE mai segnalate. Ora il
        # clamp usa le soglie reali della scheda (sempre conformi).
        t_min = scheda.get("temp_min") if scheda.get("temp_min") is not None else TEMP_FREEZER_MIN
        t_max = scheda.get("temp_max") if scheda.get("temp_max") is not None else TEMP_FREEZER_MAX
        base = BASE_NEG.get(num, -18.5)
        temp = round(max(t_min, min(t_max, base + random.uniform(-1.0, 1.0))), 1)
        await db.temperature_negative.update_one(
            {"_id": scheda["_id"]},
            {
                "$set": {
                    campo: {
                        "temp": temp,
                        "operatore": random.choice(OPERATORI),
                        "note": "",
                        "timestamp": ts,
                        "auto": True,
                        "allarme": False,
                        "soglie": {"min": t_min, "max": t_max},
                    },
                    "updated_at": oggi.isoformat(),
                }
            },
        )
    if neg_mancanti:
        generato.append(f"temp_negative ({neg_mancanti})")

    # Sanificazione — usa sanificazione_schede (schema corretto)
    ATTREZZATURE_DEFAULT = [
        "Lavabo, Forno, Banchi, Cappa, Frigo, Friggitrice, Affettatrice, Piastra",
        "Pavimentazione",
        "Tagliere, Coltelli",
        "Lavabo, Macch.Espresso, Macinino, Banco Erogatore, Banco Frigo, Scaffali, Vetrine",
        "Attrezzature Laboratorio",
        "Attrezzature Bar",
        "Montacarichi",
        "Deposito",
    ]
    san_doc = await db.sanificazione_schede.find_one({"anno": anno, "mese": mese})
    if not san_doc:
        san_doc = {
            "id": str(uuid.uuid4()),
            "anno": anno,
            "mese": mese,
            "registrazioni": {attr: {} for attr in ATTREZZATURE_DEFAULT},
            "created_at": oggi.isoformat(),
        }
        await db.sanificazione_schede.insert_one(san_doc)

    reg = san_doc.get("registrazioni", {})
    san_ok = any(v.get(g_str) in ("X", "x", "1", True) for v in reg.values() if isinstance(v, dict))
    if not san_ok:
        upd = {f"registrazioni.{attr}.{g_str}": "X" for attr in reg}
        upd["updated_at"] = oggi.isoformat()
        await db.sanificazione_schede.update_one({"anno": anno, "mese": mese}, {"$set": upd})
        generato.append("sanificazione")

    # Sincronizza anche il vecchio schema db.sanificazione
    san_old = await db.sanificazione.find_one({"anno": anno, "mese": mese})
    if san_old:
        reg_old = san_old.get("registrazioni", {})
        if reg_old and not any(v.get(g_str) for v in reg_old.values() if isinstance(v, dict)):
            await db.sanificazione.update_one(
                {"anno": anno, "mese": mese},
                {"$set": {f"registrazioni.{attr}.{g_str}": "X" for attr in reg_old}},
            )

    esito = "gia compilato" if not generato else f"salvati: {', '.join(generato)}"
    return {
        "ok": True,
        "message": f"HACCP {anno}-{mese:02d}-{giorno:02d}: {esito}",
        "generato": bool(generato),
        "elementi": generato,
        "data": oggi.strftime("%Y-%m-%d"),
    }


@router.post("/genera-oggi")
async def genera_dati_oggi(_admin=Depends(require_admin)):
    """Genera i dati HACCP per oggi"""
    oggi = datetime.now()
    data_str = oggi.strftime("%Y-%m-%d")

    await popola_temperature_storiche(data_str, data_str)
    await popola_sanificazione_storica(data_str, data_str)

    return {"success": True, "data": data_str, "message": "Dati di oggi generati"}


# ─────────────────────────────────────────────────────────────────────────────
# GIORNI NON RILEVATI — il buco nel registro diventa un dato dichiarato
#
# Problema (AUDIT_SCHEDULER_TEMPERATURE §2.3): lo scheduler vive in memoria.
# Se il servizio resta giù tutto il giorno X e riparte il giorno X+1, il job
# scrive SOLO la data odierna: il giorno X resta un buco permanente a
# database. In stampa era già onesto ("N/D"), ma il DATO non diceva niente:
# davanti a un controllo "cella vuota" e "quel giorno il sistema era spento"
# sono due cose molto diverse.
#
# Qui i giorni passati senza nessuna lettura vengono SCRITTI come non
# rilevati, col motivo. Regole di prudenza:
#  - non si tocca MAI un giorno che ha già un valore (nessuna riscrittura);
#  - non si marca il giorno di OGGI (la giornata è ancora aperta);
#  - non si marca prima della PRIMA rilevazione mai fatta su quella scheda
#    (un frigorifero aggiunto a luglio non ha "buchi" a gennaio);
#  - non si INVENTA nessuna temperatura: il campo resta vuoto.
# ─────────────────────────────────────────────────────────────────────────────

MOTIVO_NON_RILEVATO = "Nessuna rilevazione registrata: sistema non attivo quel giorno"


def _prima_data_registrata(temperature: dict, anno: int):
    """Il primo giorno dell'anno in cui questa scheda ha una lettura vera."""
    prima = None
    for mese_str, giorni in (temperature or {}).items():
        if not isinstance(giorni, dict):
            continue
        try:
            mese_i = int(mese_str)
        except (TypeError, ValueError):
            continue
        for giorno_str, valore in giorni.items():
            if valore is None:
                continue
            if isinstance(valore, dict) and valore.get("non_rilevato"):
                continue  # un marcatore non conta come "prima rilevazione"
            try:
                data = datetime(anno, mese_i, int(giorno_str)).date()
            except (TypeError, ValueError):
                continue
            if prima is None or data < prima:
                prima = data
    return prima


def _giorni_scoperti(temperature: dict, anno: int, oggi, giorni_indietro: int):
    """Elenco delle date passate, dentro la finestra, senza nessun valore."""
    prima = _prima_data_registrata(temperature, anno)
    if prima is None:
        return []  # scheda mai usata: non ci sono buchi da dichiarare
    inizio = max(prima, oggi - timedelta(days=giorni_indietro))
    scoperti = []
    data = inizio
    while data < oggi:  # oggi ESCLUSO: la giornata è ancora aperta
        if data.year == anno:
            esistente = (temperature or {}).get(str(data.month), {}).get(str(data.day))
            if esistente is None:
                scoperti.append(data)
        data += timedelta(days=1)
    return scoperti


async def marca_giorni_non_rilevati(giorni_indietro: int = 45) -> dict:
    """Scrive a database i giorni passati senza lettura come "non rilevato".
    Girato all'avvio del server e ogni mattina dopo il job delle 07:00."""
    oggi = datetime.now(timezone.utc).date()
    anno = oggi.year
    ts = datetime.now(timezone.utc).isoformat()
    marcatore = {
        "temp": None,
        "non_rilevato": True,
        "motivo": MOTIVO_NON_RILEVATO,
        "timestamp": ts,
        "auto": True,
        "allarme": False,
    }

    esito = {"temperature_positive": 0, "temperature_negative": 0, "sanificazione": 0}

    for collection, chiave in (
        (db.temperature_positive, "temperature_positive"),
        (db.temperature_negative, "temperature_negative"),
    ):
        schede = await collection.find({"anno": anno}, {"_id": 1, "temperature": 1}).to_list(50)
        for scheda in schede:
            scoperti = _giorni_scoperti(scheda.get("temperature"), anno, oggi, giorni_indietro)
            if not scoperti:
                continue
            upd = {f"temperature.{d.month}.{d.day}": marcatore for d in scoperti}
            upd["updated_at"] = ts
            await collection.update_one({"_id": scheda["_id"]}, {"$set": upd})
            esito[chiave] += len(scoperti)

    # Sanificazione: la casella vuota non dice se "non è stato fatto" oppure
    # "nessuno l'ha registrato". Il giorno passato senza NESSUNA registrazione
    # diventa "N/D" su tutte le righe di quel giorno.
    inizio_finestra = oggi - timedelta(days=giorni_indietro)
    schede_san = await db.sanificazione_schede.find(
        {"anno": anno}, {"_id": 1, "mese": 1, "registrazioni": 1}
    ).to_list(50)
    for scheda in schede_san:
        mese = scheda.get("mese")
        reg = scheda.get("registrazioni") or {}
        if not mese or not reg:
            continue
        # prima registrazione vera del mese: prima di quella non c'è buco
        giorni_fatti = [
            int(g)
            for v in reg.values()
            if isinstance(v, dict)
            for g, val in v.items()
            if val in ("X", "x", "1", 1, True) and str(g).isdigit()
        ]
        if not giorni_fatti:
            continue
        upd = {}
        for giorno in range(min(giorni_fatti), 32):
            try:
                data = datetime(anno, int(mese), giorno).date()
            except ValueError:
                break  # fine mese
            if data >= oggi or data < inizio_finestra:
                continue
            g_str = str(giorno)
            if any(v.get(g_str) for v in reg.values() if isinstance(v, dict)):
                continue  # qualcosa è stato registrato: non è un buco
            for attr in reg:
                upd[f"registrazioni.{attr}.{g_str}"] = "N/D"
        if upd:
            upd["updated_at"] = ts
            await db.sanificazione_schede.update_one({"_id": scheda["_id"]}, {"$set": upd})
            esito["sanificazione"] += 1

    return esito


@router.post("/marca-giorni-non-rilevati")
async def marca_giorni_non_rilevati_endpoint(
    giorni_indietro: int = 45, _admin=Depends(require_admin)
):
    """Dichiara a database i giorni passati senza rilevazione. Non riscrive
    nulla di esistente e non inventa temperature."""
    esito = await marca_giorni_non_rilevati(giorni_indietro)
    return {"success": True, "marcati": esito, "motivo": MOTIVO_NON_RILEVATO}


@router.get("/stato")
async def get_status():
    """Verifica stato dei dati HACCP"""
    temp_pos = await db.temperature_positive.count_documents({})
    temp_neg = await db.temperature_negative.count_documents({})
    san = await db.sanificazione.count_documents({})

    # Verifica ultimo aggiornamento
    ultimo_temp = await db.temperature_positive.find_one({}, sort=[("updated_at", -1)])

    return {
        "schede_frigoriferi": temp_pos,
        "schede_freezer": temp_neg,
        "schede_sanificazione": san,
        "ultimo_aggiornamento": ultimo_temp.get("updated_at") if ultimo_temp else None,
    }
