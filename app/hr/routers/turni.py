"""
Turni settimanali: generazione con vincoli, bozza→pubblicato, modifica con
rivalidazione, pubblicazione con notifica al dipendente.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from uuid import uuid4
from fastapi import APIRouter, HTTPException, Body, Depends

from app.hr.database import Database, Collections
from app.hr.utils.identity import get_identity, require_roles
from app.hr.services import turni_generator as TG
from app.hr.services.notifiche import crea_notifica

logger = logging.getLogger(__name__)
router = APIRouter()

COLL = "turni_settimane"
COLL_INDISP = "turni_indisponibilita"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sid(settimana_inizio: str) -> str:
    return f"sett_{settimana_inizio}"


async def _dipendenti_attivi() -> List[Dict[str, Any]]:
    db = Database.get_db()
    docs = await db[Collections.EMPLOYEES].find(
        {"attivo": {"$ne": False}, "merged_into": {"$exists": False}},
        {"_id": 0, "id": 1, "nome_completo": 1},
    ).sort("nome_completo", 1).to_list(500)
    return [d for d in docs if d.get("id")]


async def _indisponibilita() -> List[Dict[str, Any]]:
    db = Database.get_db()
    return await db[COLL_INDISP].find({}, {"_id": 0}).to_list(2000)


def _ricalcola_totali(doc: Dict[str, Any]) -> None:
    tot: Dict[str, Dict[str, Any]] = {}
    for g in doc["giorni"]:
        for dip_id, a in g["assegnazioni"].items():
            t = tot.setdefault(dip_id, {"nome": doc.get("totali", {}).get(dip_id, {}).get("nome", ""),
                                        "ore": 0, "lunghe": 0, "riposi": 0})
            t["ore"] += a.get("ore", 0)
            if a.get("turno") == "lunga":
                t["lunghe"] += 1
            if a.get("turno") == "riposo":
                t["riposi"] += 1
    doc["totali"] = tot


@router.post("/genera", summary="Genera bozza turni (responsabile/admin)")
async def genera(
    payload: Dict[str, Any] = Body(..., example={"settimana_inizio": "2026-06-15"}),
    identity: Dict[str, Any] = Depends(require_roles("responsabile_turni", "admin")),
):
    settimana = str(payload.get("settimana_inizio", "")).strip()
    try:
        base = datetime.strptime(settimana, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, "settimana_inizio deve essere una data YYYY-MM-DD (lunedì)")
    if base.weekday() != 0:
        raise HTTPException(400, "settimana_inizio deve essere un lunedì")

    dipendenti = await _dipendenti_attivi()
    if not dipendenti:
        raise HTTPException(400, "Nessun dipendente attivo")

    db = Database.get_db()
    esistente = await db[COLL].find_one({"id": _sid(settimana)}, {"_id": 0})
    if esistente and esistente.get("stato") == "pubblicato":
        raise HTTPException(409, "Settimana già pubblicata: crea una nuova versione sbloccandola prima")

    gen = TG.genera_settimana(dipendenti, await _indisponibilita(), settimana,
                              fabbisogno=payload.get("fabbisogno"))
    doc = {
        "id": _sid(settimana),
        "settimana_inizio": settimana,
        "stato": "bozza",
        "versione": (esistente.get("versione", 0) + 1) if esistente else 1,
        "giorni": gen["giorni"],
        "totali": gen["totali"],
        "avvisi": gen["avvisi"],
        "creato_da": identity["id"],
        "creato_il": _now(),
        "pubblicato_da": None,
        "pubblicato_il": None,
    }
    await db[COLL].replace_one({"id": _sid(settimana)}, doc, upsert=True)
    doc.pop("_id", None)
    return doc


@router.get("", summary="Elenco settimane (responsabile/admin)")
async def lista(_: Dict[str, Any] = Depends(require_roles("responsabile_turni", "admin"))):
    db = Database.get_db()
    return await db[COLL].find({}, {"_id": 0, "giorni": 0}).sort("settimana_inizio", -1).to_list(200)


@router.get("/miei/corrente", summary="I miei turni (ultima settimana pubblicata)")
async def miei(identity: Dict[str, Any] = Depends(get_identity)):
    db = Database.get_db()
    doc = await db[COLL].find_one({"stato": "pubblicato"}, {"_id": 0},
                                  sort=[("settimana_inizio", -1)])
    if not doc:
        return {"settimana_inizio": None, "giorni": []}
    mid = identity["id"]
    giorni = [{"data": g["data"], "giorno_nome": g["giorno_nome"],
               "turno": g["assegnazioni"].get(mid, {})} for g in doc["giorni"]]
    return {"settimana_inizio": doc["settimana_inizio"], "stato": doc["stato"], "giorni": giorni}


@router.get("/{settimana_inizio}", summary="Dettaglio settimana")
async def dettaglio(settimana_inizio: str, identity: Dict[str, Any] = Depends(get_identity)):
    db = Database.get_db()
    doc = await db[COLL].find_one({"id": _sid(settimana_inizio)}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Settimana non trovata")
    if identity.get("role") in ("admin", "responsabile_turni"):
        return doc
    # dipendente: vede la griglia completa di tutti, ma solo se pubblicata
    # e senza le note gestionali (avvisi/metadati interni)
    if doc["stato"] != "pubblicato":
        raise HTTPException(403, "Turni non ancora pubblicati")
    return {
        "settimana_inizio": doc["settimana_inizio"],
        "stato": doc["stato"],
        "giorni": doc["giorni"],
        "totali": doc.get("totali", {}),
    }


@router.put("/{settimana_inizio}/cella", summary="Modifica una cella (responsabile/admin) + rivalida")
async def modifica_cella(
    settimana_inizio: str,
    payload: Dict[str, Any] = Body(..., example={"data": "2026-06-16", "dipendente_id": "dip-1", "turno": "lunga"}),
    _: Dict[str, Any] = Depends(require_roles("responsabile_turni", "admin")),
):
    data = payload.get("data")
    dip_id = payload.get("dipendente_id")
    turno = payload.get("turno")
    if turno not in TG.TURNI_DEFAULT:
        raise HTTPException(400, f"Turno non valido: {turno}")
    db = Database.get_db()
    doc = await db[COLL].find_one({"id": _sid(settimana_inizio)}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Settimana non trovata")
    if doc["stato"] == "pubblicato":
        raise HTTPException(409, "Settimana pubblicata: non modificabile")

    trovato = False
    for g in doc["giorni"]:
        if g["data"] == data and dip_id in g["assegnazioni"]:
            t = TG.TURNI_DEFAULT[turno]
            g["assegnazioni"][dip_id] = {"turno": turno, "label": t["label"],
                                         "inizio": t["inizio"], "fine": t["fine"], "ore": t["ore"]}
            trovato = True
            break
    if not trovato:
        raise HTTPException(404, "Cella (data/dipendente) non trovata")

    _ricalcola_totali(doc)
    doc["avvisi"] = TG.rivalida(doc)
    await db[COLL].replace_one({"id": doc["id"]}, doc)
    doc.pop("_id", None)
    return {"ok": True, "avvisi": doc["avvisi"]}


@router.post("/{settimana_inizio}/pubblica", summary="Pubblica e notifica i dipendenti")
async def pubblica(settimana_inizio: str,
                   identity: Dict[str, Any] = Depends(require_roles("responsabile_turni", "admin"))):
    db = Database.get_db()
    doc = await db[COLL].find_one({"id": _sid(settimana_inizio)}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Settimana non trovata")
    if doc["stato"] == "pubblicato":
        raise HTTPException(409, "Già pubblicata")

    await db[COLL].update_one({"id": doc["id"]},
                              {"$set": {"stato": "pubblicato", "pubblicato_il": _now(),
                                        "pubblicato_da": identity["id"]}})

    # notifica ogni dipendente coinvolto, col riepilogo dei suoi turni
    coinvolti = {dip for g in doc["giorni"] for dip in g["assegnazioni"]}
    notificati = 0
    for dip_id in coinvolti:
        righe = []
        for g in doc["giorni"]:
            a = g["assegnazioni"].get(dip_id, {})
            lbl = a.get("label", "—")
            orario = f" {a['inizio']}–{a['fine']}" if a.get("inizio") else ""
            righe.append(f"{g['giorno_nome'][:3]} {g['data'][8:10]}/{g['data'][5:7]}: {lbl}{orario}")
        msg = ("Turni della settimana del " + settimana_inizio + " pubblicati. "
               "Collegati all'app per la visione.\n\n" + "\n".join(righe))
        await crea_notifica(db, dip_id, "turno_pubblicato",
                            f"Turni settimana {settimana_inizio}", msg,
                            extra={"settimana_inizio": settimana_inizio})
        notificati += 1

    return {"ok": True, "stato": "pubblicato", "dipendenti_notificati": notificati}


@router.post("/{settimana_inizio}/sblocca", summary="Riporta in bozza (admin)")
async def sblocca(settimana_inizio: str, _: Dict[str, Any] = Depends(require_roles("admin"))):
    db = Database.get_db()
    r = await db[COLL].update_one({"id": _sid(settimana_inizio)}, {"$set": {"stato": "bozza"}})
    if r.matched_count == 0:
        raise HTTPException(404, "Settimana non trovata")
    return {"ok": True, "stato": "bozza"}


# ============================================================================
# Griglia turni generata dal portale (motore client-side con le regole della
# pasticceria). Il responsabile genera nel browser e PUBBLICA qui; tutti la
# leggono. Storage semplice, una griglia per settimana.
# ============================================================================


# ============================================================
# TURNI AZIENDA NEL PORTALE — sola lettura della settimana REALE
# (stessa fonte della pagina Turni di gestione: assegnazioni_turni_cloud.
# Sostituisce la vecchia "griglia pubblicata" separata: un solo sistema.)
# ============================================================
GG_SETTIMANA = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
COLL_PREF = "turni_preferenze_riposo"


def _lunedi_corrente() -> str:
    oggi = datetime.now(timezone.utc).date()
    return (oggi - timedelta(days=oggi.weekday())).isoformat()


def _lunedi_prossimo() -> str:
    oggi = datetime.now(timezone.utc).date()
    return (oggi - timedelta(days=oggi.weekday()) + timedelta(days=7)).isoformat()


@router.get("/azienda/settimana", summary="Turni azienda della settimana (sola lettura, tutti)")
async def turni_azienda(settimana: str = "", identity: Dict[str, Any] = Depends(get_identity)):
    """La stessa settimana che si compone nella pagina Turni di gestione:
    ogni dipendente vede il proprio turno e quello di tutti i colleghi."""
    db = Database.get_db()
    settimana = settimana or _lunedi_corrente()
    assegnazioni = await db.assegnazioni_turni_cloud.find(
        {"settimana": settimana}, {"_id": 0}).to_list(2000)
    turni = await db.turni_cloud.find({}, {"_id": 0}).to_list(100)
    dipendenti = await db[Collections.EMPLOYEES].find(
        {"stato": "attivo", "merged_into": {"$exists": False}},
        {"_id": 0, "id": 1, "nome": 1, "cognome": 1, "nome_completo": 1}).to_list(500)
    # Chi può coprire il bar nelle sostituzioni (flag in turni_config, niente nomi
    # cablati) e chi sono i baristi in rotazione (per il campo "al posto di").
    sostituti = await db.turni_config.find(
        {"sostituto_bar": True}, {"_id": 0, "dipendente_id": 1}).to_list(100)
    baristi = await db.turni_config.find(
        {"rotazione": {"$nin": [None, ""]}}, {"_id": 0, "dipendente_id": 1}).to_list(100)
    return {"settimana": settimana, "assegnazioni": assegnazioni,
            "turni": turni, "dipendenti": dipendenti,
            "sostituti_bar": [s["dipendente_id"] for s in sostituti],
            "baristi_rotazione": [b["dipendente_id"] for b in baristi]}


COLL_DISP_BAR = "turni_disponibilita_bar"


@router.get("/disponibilita-bar", summary="Le mie disponibilità a coprire il bar")
async def mie_disponibilita_bar(identity: Dict[str, Any] = Depends(get_identity)):
    db = Database.get_db()
    oggi = datetime.now(timezone.utc).date().isoformat()
    return await db[COLL_DISP_BAR].find(
        {"dipendente_id": identity["id"], "al": {"$gte": oggi}},
        {"_id": 0}).sort("dal", 1).to_list(50)


@router.post("/disponibilita-bar", summary="Offro copertura al bar (dal-al + fascia)")
async def crea_disponibilita_bar(payload: Dict[str, Any] = Body(...),
                                 identity: Dict[str, Any] = Depends(get_identity)):
    """Un cameriere abilitato ('🆘 può coprire il bar' in Configura turni) offre
    la copertura del bar per un periodo, scegliendo la fascia (mattina/pomeriggio).
    'Genera settimana' lo mette al bar in quei giorni e riorganizza la sala."""
    db = Database.get_db()
    cfg = await db.turni_config.find_one(
        {"dipendente_id": identity["id"]}, {"_id": 0, "sostituto_bar": 1})
    if not (cfg or {}).get("sostituto_bar"):
        raise HTTPException(403, "Non sei abilitato alle sostituzioni bar (chiedilo in gestione)")
    dal = str(payload.get("dal") or "")[:10]
    al = str(payload.get("al") or "")[:10] or dal
    fascia = payload.get("fascia")
    try:
        d1 = datetime.strptime(dal, "%Y-%m-%d").date()
        d2 = datetime.strptime(al, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(400, "Date non valide (aaaa-mm-gg)")
    if d2 < d1:
        raise HTTPException(400, "'Al' è prima di 'Dal'")
    if fascia not in ("mattina", "pomeriggio"):
        raise HTTPException(400, "fascia: mattina o pomeriggio")
    dip = await db[Collections.EMPLOYEES].find_one(
        {"id": identity["id"]}, {"_id": 0, "nome": 1, "cognome": 1, "nome_completo": 1})
    nome = ((dip or {}).get("nome_completo")
            or f"{(dip or {}).get('cognome', '')} {(dip or {}).get('nome', '')}".strip()
            or identity.get("name") or "Dipendente")
    # "Al posto di": il barista assente che si sta coprendo (facoltativo ma
    # consigliato — così Genera settimana lo toglie dal calendario in quei giorni)
    sostituisce_id = payload.get("sostituisce_id") or None
    sostituisce_nome = None
    if sostituisce_id:
        ass = await db[Collections.EMPLOYEES].find_one(
            {"id": sostituisce_id}, {"_id": 0, "nome": 1, "cognome": 1, "nome_completo": 1})
        if not ass:
            raise HTTPException(400, "Dipendente da sostituire non trovato")
        sostituisce_nome = (ass.get("nome_completo")
                            or f"{ass.get('cognome', '')} {ass.get('nome', '')}".strip())
    doc = {"id": f"db_{uuid4().hex[:12]}", "dipendente_id": identity["id"], "nome": nome,
           "dal": dal, "al": al, "fascia": fascia,
           "sostituisce_id": sostituisce_id, "sostituisce_nome": sostituisce_nome,
           "creata_il": _now()}
    await db[COLL_DISP_BAR].insert_one(dict(doc))
    try:
        al_posto = f" al posto di {sostituisce_nome}" if sostituisce_nome else ""
        async for r in db[Collections.EMPLOYEES].find(
                {"ruolo_app": "responsabile_turni", "merged_into": {"$exists": False}},
                {"_id": 0, "id": 1}):
            if r["id"] != identity["id"]:
                await crea_notifica(
                    db, dipendente_id=r["id"], tipo="turni",
                    titolo="Disponibilità copertura bar",
                    messaggio=f"{nome} copre il bar ({fascia}){al_posto} dal {dal} al {al}: "
                              "rigenera la settimana in pagina Turni per applicarla.")
    except Exception:
        logger.warning("Notifica disponibilità bar non inviata")
    doc.pop("_id", None)
    return doc


@router.delete("/disponibilita-bar/{disp_id}", summary="Annulla una mia disponibilità")
async def annulla_disponibilita_bar(disp_id: str, identity: Dict[str, Any] = Depends(get_identity)):
    db = Database.get_db()
    r = await db[COLL_DISP_BAR].delete_one({"id": disp_id, "dipendente_id": identity["id"]})
    if r.deleted_count == 0:
        raise HTTPException(404, "Disponibilità non trovata")
    return {"ok": True}


@router.get("/preferenza-riposo", summary="La mia preferenza di riposo per la settimana")
async def mia_preferenza(settimana: str = "", identity: Dict[str, Any] = Depends(get_identity)):
    db = Database.get_db()
    settimana = settimana or _lunedi_prossimo()
    doc = await db[COLL_PREF].find_one(
        {"dipendente_id": identity["id"], "settimana": settimana}, {"_id": 0})
    return doc or {"dipendente_id": identity["id"], "settimana": settimana, "giorno": None}


@router.post("/preferenza-riposo", summary="Imposta la preferenza del giorno di riposo")
async def salva_preferenza(payload: Dict[str, Any] = Body(...),
                           identity: Dict[str, Any] = Depends(get_identity)):
    """Il dipendente indica dal portale il giorno di riposo preferito per la
    settimana (di norma la prossima): chi compone i turni la vede nella pagina
    Turni e riceve una notifica. giorno = null per togliere la preferenza."""
    db = Database.get_db()
    settimana = str(payload.get("settimana") or _lunedi_prossimo())
    giorno = payload.get("giorno") or None
    if giorno is not None and giorno not in GG_SETTIMANA:
        raise HTTPException(400, f"giorno non valido: usare uno tra {', '.join(GG_SETTIMANA)}")
    chiave = {"dipendente_id": identity["id"], "settimana": settimana}
    dip = await db[Collections.EMPLOYEES].find_one(
        {"id": identity["id"]}, {"_id": 0, "nome": 1, "cognome": 1, "nome_completo": 1})
    nome = ((dip or {}).get("nome_completo")
            or f"{(dip or {}).get('cognome', '')} {(dip or {}).get('nome', '')}".strip()
            or identity.get("name") or "Dipendente")
    if giorno is None:
        await db[COLL_PREF].delete_one(chiave)
    else:
        await db[COLL_PREF].update_one(
            chiave,
            {"$set": {**chiave, "giorno": giorno, "nome": nome, "aggiornata_il": _now()}},
            upsert=True)
    # Notifica chi fa i turni (responsabile turni; best-effort)
    try:
        msg = (f"{nome} preferisce riposare {giorno} nella settimana del {settimana}."
               if giorno else
               f"{nome} ha tolto la preferenza di riposo per la settimana del {settimana}.")
        async for r in db[Collections.EMPLOYEES].find(
                {"ruolo_app": "responsabile_turni", "merged_into": {"$exists": False}},
                {"_id": 0, "id": 1}):
            if r["id"] != identity["id"]:
                await crea_notifica(db, dipendente_id=r["id"], tipo="turni",
                                    titolo="Preferenza giorno di riposo", messaggio=msg)
    except Exception:
        logger.warning("Notifica preferenza riposo non inviata")
    return {"ok": True, "settimana": settimana, "giorno": giorno}
