"""
Timbrature con geolocalizzazione — portale dipendente.

Il dipendente timbra entrata/uscita dal telefono; il browser fornisce la
posizione (lat/lng). Se è configurata una sede di lavoro si calcola la distanza
(geofencing) e si segnala la timbratura "fuori sede".

A→B: la timbratura alimenta le PRESENZE reali (collezione presenze_cloud, la
stessa mostrata in gestione): entrata → presente; uscita → ore lavorate calcolate.
"""
from fastapi import APIRouter, HTTPException, Body, Query, Depends
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import uuid
import math
import logging

from app.hr.database import Database, Collections
from app.hr.utils.identity import get_identity, require_roles

logger = logging.getLogger(__name__)
router = APIRouter()

COLL = "timbrature"
COLL_SET = "impostazioni"
RAGGIO_DEFAULT_M = 200
MARGINE_GPS_MAX_M = 75  # tolleranza massima sull'accuracy dichiarata dal client
MIN_PERMANENZA_MIN = 60  # permanenza minima in sede perché la presenza sia validata


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _haversine_m(lat1, lon1, lat2, lon2) -> float:
    """Distanza in metri tra due coordinate (formula dell'emisenoverso)."""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


async def _sede(db):
    return await db[COLL_SET].find_one({"chiave": "sede_lavoro"}, {"_id": 0})


@router.post("", summary="Timbra entrata/uscita (dipendente)")
async def timbra(payload: Dict[str, Any] = Body(...),
                 identity: Dict[str, Any] = Depends(get_identity)) -> Dict[str, Any]:
    tipo = str(payload.get("tipo", "")).strip()
    if tipo not in ("entrata", "uscita"):
        raise HTTPException(400, "tipo deve essere 'entrata' o 'uscita'")
    db = Database.get_db()
    now = _now()
    oggi = now.strftime("%Y-%m-%d")
    lat, lng = payload.get("lat"), payload.get("lng")
    accuracy = payload.get("accuracy")

    # Ultima timbratura di oggi: evita doppioni e impone l'ordine entrata→uscita
    ultima = await db[COLL].find_one(
        {"dipendente_id": identity["id"], "data": oggi}, {"_id": 0}, sort=[("ts", -1)])
    if ultima and ultima.get("tipo") == tipo:
        raise HTTPException(409, f"Hai già timbrato l'{tipo}. Timbra l'azione opposta.")
    if tipo == "uscita" and not ultima:
        raise HTTPException(409, "Devi prima timbrare l'entrata.")

    # Geofencing
    distanza_m = None
    fuori_sede = None
    sede = await _sede(db)
    raggio = int((sede or {}).get("raggio_m") or RAGGIO_DEFAULT_M)
    if sede and sede.get("lat") is not None:
        if lat is None or lng is None:
            # Sede attiva ma posizione assente
            if sede.get("blocca_fuori_sede"):
                raise HTTPException(403, "Posizione non disponibile: attiva il GPS e consenti la "
                                         "localizzazione per timbrare in sede.")
            fuori_sede = True
        else:
            try:
                la, lo = float(lat), float(lng)
                if not (-90 <= la <= 90 and -180 <= lo <= 180):
                    raise ValueError("coordinate fuori range")
                distanza_m = round(_haversine_m(la, lo, float(sede["lat"]), float(sede["lng"])))
                # Tolleranza per l'imprecisione GPS, ma CAPPATA: un client malevolo
                # non può dichiarare accuracy enorme per aggirare il geofence.
                margine = 0
                if isinstance(accuracy, (int, float)) and accuracy > 0:
                    margine = min(int(accuracy), MARGINE_GPS_MAX_M)
                fuori_sede = max(0, distanza_m - margine) > raggio
            except (ValueError, TypeError):
                distanza_m = None
                fuori_sede = bool(sede.get("blocca_fuori_sede"))
        if fuori_sede and sede.get("blocca_fuori_sede"):
            raise HTTPException(403,
                f"Sei fuori sede ({'~' + str(distanza_m) + ' m dalla sede' if distanza_m is not None else 'posizione non valida'}). "
                f"La timbratura è ammessa solo presso {sede.get('nome') or 'la sede di lavoro'}.")

    nome = identity.get("name") or ""
    if not nome:
        dip = await db[Collections.EMPLOYEES].find_one({"id": identity["id"]}, {"_id": 0, "nome_completo": 1})
        nome = (dip or {}).get("nome_completo", "")

    rec = {
        "id": f"tmb_{uuid.uuid4().hex[:12]}",
        "dipendente_id": identity["id"],
        "dipendente_nome": nome,
        "tipo": tipo,
        "data": oggi,
        "ora": now.strftime("%H:%M"),
        "ts": now.isoformat(),
        "lat": lat, "lng": lng, "accuracy": accuracy,
        "distanza_m": distanza_m, "fuori_sede": fuori_sede,
    }
    await db[COLL].insert_one(rec.copy())
    rec.pop("_id", None)

    # A→B: aggiorna la presenza reale del giorno (presenze_cloud)
    ore = None
    base = {"dipendente_id": identity["id"], "data": oggi, "stato": "presente",
            "giustificativo": "P", "origine": "timbratura"}
    if tipo == "entrata":
        base["entrata"] = rec["ora"]
        # Presenza ancora NON validata: serve l'uscita in sede dopo almeno 1 ora.
        base["validata"] = False
    else:
        base["uscita"] = rec["ora"]
        if ultima:
            base["entrata"] = ultima.get("ora")
            try:
                t_in = datetime.fromisoformat(ultima["ts"])
                minuti = (now - t_in).total_seconds() / 60
                ore = round(minuti / 60, 2)
                base["ore_lavorate"] = ore
                base["minuti"] = round(minuti)
                # Presenza VALIDA solo se: entrata in sede + uscita in sede + permanenza ≥ 1 ora.
                entrata_in_sede = not bool(ultima.get("fuori_sede"))
                uscita_in_sede = not bool(fuori_sede)
                base["validata"] = bool(entrata_in_sede and uscita_in_sede and minuti >= MIN_PERMANENZA_MIN)
            except (ValueError, TypeError, KeyError):
                ore = None
                base["validata"] = False
        else:
            base["validata"] = False
    await db["presenze_cloud"].update_one(
        {"dipendente_id": identity["id"], "data": oggi}, {"$set": base}, upsert=True)

    return {"ok": True, "timbratura": rec, "ore_lavorate": ore, "fuori_sede": fuori_sede,
            "validata": base.get("validata", False)}


@router.get("/mie/oggi", summary="Le mie timbrature di oggi + stato")
async def mie_oggi(identity: Dict[str, Any] = Depends(get_identity)) -> Dict[str, Any]:
    db = Database.get_db()
    oggi = _now().strftime("%Y-%m-%d")
    ts = await db[COLL].find({"dipendente_id": identity["id"], "data": oggi}, {"_id": 0}).sort("ts", 1).to_list(50)
    stato = "dentro" if (ts and ts[-1]["tipo"] == "entrata") else "fuori"
    return {"data": oggi, "stato": stato, "timbrature": ts}


@router.get("", summary="Timbrature (admin/responsabile)")
async def lista(data: Optional[str] = Query(None), dipendente_id: Optional[str] = Query(None),
                identity: Dict[str, Any] = Depends(require_roles("admin", "responsabile_turni"))) -> Dict[str, Any]:
    db = Database.get_db()
    q: Dict[str, Any] = {}
    if data:
        q["data"] = data
    if dipendente_id:
        q["dipendente_id"] = dipendente_id
    if not data and not dipendente_id:
        q["data"] = _now().strftime("%Y-%m-%d")
    ts = await db[COLL].find(q, {"_id": 0}).sort("ts", -1).to_list(2000)
    return {"totale": len(ts), "timbrature": ts}


@router.get("/riepilogo", summary="Riepilogo ore mensili per dipendente (admin)")
async def riepilogo(anno: int = Query(...), mese: int = Query(...),
                    identity: Dict[str, Any] = Depends(require_roles("admin", "responsabile_turni"))) -> Dict[str, Any]:
    """Totale ore timbrate e giorni lavorati nel mese, per dipendente
    (utile per il controllo delle buste paga)."""
    db = Database.get_db()
    prefix = f"{anno}-{str(mese).zfill(2)}"
    ts = await db[COLL].find({"data": {"$regex": f"^{prefix}"}}, {"_id": 0}).sort("ts", 1).to_list(20000)
    by: Dict[str, Any] = {}
    for t in ts:
        dip = t["dipendente_id"]
        rec = by.setdefault(dip, {"dipendente_id": dip, "nome": t.get("dipendente_nome", ""), "giorni": {}})
        g = rec["giorni"].setdefault(t["data"], {"in": None, "out": None})
        if t["tipo"] == "entrata" and not g["in"]:
            g["in"] = t["ts"]
        if t["tipo"] == "uscita":
            g["out"] = t["ts"]
    out = []
    for rec in by.values():
        tot, gg = 0.0, 0
        for g in rec["giorni"].values():
            if g["in"] and g["out"]:
                try:
                    h = (datetime.fromisoformat(g["out"]) - datetime.fromisoformat(g["in"])).total_seconds() / 3600
                    if h > 0:
                        tot += h
                        gg += 1
                except (ValueError, TypeError):
                    pass
        out.append({"dipendente_id": rec["dipendente_id"], "nome": rec["nome"],
                    "ore": round(tot, 2), "giorni": gg})
    out.sort(key=lambda x: (x["nome"] or "").lower())
    return {"anno": anno, "mese": mese, "riepilogo": out}


@router.get("/sede", summary="Sede di lavoro configurata")
async def get_sede(identity: Dict[str, Any] = Depends(get_identity)) -> Dict[str, Any]:
    db = Database.get_db()
    return (await _sede(db)) or {}


@router.post("/sede", summary="Imposta la sede per il geofencing (admin)")
async def imposta_sede(payload: Dict[str, Any] = Body(...),
                       identity: Dict[str, Any] = Depends(require_roles("admin"))) -> Dict[str, Any]:
    db = Database.get_db()
    try:
        lat = float(payload["lat"]); lng = float(payload["lng"])
    except (KeyError, ValueError, TypeError):
        raise HTTPException(400, "lat e lng obbligatori e numerici")
    raggio = int(payload.get("raggio_m") or RAGGIO_DEFAULT_M)
    await db[COLL_SET].update_one(
        {"chiave": "sede_lavoro"},
        {"$set": {"chiave": "sede_lavoro", "lat": lat, "lng": lng, "raggio_m": raggio,
                  "nome": payload.get("nome", ""), "indirizzo": payload.get("indirizzo", ""),
                  "blocca_fuori_sede": bool(payload.get("blocca_fuori_sede", True))}},
        upsert=True)
    return {"ok": True, "lat": lat, "lng": lng, "raggio_m": raggio,
            "blocca_fuori_sede": bool(payload.get("blocca_fuori_sede", True))}
