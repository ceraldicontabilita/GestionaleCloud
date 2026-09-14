"""Registro dei giorni di CHIUSURA dell'attivita' (ferie, ristrutturazione).

Richiesta del titolare (14/09/2026): il bar e' rimasto chiuso dal 26 gennaio
all'8 marzo 2026 per ristrutturazione (febbraio compreso) e dal 15 al 23
agosto per ferie. Un giorno di chiusura NON e' un corrispettivo mancante: il
registratore telematico, il giorno della riapertura, dichiara all'Agenzia
delle Entrate il periodo di inattivita' ("Periodo di inattivita' da/a" nel
tracciato AdE) e le presenze HR mostrano tutti i dipendenti in ferie.

Una sola collezione, ``chiusure_attivita``::

    {id, data_inizio, data_fine, motivo, fonte, riferimento, note, created_at}

``fonte``: ``titolare`` (periodi confermati a voce dal titolare, seminati da
``PERIODI_CONFERMATI``), ``ade_inattivita`` (colonne del CSV AdE importato in
``/api/corrispettivi/import-csv``), ``presenze_hr`` (giorno in cui almeno
``QUOTA_FERIE_CHIUSURA`` dei dipendenti attivi e' in ferie e non c'e' alcun
corrispettivo), ``manuale`` (registrata dalla pagina).

Chi calcola "giorni senza corrispettivo" (``iva_liquidation_query``) toglie
questi giorni: restano segnalati solo i giorni davvero non caricati.
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Set

logger = logging.getLogger(__name__)

COLLEZIONE = "chiusure_attivita"
QUOTA_FERIE_CHIUSURA = 0.8  # 80% dei dipendenti attivi in ferie = negozio chiuso

# Periodi confermati dal titolare il 14/09/2026 (chat): non sono una
# dimenticanza dell'import, il negozio era chiuso. La ristrutturazione e' un
# unico periodo continuo 26/01 -> 08/03 (febbraio compreso): lo confermano le
# transazioni POS in produzione, ultima il 25/01 e prima riapertura il 09/03.
PERIODI_CONFERMATI = (
    ("2026-01-26", "2026-03-08", "ristrutturazione"),
    ("2026-08-15", "2026-08-23", "ferie"),
)


def _iso(valore: Any) -> Optional[str]:
    if isinstance(valore, (date, datetime)):
        return valore.strftime("%Y-%m-%d")
    testo = str(valore or "").strip()
    if len(testo) >= 10 and testo[4] == "-" and testo[7] == "-":
        return testo[:10]
    for sep in ("/", "-", "."):
        parti = testo[:10].split(sep)
        if len(parti) == 3 and len(parti[2]) == 4:
            try:
                return "%s-%02d-%02d" % (parti[2], int(parti[1]), int(parti[0]))
            except ValueError:
                return None
    return None


def giorni_del_periodo(inizio: str, fine: str) -> List[str]:
    a, b = date.fromisoformat(inizio), date.fromisoformat(fine)
    if b < a:
        a, b = b, a
    return [(a + timedelta(days=i)).isoformat() for i in range((b - a).days + 1)]


async def registra_chiusura(db, inizio: Any, fine: Any, motivo: str, fonte: str,
                            riferimento: Optional[str] = None, note: str = "") -> Dict[str, Any]:
    """Inserisce il periodo se non esiste gia' (stesso inizio/fine); idempotente."""
    inizio_iso, fine_iso = _iso(inizio), _iso(fine) or _iso(inizio)
    if not inizio_iso or not fine_iso:
        raise ValueError("date di chiusura non valide")
    if fine_iso < inizio_iso:
        inizio_iso, fine_iso = fine_iso, inizio_iso
    esistente = await db[COLLEZIONE].find_one(
        {"data_inizio": inizio_iso, "data_fine": fine_iso}, {"_id": 0})
    if esistente:
        return {**esistente, "gia_presente": True}
    doc = {
        "id": str(uuid.uuid4()), "data_inizio": inizio_iso, "data_fine": fine_iso,
        "motivo": (motivo or "chiusura").strip().lower(), "fonte": fonte,
        "riferimento": riferimento, "note": note or "",
        "giorni": len(giorni_del_periodo(inizio_iso, fine_iso)),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db[COLLEZIONE].insert_one(dict(doc))
    logger.info("[CHIUSURE] registrata %s -> %s (%s, %s)", inizio_iso, fine_iso, doc["motivo"], fonte)
    return {**doc, "gia_presente": False}


async def elenca_chiusure(db, anno: Optional[int] = None) -> List[Dict[str, Any]]:
    filtro: Dict[str, Any] = {}
    if anno:
        filtro = {"data_inizio": {"$lte": f"{anno}-12-31"}, "data_fine": {"$gte": f"{anno}-01-01"}}
    righe = await db[COLLEZIONE].find(filtro, {"_id": 0}).to_list(1000)
    righe.sort(key=lambda r: r.get("data_inizio") or "")
    return righe


async def giorni_chiusi(db, da: str, a: str) -> Set[str]:
    """Insieme dei giorni ``YYYY-MM-DD`` in chiusura nell'intervallo [da, a]."""
    periodi = await db[COLLEZIONE].find(
        {"data_inizio": {"$lte": a}, "data_fine": {"$gte": da}}, {"_id": 0}).to_list(1000)
    giorni: Set[str] = set()
    for p in periodi:
        for g in giorni_del_periodo(p["data_inizio"], p["data_fine"]):
            if da <= g <= a:
                giorni.add(g)
    return giorni


async def elimina_chiusura(db, chiusura_id: str) -> bool:
    res = await db[COLLEZIONE].delete_one({"id": chiusura_id})
    return bool(getattr(res, "deleted_count", 0))


async def semina_periodi_confermati(db) -> int:
    nuovi = 0
    for inizio, fine, motivo in PERIODI_CONFERMATI:
        esito = await registra_chiusura(db, inizio, fine, motivo, "titolare",
                                        note="confermato dal titolare il 14/09/2026")
        nuovi += 0 if esito.get("gia_presente") else 1
    return nuovi


def _db_hr():
    try:
        from app.hr.database import Database, DatabaseNonConfigurato
    except Exception:  # pragma: no cover - modulo HR assente
        return None
    db_hr = Database.get_db()
    if db_hr is None or isinstance(db_hr, DatabaseNonConfigurato):
        return None
    return db_hr


def _giorni_ferie_collettive(presenze: Iterable[Dict[str, Any]], dipendenti_attivi: int) -> Set[str]:
    """Giorni in cui almeno QUOTA_FERIE_CHIUSURA dei dipendenti attivi e' in ferie."""
    if dipendenti_attivi <= 0:
        return set()
    per_giorno: Dict[str, Set[str]] = {}
    for p in presenze:
        giust = str(p.get("giustificativo") or "").strip().upper()
        stato = str(p.get("stato") or "").strip().lower()
        if giust == "F" or (stato == "giustificato" and giust in {"", "F", "FERIE"}):
            giorno = _iso(p.get("data"))
            if giorno and p.get("dipendente_id"):
                per_giorno.setdefault(giorno, set()).add(str(p["dipendente_id"]))
    soglia = max(1, int(round(dipendenti_attivi * QUOTA_FERIE_CHIUSURA)))
    return {g for g, dips in per_giorno.items() if len(dips) >= soglia}


def _raggruppa_in_periodi(giorni: Set[str]) -> List[tuple]:
    """Giorni consecutivi -> (inizio, fine)."""
    periodi: List[tuple] = []
    for g in sorted(giorni):
        if periodi and (date.fromisoformat(g) - date.fromisoformat(periodi[-1][1])).days == 1:
            periodi[-1] = (periodi[-1][0], g)
        else:
            periodi.append((g, g))
    return periodi


async def rileva_chiusure_da_presenze_hr(db, da: Optional[str] = None, a: Optional[str] = None) -> Dict[str, Any]:
    """Ferie collettive nelle presenze HR senza alcun corrispettivo = chiusura.

    Legge il database HR in-process (stesso schema dell'app HR); se non e'
    configurato non fa nulla. Idempotente: registra solo periodi nuovi.
    """
    db_hr = _db_hr()
    if db_hr is None:
        return {"esito": "hr_non_configurato", "nuovi": 0}
    oggi = date.today()
    da = da or (oggi - timedelta(days=400)).isoformat()
    a = a or oggi.isoformat()
    attivi = await db_hr.dipendenti.find(
        {"attivo": True, "merged_into": {"$exists": False}}, {"_id": 0, "id": 1}).to_list(1000)
    presenze = await db_hr.presenze_cloud.find(
        {"data": {"$gte": da, "$lte": a}}, {"_id": 0, "data": 1, "dipendente_id": 1,
                                             "stato": 1, "giustificativo": 1}).to_list(100000)
    candidati = _giorni_ferie_collettive(presenze, len(attivi))
    if not candidati:
        return {"esito": "ok", "nuovi": 0, "giorni_candidati": 0}
    con_corrispettivo = {
        str(c.get("data") or "")[:10]
        for c in await db["corrispettivi"].find(
            {"data": {"$gte": min(candidati), "$lte": max(candidati)}}, {"_id": 0, "data": 1}).to_list(5000)
    }
    giorni = {g for g in candidati if g not in con_corrispettivo}
    nuovi = 0
    for inizio, fine in _raggruppa_in_periodi(giorni):
        esito = await registra_chiusura(db, inizio, fine, "ferie", "presenze_hr",
                                        note=f"ferie collettive nelle presenze HR ({len(attivi)} dipendenti attivi)")
        nuovi += 0 if esito.get("gia_presente") else 1
    return {"esito": "ok", "nuovi": nuovi, "giorni_candidati": len(candidati), "giorni_chiusura": len(giorni)}


async def aggiorna_registro_chiusure(db) -> Dict[str, Any]:
    """Giro periodico: semina i periodi confermati + rileva le ferie collettive."""
    seminati = await semina_periodi_confermati(db)
    presenze = await rileva_chiusure_da_presenze_hr(db)
    return {"seminati": seminati, **presenze}
