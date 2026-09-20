"""
Router per gestione automatica dati HACCP.
Popola i dati nella struttura ESISTENTE del database (frigorifero_numero, temperature per mese/giorno).
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends

from app.lotti.auth import require_admin
from pydantic import BaseModel

from app.lotti.db import database as db

router = APIRouter(prefix="/haccp-auto", tags=["HACCP Automazione"])


class PopulateResult(BaseModel):
    success: bool
    message: str
    days_populated: int
    date_from: str
    date_to: str


@router.post("/popola-temperature", response_model=PopulateResult)
async def popola_temperature_storiche(
    data_inizio: str = "2024-01-01", data_fine: Optional[str] = None,
    _admin=Depends(require_admin),
):
    raise HTTPException(
        status_code=410,
        detail="Bloccato: le temperature HACCP devono provenire da una rilevazione verificabile.",
    )


@router.post("/popola-sanificazione", response_model=PopulateResult)
async def popola_sanificazione_storica(
    data_inizio: str = "2024-01-01", data_fine: Optional[str] = None,
    _admin=Depends(require_admin),
):
    raise HTTPException(
        status_code=410,
        detail="Bloccato: le sanificazioni devono essere registrate dall'operatore.",
    )


@router.post("/popola-tutto", response_model=PopulateResult)
async def popola_tutti_dati_haccp(data_inizio: str = "2024-01-01",
                                  _admin=Depends(require_admin)):
    raise HTTPException(
        status_code=410,
        detail="Bloccato: temperature e sanificazioni si registrano quando si eseguono.",
    )


@router.get("/verifica-oggi")
async def verifica_e_popola_oggi():
    """Non genera niente: le rilevazioni HACCP le registra chi le esegue.

    Qui sotto c'erano 201 righe di generatore, rese irraggiungibili da questo
    `return` ma mai tolte. Inventavano la rilevazione del giorno con
    `random.uniform` dentro le soglie — «sempre conformi», lo diceva il
    commento — e la firmavano con `random.choice` su una lista di sei
    dipendenti veri, nome e cognome. Stessa cosa per le sanificazioni, segnate
    «X» su tutte le attrezzature. In archivio ne restano **384** del 2026
    (192 frigoriferi + 192 congelatori): vanno convertite in «non rilevato»
    su decisione del titolare, perche' un registro sanitario non si riscrive
    da soli.

    Un registro HACCP che attesta controlli mai fatti, con il nome di chi non
    li ha fatti, davanti a un'ispezione vale meno di un registro vuoto. Il
    buco si dichiara: `marca_giorni_non_rilevati` scrive `temp: None` con il
    motivo, ed e' l'unico automatismo ammesso su queste schede.
    """
    oggi = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return {
        "ok": True,
        "message": f"HACCP {oggi}: rilevazioni attese; nessuna evidenza sintetica creata",
        "generato": False,
        "elementi": [],
        "data": oggi,
    }


@router.post("/genera-oggi")
async def genera_dati_oggi(_admin=Depends(require_admin)):
    raise HTTPException(
        status_code=410,
        detail="Bloccato: inserire solo rilevazioni HACCP realmente eseguite.",
    )


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
