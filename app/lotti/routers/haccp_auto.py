"""
Router per gestione automatica dati HACCP.
Popola i dati nella struttura ESISTENTE del database (frigorifero_numero, temperature per mese/giorno).
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Request

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




@router.post("/popola-sanificazione", response_model=PopulateResult)
async def popola_sanificazione_storica(
    data_inizio: str = "2024-01-01", data_fine: Optional[str] = None,
    _admin=Depends(require_admin),
):
    raise HTTPException(
        status_code=410,
        detail="Bloccato: le sanificazioni devono essere registrate dall'operatore.",
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


# ─────────────────────────────────────────────────────────────────────────────
# TURNO DEL MATTINO — le rilevazioni del giorno si APRONO, non si riempiono
#
# Alle 07:00 il sistema prepara il lavoro della giornata: per ogni frigorifero
# e congelatore attivo apre la casella di oggi e ci scrive CHI deve rilevare
# (il responsabile assegnato all'apparecchio, nome preso da HR). La casella
# resta senza temperatura: `temp` e' None, `stato` e' "da_rilevare".
#
# L'operatore la compila dal tablet, e il PIN con cui e' entrato E' la firma.
# Quella e' una misura vera, con un nome vero sopra.
#
# Perche' non la riempie il sistema: fino al 20/09/2026 lo faceva, con una
# temperatura sorteggiata dentro le soglie e un firmatario sorteggiato fra sei
# dipendenti. Un registro HACCP che attesta controlli mai eseguiti, col nome di
# chi non li ha eseguiti, davanti a un'ispezione vale meno di un registro
# vuoto: e' un falso, e il rischio e' di chi lo esibisce.
#
# Cosa cambia in pratica: il registro si riempie lo stesso, ma la mattina i
# responsabili trovano il loro elenco gia' pronto e a fine giornata si vede a
# colpo d'occhio cosa manca — invece di scoprire a marzo che a settembre non
# aveva rilevato nessuno.
# ─────────────────────────────────────────────────────────────────────────────

STATO_DA_RILEVARE = "da_rilevare"
STATO_CONFORME = "conforme"

# Cosa dichiara il record quando il responsabile registra il proprio controllo:
# e' l'esito di una verifica visiva, non la lettura di uno strumento. Detto
# cosi' in stampa, davanti a un'ispezione dichiara esattamente il vero.
METODO_CONTROLLO_VISIVO = "controllo visivo del responsabile dell'attivita'"


async def _apparecchi_attivi(tipo: str) -> list:
    """Frigoriferi o congelatori in servizio, col loro responsabile."""
    # Un apparecchio fuori servizio non si rileva: aprirgli le caselle
    # riempirebbe il registro di giornate che nessuno poteva compilare, e a
    # fine mese non si distinguerebbe un guasto da una dimenticanza.
    return await db.attrezzature_config.find(
        {"tipo": tipo, "attivo": {"$ne": False}, "fuori_servizio": {"$ne": True}},
        {"_id": 0, "numero": 1, "nome": 1, "operatore_id": 1, "operatore_nome": 1},
    ).sort("numero", 1).to_list(100)


async def apri_rilevazioni_del_giorno(quando=None) -> dict:
    """Apre la casella di oggi su ogni apparecchio attivo, assegnata al suo
    responsabile. Non scrive nessuna temperatura e non sovrascrive mai una
    casella che ha gia' un valore.

    Ritorna il riepilogo del turno: quante aperte, e su quali apparecchi manca
    il responsabile (quelli il cui registro restera' senza firma finche'
    qualcuno non li assegna).
    """
    adesso = quando or datetime.now(timezone.utc)
    anno, mese, giorno = adesso.year, adesso.month, adesso.day
    campo = f"temperature.{mese}.{giorno}"
    ts = adesso.isoformat()

    esito = {"aperte": 0, "gia_presenti": 0, "senza_responsabile": [],
             "data": adesso.date().isoformat()}

    # Qui il turno scriveva «conforme, entro soglia» firmato dal responsabile
    # su ogni apparecchio, alle 07:00, prima che qualcuno avesse controllato.
    # Il controllo visivo si dichiara DOPO il giro, firmato da chi lo fa:
    # POST /haccp-auto/dichiara-conformi-oggi. Il turno apre solo le caselle.
    for tipo, collezione, chiave_numero in (
        ("frigo", db.temperature_positive, "frigorifero_numero"),
        ("congelatore", db.temperature_negative, "congelatore_numero"),
    ):
        for apparecchio in await _apparecchi_attivi(tipo):
            numero = apparecchio.get("numero")
            scheda = await collezione.find_one(
                {"anno": anno, chiave_numero: numero},
                # Le soglie servono: finiscono DENTRO il record, cosi' un
                # cambio successivo non riscrive il giudizio sul passato.
                {"_id": 1, "temperature": 1, "temp_min": 1, "temp_max": 1},
            )
            if not scheda:
                continue  # la scheda dell'anno la crea chi registra, non il turno
            if (scheda.get("temperature") or {}).get(str(mese), {}).get(str(giorno)) is not None:
                esito["gia_presenti"] += 1
                continue
            if not apparecchio.get("operatore_id"):
                esito["senza_responsabile"].append(apparecchio.get("nome", f"{tipo} {numero}"))

            casella = {
                "temp": None,                       # la misura la fa una persona
                "stato": STATO_DA_RILEVARE,
                "operatore_id": apparecchio.get("operatore_id", ""),
                "operatore_nome": apparecchio.get("operatore_nome", ""),
                "aperta_il": ts,
                "allarme": False,
            }

            await collezione.update_one(
                {"_id": scheda["_id"]},
                {"$set": {campo: casella, "updated_at": ts}},
            )
            esito["aperte"] += 1
    return esito


@router.post("/apri-rilevazioni-oggi")
async def apri_rilevazioni_oggi(_admin=Depends(require_admin)):
    """Rifa' a mano il turno del mattino (se il servizio era spento alle 07:00)."""
    return {"success": True, **await apri_rilevazioni_del_giorno()}


@router.post("/dichiara-conformi-oggi")
async def dichiara_conformi_oggi(request: Request, pin: str = ""):
    """Il responsabile, finito il giro, dichiara conformi le caselle ancora aperte.

    Vale solo se nelle Impostazioni il metodo e' il controllo visivo del
    responsabile. Firma chi tocca il pulsante (PIN o sessione verificata),
    all'ora in cui lo tocca; una firma non verificata non dichiara niente.
    Non tocca le caselle gia' registrate (una temperatura vera vince).
    """
    from app.lotti.azienda import get_azienda
    from app.lotti.servizi.registro_haccp import firma_registrazione

    azienda = await get_azienda()
    if str(azienda.get("controllo_visivo_responsabile") or "").strip().lower() not in (
        "1", "true", "si", "sì", "x"
    ):
        raise HTTPException(
            status_code=409,
            detail="Il controllo visivo del responsabile non e' attivo nelle Impostazioni.",
        )
    firma = await firma_registrazione(request, pin, "")
    if not firma.get("firma_verificata") or not firma.get("operatore"):
        raise HTTPException(
            status_code=401,
            detail="Serve la firma di chi ha fatto il giro: entra col tuo PIN.",
        )
    adesso = datetime.now(timezone.utc)
    ts = adesso.isoformat()
    ogni_ore = str(azienda.get("controllo_visivo_ogni_ore") or "2").strip()
    dichiarate = 0
    for tipo, collezione, chiave_numero in (
        ("frigo", db.temperature_positive, "frigorifero_numero"),
        ("congelatore", db.temperature_negative, "congelatore_numero"),
    ):
        for apparecchio in await _apparecchi_attivi(tipo):
            scheda = await collezione.find_one(
                {"anno": adesso.year, chiave_numero: apparecchio.get("numero")},
                {"_id": 1, "temperature": 1, "temp_min": 1, "temp_max": 1},
            )
            if not scheda:
                continue
            attuale = (scheda.get("temperature") or {}).get(str(adesso.month), {}).get(str(adesso.day))
            if attuale is not None and not (
                isinstance(attuale, dict) and attuale.get("stato") == STATO_DA_RILEVARE
            ):
                continue
            casella = {
                "temp": None,
                "esito": "conforme",
                "stato": STATO_CONFORME,
                "soglie": {"min": scheda.get("temp_min"), "max": scheda.get("temp_max")},
                "metodo": METODO_CONTROLLO_VISIVO,
                "controllo_ogni_ore": ogni_ore,
                "operatore": firma["operatore"],
                "dipendente_id": firma.get("dipendente_id") or "",
                "firma_verificata": True,
                "firma_via": firma.get("firma_via") or "",
                "dichiarato_dal_responsabile": True,
                "allarme": False,
                "timestamp": ts,
            }
            await collezione.update_one(
                {"_id": scheda["_id"]},
                {"$set": {f"temperature.{adesso.month}.{adesso.day}": casella, "updated_at": ts}},
            )
            dichiarate += 1
    return {"success": True, "dichiarate": dichiarate, "firmato_da": firma["operatore"]}


@router.get("/turno-oggi")
async def turno_di_oggi():
    """Cosa resta da rilevare oggi, e a chi tocca. Lo leggono i tablet."""
    adesso = datetime.now(timezone.utc)
    mese, giorno = str(adesso.month), str(adesso.day)
    da_fare, fatte = [], 0
    for tipo, collezione, chiave_numero in (
        ("frigo", db.temperature_positive, "frigorifero_numero"),
        ("congelatore", db.temperature_negative, "congelatore_numero"),
    ):
        for scheda in await collezione.find(
            {"anno": adesso.year}, {"_id": 0, chiave_numero: 1, "temperature": 1,
                                    "frigorifero_nome": 1, "congelatore_nome": 1},
        ).to_list(100):
            casella = (scheda.get("temperature") or {}).get(mese, {}).get(giorno)
            if not isinstance(casella, dict):
                if casella is not None:
                    fatte += 1
                continue
            if casella.get("temp") is not None:
                fatte += 1
                continue
            da_fare.append({
                "tipo": tipo,
                "numero": scheda.get(chiave_numero),
                "nome": scheda.get("frigorifero_nome") or scheda.get("congelatore_nome") or "",
                "operatore_id": casella.get("operatore_id", ""),
                "operatore_nome": casella.get("operatore_nome", ""),
            })
    return {"data": adesso.date().isoformat(), "da_rilevare": da_fare,
            "quante_da_rilevare": len(da_fare), "gia_rilevate": fatte}
