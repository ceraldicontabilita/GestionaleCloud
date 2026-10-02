"""
Router per gestione automatica dati HACCP.
Popola i dati nella struttura ESISTENTE del database (frigorifero_numero, temperature per mese/giorno).
"""

from datetime import date, datetime, timedelta, timezone
from typing import Optional
import uuid

from fastapi import APIRouter, HTTPException, Depends, File, Request, UploadFile

from app.lotti.auth import request_actor, require_admin, require_permesso
from pydantic import BaseModel

from app.lotti.db import database as db
from app.lotti.servizi.registro_haccp import FUSO

router = APIRouter(prefix="/haccp-auto", tags=["HACCP Automazione"])


@router.post("/importa-registri-excel")
async def importa_registri_excel(
    request: Request,
    temperature_negative: UploadFile = File(...),
    temperature_positive: UploadFile = File(...),
    sanificazione: UploadFile = File(...),
    conferma: bool = False,
    _admin=Depends(require_admin),
):
    """Anteprima o sostituzione protetta dei registri HACCP dell'anno corrente.

    L'anteprima non scrive nulla. Con ``conferma=true`` viene prima conservato
    un backup completo nel database; un errore durante la sostituzione avvia il
    ripristino automatico.
    """
    from app.lotti.servizi.import_haccp_excel import (
        prepara_importazione,
        riepilogo,
        sostituisci_archivio,
    )
    from app.utils.upload_guard import leggi_upload

    neg_raw = await leggi_upload(temperature_negative)
    pos_raw = await leggi_upload(temperature_positive)
    san_raw = await leggi_upload(sanificazione)
    preparata = prepara_importazione(
        neg_raw,
        temperature_negative.filename or "temperature-negative.xlsx",
        pos_raw,
        temperature_positive.filename or "temperature-positive.xlsx",
        san_raw,
        sanificazione.filename or "sanificazione.xlsx",
    )
    if not conferma:
        return {"success": True, "anteprima": True, **riepilogo(preparata)}
    esito = await sostituisci_archivio(db, preparata, request_actor(request) or {})
    return {"success": True, "anteprima": False, **esito}


class PopulateResult(BaseModel):
    success: bool
    message: str
    days_populated: int
    date_from: str
    date_to: str


class AttestazioneStoricaRequest(BaseModel):
    """Dichiarazione del titolare, non generazione di misure strumentali."""

    data_inizio: date = date(2023, 1, 1)
    data_fine: Optional[date] = None
    dichiarazione: str = (
        "Il responsabile attesta che, nel periodo indicato, i controlli "
        "giornalieri delle temperature sono risultati conformi. Le anomalie "
        "eventualmente riscontrate vengono registrate manualmente con il valore misurato."
    )
    attesta_sanificazioni_registrate: bool = True
    attiva_giro_automatico_ore_7: bool = True


_DOC_ATTESTAZIONE = "haccp_attestazione_continua"
_STATI_DA_NON_SOVRASCRIVERE = {
    "anomalia", "fuori_range", "manutenzione", "non_usato", "chiuso",
}


def _firma_da_attore(attore: dict, attestazione_id: str, sottoscritta_il: str) -> dict:
    return {
        "operatore": attore.get("nome") or "",
        "dipendente_id": attore.get("id") or "",
        "firma_verificata": True,
        "firma_via": "attestazione_titolare",
        "attestazione_verificata": True,
        "attestazione_id": attestazione_id,
        "attestazione_sottoscritta_il": sottoscritta_il,
    }


def _fuori_soglia(valore, minimo, massimo) -> bool:
    if not isinstance(valore, (int, float)) or isinstance(valore, bool):
        return False
    return ((minimo is not None and valore < minimo)
            or (massimo is not None and valore > massimo))


def _record_attestato(esistente, scheda: dict, data_riferimento: date, firma: dict) -> tuple[dict | None, str]:
    """Trasforma una casella in una dichiarazione verificabile senza inventare gradi.

    Una misura o anomalia manuale vince sempre. I valori numerici gia' presenti
    restano identici; la firma attesta la loro veridicita'. Una casella vuota o
    un vecchio N/D diventa invece un esito conforme senza valore numerico.
    """
    if isinstance(esistente, dict):
        if esistente.get("attestazione_verificata"):
            return None, "gia_attestata"
        stato = str(esistente.get("stato") or "").strip().lower()
        if (esistente.get("allarme") or stato in _STATI_DA_NON_SOVRASCRIVERE
                or esistente.get("is_manutenzione") or esistente.get("is_non_usato")):
            return None, "anomalia_o_stato_speciale"
        temperatura = esistente.get("temp")
        if _fuori_soglia(temperatura, scheda.get("temp_min"), scheda.get("temp_max")):
            return None, "fuori_soglia"
        if esistente.get("firma_verificata"):
            return None, "gia_firmata"
        if isinstance(temperatura, (int, float)) and not isinstance(temperatura, bool):
            nuovo = dict(esistente)
            tipo = "misura_attestata"
        else:
            nuovo = {
                "temp": None,
                "esito": "conforme",
                "stato": STATO_CONFORME,
                "soglie": {"min": scheda.get("temp_min"), "max": scheda.get("temp_max")},
                "metodo": METODO_CONTROLLO_VISIVO,
                "dichiarato_dal_responsabile": True,
                "allarme": False,
                "data_riferimento": data_riferimento.isoformat(),
            }
            tipo = "conformita_popolata"
    elif isinstance(esistente, (int, float)) and not isinstance(esistente, bool):
        if _fuori_soglia(esistente, scheda.get("temp_min"), scheda.get("temp_max")):
            return None, "fuori_soglia"
        nuovo = {"temp": esistente, "allarme": False}
        tipo = "misura_attestata"
    elif esistente in (None, "", "N/D"):
        nuovo = {
            "temp": None,
            "esito": "conforme",
            "stato": STATO_CONFORME,
            "soglie": {"min": scheda.get("temp_min"), "max": scheda.get("temp_max")},
            "metodo": METODO_CONTROLLO_VISIVO,
            "dichiarato_dal_responsabile": True,
            "allarme": False,
            "data_riferimento": data_riferimento.isoformat(),
        }
        tipo = "conformita_popolata"
    else:
        return None, "valore_non_riconosciuto"

    nuovo.update(firma)
    nuovo["firma_significato"] = "attestazione_veridicita_storica"
    return nuovo, tipo


def _normalizza_registrazioni_sanificazione(registrazioni: dict) -> tuple[dict, int]:
    """Ricompone la chiave con il punto che vecchi update Mongo avevano spezzato."""
    from app.lotti.routers.sanificazione import ATTREZZATURE_SANIFICAZIONE

    normalizzate = dict(registrazioni or {})
    riparate = 0
    for area in ATTREZZATURE_SANIFICAZIONE:
        if "." not in area:
            continue
        prefisso, resto = area.split(".", 1)
        corrotta = normalizzate.get(prefisso)
        if not isinstance(corrotta, dict):
            continue
        annidata = corrotta.get(resto)
        dirette = {k: v for k, v in corrotta.items() if str(k).isdigit()}
        if not isinstance(annidata, dict) and not dirette:
            continue
        destinazione = dict(normalizzate.get(area) or {})
        for fonte in (dirette, annidata if isinstance(annidata, dict) else {}):
            for giorno, valore in fonte.items():
                destinazione.setdefault(str(giorno), valore)
        normalizzate[area] = destinazione
        normalizzate.pop(prefisso, None)
        riparate += 1
    return normalizzate, riparate


async def applica_attestazione_storica(
    data_inizio: date, data_fine: date, attore: dict, dichiarazione: str,
    *, attesta_sanificazioni_registrate: bool = True,
    attiva_giro_automatico_ore_7: bool = True,
) -> dict:
    """Applica la dichiarazione del titolare in modo additivo e idempotente."""
    oggi = datetime.now(FUSO).date()
    if data_inizio < date(2023, 1, 1):
        raise HTTPException(422, "Il periodo attestabile parte dal 01/01/2023")
    data_fine = min(data_fine, oggi)
    if data_inizio > data_fine:
        raise HTTPException(422, "Intervallo della dichiarazione non valido")
    testo = str(dichiarazione or "").strip()
    if not testo:
        raise HTTPException(422, "La dichiarazione non puo' essere vuota")

    gia = await db.impostazioni.find_one({
        "_id": _DOC_ATTESTAZIONE,
        "data_inizio": data_inizio.isoformat(),
        "data_fine": data_fine.isoformat(),
        "firmatario_id": attore.get("id") or "",
        "dichiarazione": testo,
    })
    # Non basta che la dichiarazione esista: un'importazione Excel successiva
    # puo' aver sostituito le caselle e rimosso le firme. In quel caso la stessa
    # attestazione deve essere riapplicata ai nuovi valori, senza crearne una
    # fittizia o cambiare la data della sottoscrizione originale.
    attestazione_id = str((gia or {}).get("attestazione_id") or uuid.uuid4())
    sottoscritta_il = str(
        (gia or {}).get("sottoscritta_il") or datetime.now(timezone.utc).isoformat()
    )
    firma = _firma_da_attore(attore, attestazione_id, sottoscritta_il)
    riepilogo = {
        "temperature_popolate": 0,
        "misure_esistenti_attestate": 0,
        "temperature_non_sovrascritte": 0,
        "sanificazioni_attestate": 0,
        "schede_sanificazione_riparate": 0,
    }

    for collezione in (db.temperature_positive, db.temperature_negative):
        schede = await collezione.find({
            "anno": {"$gte": data_inizio.year, "$lte": data_fine.year}
        }).to_list(500)
        for scheda in schede:
            aggiornamenti = {}
            giorno = max(data_inizio, date(int(scheda["anno"]), 1, 1))
            fine_scheda = min(data_fine, date(int(scheda["anno"]), 12, 31))
            temperature = scheda.get("temperature") or {}
            while giorno <= fine_scheda:
                esistente = (temperature.get(str(giorno.month)) or {}).get(str(giorno.day))
                record, tipo = _record_attestato(esistente, scheda, giorno, firma)
                if record is not None:
                    aggiornamenti[f"temperature.{giorno.month}.{giorno.day}"] = record
                    if tipo == "conformita_popolata":
                        riepilogo["temperature_popolate"] += 1
                    else:
                        riepilogo["misure_esistenti_attestate"] += 1
                elif tipo not in ("gia_attestata", "gia_firmata"):
                    riepilogo["temperature_non_sovrascritte"] += 1
                giorno += timedelta(days=1)
            if aggiornamenti:
                aggiornamenti["updated_at"] = sottoscritta_il
                await collezione.update_one({"_id": scheda["_id"]}, {"$set": aggiornamenti})

    if attesta_sanificazioni_registrate:
        schede = await db.sanificazione_schede.find({
            "anno": {"$gte": data_inizio.year, "$lte": data_fine.year}
        }).to_list(100)
        for scheda in schede:
            registrazioni, riparate = _normalizza_registrazioni_sanificazione(
                scheda.get("registrazioni") or {})
            firme = dict(scheda.get("firme") or {})
            cambiate = bool(riparate)
            for area, giorni in registrazioni.items():
                if not isinstance(giorni, dict):
                    continue
                firme_area = dict(firme.get(area) or {})
                for giorno_str, valore in giorni.items():
                    if valore not in ("X", "x", "1", 1, True) or not str(giorno_str).isdigit():
                        continue
                    try:
                        riferimento = date(int(scheda["anno"]), int(scheda["mese"]), int(giorno_str))
                    except (TypeError, ValueError):
                        continue
                    if not (data_inizio <= riferimento <= data_fine):
                        continue
                    precedente = firme_area.get(str(giorno_str)) or {}
                    if precedente.get("firma_verificata") or precedente.get("attestazione_verificata"):
                        continue
                    firme_area[str(giorno_str)] = {
                        "valore": "X",
                        **firma,
                        "firma_significato": "attestazione_veridicita_storica",
                        "data_riferimento": riferimento.isoformat(),
                    }
                    riepilogo["sanificazioni_attestate"] += 1
                    cambiate = True
                if firme_area:
                    firme[area] = firme_area
            if cambiate:
                await db.sanificazione_schede.update_one(
                    {"_id": scheda["_id"]},
                    {"$set": {"registrazioni": registrazioni, "firme": firme,
                              "updated_at": sottoscritta_il}},
                )
                riepilogo["schede_sanificazione_riparate"] += riparate

    documento = {
        "_id": _DOC_ATTESTAZIONE,
        "attivo": bool(attiva_giro_automatico_ore_7),
        "attestazione_id": attestazione_id,
        "data_inizio": data_inizio.isoformat(),
        "data_fine": data_fine.isoformat(),
        "dichiarazione": testo,
        "firmato_da": attore.get("nome") or "",
        "firmatario_id": attore.get("id") or "",
        "firma_via": attore.get("via") or "sessione",
        "firma_verificata": True,
        "sottoscritta_il": sottoscritta_il,
        "modalita_operativa": (
            "Alle 07:00 registra esito conforme senza inventare gradi; "
            "ogni anomalia rilevata nel giro sostituisce l'esito con la misura manuale."
        ),
        "ultima_esecuzione": {
            "success": True,
            "attestazione_id": attestazione_id,
            "data_inizio": data_inizio.isoformat(),
            "data_fine": data_fine.isoformat(),
            **riepilogo,
        },
    }
    await db.impostazioni.replace_one({"_id": _DOC_ATTESTAZIONE}, documento, upsert=True)
    scritture = (
        riepilogo["temperature_popolate"]
        + riepilogo["misure_esistenti_attestate"]
        + riepilogo["sanificazioni_attestate"]
        + riepilogo["schede_sanificazione_riparate"]
    )
    return {**documento["ultima_esecuzione"], "idempotente": scritture == 0}


@router.post("/attesta-storico")
async def attesta_storico(
    richiesta: AttestazioneStoricaRequest, request: Request,
    _admin=Depends(require_admin),
):
    attore = request_actor(request)
    if not attore or not attore.get("id") or attore.get("ruolo") != "amministratore":
        raise HTTPException(401, "Serve la sessione verificata del titolare")
    return await applica_attestazione_storica(
        richiesta.data_inizio,
        richiesta.data_fine or datetime.now(FUSO).date(),
        attore,
        richiesta.dichiarazione,
        attesta_sanificazioni_registrate=richiesta.attesta_sanificazioni_registrate,
        attiva_giro_automatico_ore_7=richiesta.attiva_giro_automatico_ore_7,
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




async def verifica_e_popola_oggi():
    """Applica, se attiva, la dichiarazione continuativa firmata dal titolare.

    Non genera temperature numeriche e non assegna nomi casuali. Registra solo
    l'esito conforme dichiarato; una successiva misura manuale, soprattutto se
    anomala, lo sostituisce conservando la storia della casella.
    """
    return await applica_dichiarazione_continua_oggi()


@router.get("/verifica-oggi")
async def verifica_oggi_stato():
    """Diagnostica sola lettura; il giro scrive esclusivamente dallo scheduler."""
    attestazione = await db.impostazioni.find_one(
        {"_id": _DOC_ATTESTAZIONE},
        {"_id": 0, "attivo": 1, "data_inizio": 1, "data_fine": 1,
         "firmato_da": 1, "sottoscritta_il": 1},
    )
    return {
        "ok": True,
        "data": datetime.now(FUSO).date().isoformat(),
        "attestazione_continuativa": attestazione,
        "nota": "La scrittura giornaliera avviene solo nel job delle 07:00.",
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
            if esistente is None or (
                isinstance(esistente, dict)
                and esistente.get("stato") == STATO_DA_RILEVARE
            ):
                scoperti.append(data)
        data += timedelta(days=1)
    return scoperti


def _record_conformita_continua(scheda: dict, riferimento: date, attestazione: dict, ts: str) -> dict:
    return {
        "temp": None,
        "esito": "conforme",
        "stato": STATO_CONFORME,
        "soglie": {"min": scheda.get("temp_min"), "max": scheda.get("temp_max")},
        "metodo": METODO_CONTROLLO_VISIVO,
        "dichiarato_dal_responsabile": True,
        "allarme": False,
        "timestamp": ts,
        "data_riferimento": riferimento.isoformat(),
        "operatore": attestazione.get("firmato_da") or "",
        "dipendente_id": attestazione.get("firmatario_id") or "",
        "firma_verificata": True,
        "firma_via": "attestazione_titolare_continuativa",
        "attestazione_verificata": True,
        "attestazione_id": attestazione.get("attestazione_id") or "",
        "attestazione_sottoscritta_il": attestazione.get("sottoscritta_il") or "",
        "firma_significato": "dichiarazione_continuativa_esito_conforme",
    }


async def marca_giorni_non_rilevati(giorni_indietro: int = 45) -> dict:
    """Scrive a database i giorni passati senza lettura come "non rilevato".
    Girato all'avvio del server e ogni mattina dopo il job delle 07:00."""
    # Il giorno del registro è quello di Napoli, non di Greenwich: fra
    # mezzanotte e le 02:00 (ora legale) il giorno UTC era ancora ieri.
    oggi = datetime.now(FUSO).date()
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
    attestazione = await db.impostazioni.find_one({"_id": _DOC_ATTESTAZIONE}) or {}
    dichiarazione_attiva = bool(
        attestazione.get("attivo") and attestazione.get("firma_verificata")
    )

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
            upd = {
                f"temperature.{d.month}.{d.day}": (
                    _record_conformita_continua(scheda, d, attestazione, ts)
                    if dichiarazione_attiva else marcatore
                )
                for d in scoperti
            }
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
        reg, _riparate = _normalizza_registrazioni_sanificazione(
            scheda.get("registrazioni") or {})
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
        cambiata = False
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
                if isinstance(reg.get(attr), dict):
                    reg[attr][g_str] = "N/D"
                    cambiata = True
        if cambiata or _riparate:
            await db.sanificazione_schede.update_one(
                {"_id": scheda["_id"]},
                {"$set": {"registrazioni": reg, "updated_at": ts}},
            )
            esito["sanificazione"] += 1

    return esito


@router.post("/marca-giorni-non-rilevati")
async def marca_giorni_non_rilevati_endpoint(
    giorni_indietro: int = 45, _ruolo=Depends(require_permesso("haccp_registri"))
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
    san = await db.sanificazione_schede.count_documents({})
    attestazione = await db.impostazioni.find_one(
        {"_id": _DOC_ATTESTAZIONE}, {"_id": 0, "attivo": 1, "data_inizio": 1,
                                     "data_fine": 1, "firmato_da": 1,
                                     "sottoscritta_il": 1}
    )

    # Verifica ultimo aggiornamento
    ultimo_temp = await db.temperature_positive.find_one({}, sort=[("updated_at", -1)])

    return {
        "schede_frigoriferi": temp_pos,
        "schede_freezer": temp_neg,
        "schede_sanificazione": san,
        "ultimo_aggiornamento": ultimo_temp.get("updated_at") if ultimo_temp else None,
        "attestazione_continuativa": attestazione,
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


def controllo_visivo_attivo(azienda: dict) -> bool:
    """Nelle Impostazioni il metodo e' il controllo visivo del responsabile."""
    return str((azienda or {}).get("controllo_visivo_responsabile") or "").strip().lower() in (
        "1", "true", "si", "sì", "x"
    )


async def applica_dichiarazione_continua_oggi(quando=None) -> dict:
    adesso = quando or datetime.now(FUSO)
    attestazione = await db.impostazioni.find_one({"_id": _DOC_ATTESTAZIONE}) or {}
    if not attestazione.get("attivo") or not attestazione.get("firma_verificata"):
        return {
            "ok": True,
            "data": adesso.date().isoformat(),
            "generato": False,
            "dichiarate": 0,
            "elementi": [],
            "reason": "nessuna_attestazione_continuativa_attiva",
        }

    firma = {
        "operatore": attestazione.get("firmato_da") or "",
        "dipendente_id": attestazione.get("firmatario_id") or "",
        "firma_verificata": True,
        "firma_via": "attestazione_titolare_continuativa",
        "attestazione_verificata": True,
        "attestazione_id": attestazione.get("attestazione_id") or "",
        "attestazione_sottoscritta_il": attestazione.get("sottoscritta_il") or "",
        "firma_significato": "dichiarazione_continuativa_esito_conforme",
    }
    dichiarate = 0
    gia_presenti = 0
    for tipo, collezione, chiave_numero in (
        ("frigo", db.temperature_positive, "frigorifero_numero"),
        ("congelatore", db.temperature_negative, "congelatore_numero"),
    ):
        for apparecchio in await _apparecchi_attivi(tipo):
            scheda = await collezione.find_one({
                "anno": adesso.year, chiave_numero: apparecchio.get("numero")
            })
            if not scheda:
                continue
            esistente = (scheda.get("temperature") or {}).get(
                str(adesso.month), {}).get(str(adesso.day))
            if esistente is not None and not (
                isinstance(esistente, dict) and esistente.get("stato") == STATO_DA_RILEVARE
            ):
                gia_presenti += 1
                continue
            casella = {
                "temp": None,
                "esito": "conforme",
                "stato": STATO_CONFORME,
                "soglie": {"min": scheda.get("temp_min"), "max": scheda.get("temp_max")},
                "metodo": METODO_CONTROLLO_VISIVO,
                "dichiarato_dal_responsabile": True,
                "allarme": False,
                "timestamp": adesso.isoformat(),
                "data_riferimento": adesso.date().isoformat(),
                **firma,
            }
            await collezione.update_one(
                {"_id": scheda["_id"]},
                {"$set": {f"temperature.{adesso.month}.{adesso.day}": casella,
                          "updated_at": adesso.isoformat()}},
            )
            dichiarate += 1
    return {
        "ok": True,
        "data": adesso.date().isoformat(),
        "generato": bool(dichiarate),
        "dichiarate": dichiarate,
        "elementi": [],
        "gia_presenti": gia_presenti,
        "metodo": "attestazione_titolare_continuativa",
    }


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
    il responsabile. Senza assegnazione risponde il titolare (nome dalle
    Impostazioni): resta «senza responsabile» solo se quel nome non c'e'.
    """
    from app.lotti.servizi.responsabile_haccp import responsabile_apparecchio, responsabile_predefinito

    adesso = quando or datetime.now(FUSO)
    anno, mese, giorno = adesso.year, adesso.month, adesso.day
    campo = f"temperature.{mese}.{giorno}"
    ts = adesso.isoformat()

    # Un apparecchio senza responsabile assegnato e' del titolare (decisione
    # del 02/10/2026): il nome viene dalle Impostazioni, letto una volta per
    # giro. Se nessuno l'ha scritto, l'apparecchio resta senza responsabile.
    predefinito = await responsabile_predefinito()
    esito = {"aperte": 0, "gia_presenti": 0, "senza_responsabile": [],
             "responsabile_predefinito": predefinito.get("operatore_nome") or "",
             "data": adesso.date().isoformat()}

    # Prima fase del turno: apre le caselle senza inventare misure. Subito dopo
    # l'orchestratore applica l'eventuale dichiarazione continuativa firmata;
    # una misura manuale successiva conserva questa casella nella sua storia.
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
                # Le pagine non creano più le schede quando le apri: la scheda
                # dell'anno di un apparecchio attivo nasce qui, al primo turno,
                # vuota (nessuna temperatura), così a gennaio le caselle si aprono.
                if tipo == "frigo":
                    from app.lotti.routers.temperature_positive import get_or_create_scheda
                else:
                    from app.lotti.routers.temperature_negative import get_or_create_scheda
                await get_or_create_scheda(anno, numero)
                scheda = await collezione.find_one(
                    {"anno": anno, chiave_numero: numero},
                    {"_id": 1, "temperature": 1, "temp_min": 1, "temp_max": 1},
                )
                if not scheda:
                    continue
            if (scheda.get("temperature") or {}).get(str(mese), {}).get(str(giorno)) is not None:
                esito["gia_presenti"] += 1
                continue
            responsabile = responsabile_apparecchio(apparecchio, predefinito)
            if not responsabile["operatore_nome"]:
                esito["senza_responsabile"].append(apparecchio.get("nome", f"{tipo} {numero}"))

            casella = {
                "temp": None,                       # la misura la fa una persona
                "stato": STATO_DA_RILEVARE,
                "operatore_id": responsabile["operatore_id"] if responsabile["operatore_nome"] else "",
                "operatore_nome": responsabile["operatore_nome"],
                "responsabile_predefinito": bool(responsabile["responsabile_predefinito"]),
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
async def apri_rilevazioni_oggi(_ruolo=Depends(require_permesso("haccp_registri"))):
    """Rifa' a mano il turno del mattino (se il servizio era spento alle 07:00)."""
    return {"success": True, **await apri_rilevazioni_del_giorno()}


@router.post("/dichiara-conformi-oggi")
async def dichiara_conformi_oggi(request: Request, pin: str = "", _ruolo=Depends(require_permesso("haccp_conformita"))):
    """Il responsabile, finito il giro, firma i controlli e chiude le caselle aperte.

    Vale solo se nelle Impostazioni il metodo e' il controllo visivo del
    responsabile. Firma chi tocca il pulsante (PIN o sessione verificata),
    all'ora in cui lo tocca; una firma non verificata non dichiara niente.
    Una temperatura gia' registrata resta identica: viene aggiunta soltanto la
    firma verificata. Le caselle ancora aperte diventano conformi senza
    inventare gradi. L'operazione e' idempotente.
    """
    from app.lotti.azienda import get_azienda
    from app.lotti.servizi.registro_haccp import firma_registrazione

    azienda = await get_azienda()
    if not controllo_visivo_attivo(azienda):
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
    # Giorno e mese sono quelli di Napoli: in UTC, dopo mezzanotte si
    # dichiarava conforme la casella di ieri.
    adesso = datetime.now(FUSO)
    ts = adesso.isoformat()
    ogni_ore = str(azienda.get("controllo_visivo_ogni_ore") or "2").strip()
    dichiarate = 0
    firmate = 0
    gia_firmate = 0
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
            aperta = attuale is None or (
                isinstance(attuale, dict) and attuale.get("stato") == STATO_DA_RILEVARE
            )
            if aperta:
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
                    "firma_significato": "conferma_controllo_giornaliero",
                    "dichiarato_dal_responsabile": True,
                    "allarme": False,
                    "timestamp": ts,
                }
                dichiarate += 1
            else:
                # Una misura vera, anche anomala, non diventa mai "conforme":
                # si conserva ogni campo e si aggiunge soltanto la firma di chi
                # ha verificato il giro. I valori legacy numerici vengono
                # avvolti senza cambiarne il significato.
                if isinstance(attuale, dict):
                    casella = dict(attuale)
                elif isinstance(attuale, (int, float)) and not isinstance(attuale, bool):
                    casella = {"temp": attuale}
                else:
                    continue
                if casella.get("firma_verificata") is True and casella.get("operatore"):
                    gia_firmate += 1
                    continue
                casella.update({
                    "operatore": firma["operatore"],
                    "dipendente_id": firma.get("dipendente_id") or "",
                    "firma_verificata": True,
                    "firma_via": firma.get("firma_via") or "",
                    "firma_significato": "conferma_controllo_giornaliero",
                    "verificato_il": ts,
                })
                firmate += 1
            await collezione.update_one(
                {"_id": scheda["_id"]},
                {"$set": {f"temperature.{adesso.month}.{adesso.day}": casella, "updated_at": ts}},
            )
    return {"success": True, "dichiarate": dichiarate, "firmate": firmate,
            "gia_firmate": gia_firmate, "firmato_da": firma["operatore"]}


@router.get("/turno-oggi")
async def turno_di_oggi():
    """Cosa resta da rilevare oggi, e a chi tocca. Lo leggono i tablet.

    Compilata = una temperatura, oppure l'esito «conforme» dichiarato dal
    responsabile col controllo visivo (senza numero, per scelta). Prima una
    casella dichiarata conforme risultava ancora «da rilevare».

    `senza_casella` sono gli apparecchi attivi che oggi non hanno nessuna
    casella (aggiunti dopo le 07:00, o servizio spento al turno): si aprono
    con «Apri le caselle di oggi». `controllo_visivo_attivo` dice se la
    dichiarazione di conformita' e' ammessa dalle Impostazioni."""
    from app.lotti.azienda import get_azienda

    adesso = datetime.now(FUSO)
    mese, giorno = str(adesso.month), str(adesso.day)
    da_fare, fatte, da_firmare, gia_firmate, senza_casella = [], 0, 0, 0, []
    for tipo, collezione, chiave_numero in (
        ("frigo", db.temperature_positive, "frigorifero_numero"),
        ("congelatore", db.temperature_negative, "congelatore_numero"),
    ):
        schede = await collezione.find(
            {"anno": adesso.year}, {"_id": 0, chiave_numero: 1, "temperature": 1,
                                    "frigorifero_nome": 1, "congelatore_nome": 1},
        ).to_list(100)
        caselle_per_numero = {
            scheda.get(chiave_numero): (scheda.get("temperature") or {}).get(mese, {}).get(giorno)
            for scheda in schede
        }
        for apparecchio in await _apparecchi_attivi(tipo):
            if caselle_per_numero.get(apparecchio.get("numero")) is None:
                senza_casella.append(apparecchio.get("nome") or f"{tipo} {apparecchio.get('numero')}")
        for scheda in schede:
            casella = caselle_per_numero.get(scheda.get(chiave_numero))
            if not isinstance(casella, dict):
                if casella is not None:
                    fatte += 1
                    if isinstance(casella, (int, float)) and not isinstance(casella, bool):
                        da_firmare += 1
                continue
            if casella.get("temp") is not None or casella.get("stato") == STATO_CONFORME \
                    or casella.get("non_rilevato"):
                fatte += 1
                if not casella.get("non_rilevato"):
                    if casella.get("firma_verificata") is True and casella.get("operatore"):
                        gia_firmate += 1
                    else:
                        da_firmare += 1
                continue
            da_fare.append({
                "tipo": tipo,
                "numero": scheda.get(chiave_numero),
                "nome": scheda.get("frigorifero_nome") or scheda.get("congelatore_nome") or "",
                "operatore_id": casella.get("operatore_id", ""),
                "operatore_nome": casella.get("operatore_nome", ""),
            })
    return {"data": adesso.date().isoformat(), "da_rilevare": da_fare,
            "quante_da_rilevare": len(da_fare), "gia_rilevate": fatte,
            "da_firmare": da_firmare, "gia_firmate": gia_firmate,
            "senza_casella": senza_casella, "quante_senza_casella": len(senza_casella),
            "controllo_visivo_attivo": controllo_visivo_attivo(await get_azienda())}
