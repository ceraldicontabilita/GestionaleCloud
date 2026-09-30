"""Presenze del mese per il consulente: un solo posto per foglio e registro degli invii.

L'invio delle presenze al commercialista si fa da due punti: il bottone «Invia» della
pagina Presenze di HR e il «Pacchetto da inviare» dell'Area Commercialista dell'ERP.
Entrambi passano da qui:

* il foglio (righe dipendente per giorno) e' costruito dal server con la stessa regola
  della griglia di HR (presenza salvata > ferie/permesso > turno; mai «presente» in un
  giorno futuro), cosi' l'email non dipende dal browser;
* il registro e' uno solo, ``presenze_invii`` (destinatario, data, esito, origine):
  dopo un invio riuscito, da qualunque parte, entrambe le pagine mostrano «Inviato il».

Il generatore PDF/CSV resta quello di ``routers/dipendenti_cloud`` (Opzione C).
"""
from __future__ import annotations

import calendar
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

COLLEZIONE_INVII = "presenze_invii"
ESITO_INVIATO = "inviato"
ESITO_ERRORE = "errore"
ORIGINI = ("hr", "erp")

_GIORNI_SETTIMANA = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
_CODICI_FERIE = {"Permesso": "PE", "Malattia": "M", "ROL": "R"}


def _db():
    from app.hr.database import Database

    return Database.get_db()


def _lunedi(giorno: date) -> str:
    return (giorno - timedelta(days=giorno.weekday())).isoformat()


def _oggi_roma() -> date:
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo("Europe/Rome")).date()


def _in_forza(dip: Dict[str, Any], primo_giorno: str) -> bool:
    """In forza nel mese: rapporto in corso, oppure cessato dal primo giorno in poi."""
    from app.hr.services import stato_rapporto

    if "merged_into" in dip:
        return False
    if stato_rapporto.e_in_forza(dip):
        return True
    fine = stato_rapporto.data_fine_rapporto(dip)
    return bool(fine and fine >= primo_giorno)


def codice_giorno(giorno: date, dip_id: str, *, presenza: Optional[Dict[str, Any]],
                  ferie: Sequence[Dict[str, Any]], turno_nome: Optional[str],
                  oggi: date) -> Optional[str]:
    """Il codice della cella, identico a ``codiceDerivato`` della griglia HR.

    ``presenza`` salvata > ferie/permesso/malattia/ROL > turno. Un giorno futuro non e'
    mai «presente». ``turno_nome`` e' il nome del tipo di turno assegnato quel giorno.
    """
    futuro = giorno > oggi
    if presenza:
        g = presenza.get("giustificativo")
        if g == "P" or (not g and presenza.get("stato") == "presente"):
            return None if futuro else "P"
        if g:
            return str(g)
        if presenza.get("stato") == "assente":
            return "AS"
        return None
    iso = giorno.isoformat()
    for f in ferie:
        if f.get("dipendente_id") == dip_id and str(f.get("data_inizio") or "") <= iso \
                and str(f.get("data_fine") or f.get("data_inizio") or "") >= iso:
            return _CODICI_FERIE.get(f.get("tipo"), "F")
    if turno_nome:
        if turno_nome == "Riposo":
            return "RS"
        if turno_nome == "Ferie":
            return "F"
        return None if futuro else "P"
    return None


def _nota_giorno(iso: str, dip_id: str, presenza: Optional[Dict[str, Any]],
                 ferie: Sequence[Dict[str, Any]]) -> str:
    if presenza and (presenza.get("note") or presenza.get("nota")):
        return str(presenza.get("note") or presenza.get("nota"))
    for f in ferie:
        if f.get("dipendente_id") == dip_id and str(f.get("data_inizio") or "") <= iso \
                and str(f.get("data_fine") or f.get("data_inizio") or "") >= iso:
            return str(f.get("note") or f.get("protocollo") or "")
    return ""


async def righe_presenze_mese(anno: int, mese: int, *, oggi: Optional[date] = None) -> Dict[str, Any]:
    """Il foglio del mese: ``{giorni, righe: [{nome, celle, note}]}`` come lo costruisce HR."""
    from app.hr.routers import dipendenti_cloud as hr

    db = _db()
    oggi = oggi or _oggi_roma()
    giorni = calendar.monthrange(anno, mese)[1]
    primo = date(anno, mese, 1).isoformat()

    dipendenti = await db.dipendenti.find(
        {"merged_into": {"$exists": False}},
        {"_id": 0, "id": 1, "nome": 1, "cognome": 1, "nome_completo": 1, "stato": 1, "attivo": 1,
         "in_carico": 1, "data_fine_rapporto": 1, "data_cessazione": 1, "data_dimissione": 1,
         "data_cessazione_prevista": 1},
    ).to_list(1000)
    dipendenti = sorted(
        (d for d in dipendenti if _in_forza(d, primo)),
        key=lambda d: (str(d.get("cognome") or "").lower(), str(d.get("nome") or "").lower()),
    )

    # Le stesse quattro letture della pagina Presenze di HR, per le funzioni HR gia' esistenti.
    presenze = await hr.get_presenze(anno=anno, mese=mese, dipendente_id=None)
    per_giorno = {}
    for p in presenze:
        per_giorno.setdefault((p.get("dipendente_id"), p.get("data")), p)
    ferie = await db.ferie_cloud.find({}, {"_id": 0}).to_list(1000)
    tipi = {t.get("id"): t.get("nome") for t in await db.turni_cloud.find({}, {"_id": 0}).to_list(100)}
    settimane = sorted({_lunedi(date(anno, mese, g)) for g in range(1, giorni + 1)})
    assegnazioni = await db.assegnazioni_turni_cloud.find(
        {"settimana": {"$in": settimane}}, {"_id": 0}).to_list(8000)
    turno = {(a.get("dipendente_id"), a.get("settimana"), a.get("giorno")): tipi.get(a.get("turno_id"))
             for a in assegnazioni}

    righe: List[Dict[str, Any]] = []
    for dip in dipendenti:
        dip_id = dip.get("id")
        celle, note = [], []
        for g in range(1, giorni + 1):
            giorno = date(anno, mese, g)
            iso = giorno.isoformat()
            presenza = per_giorno.get((dip_id, iso))
            nome_turno = turno.get((dip_id, _lunedi(giorno), _GIORNI_SETTIMANA[giorno.weekday()]))
            celle.append(codice_giorno(giorno, dip_id, presenza=presenza, ferie=ferie,
                                       turno_nome=nome_turno, oggi=oggi) or "")
            note.append(_nota_giorno(iso, dip_id, presenza, ferie))
        nome = f"{dip.get('cognome') or ''} {dip.get('nome') or ''}".strip() \
            or str(dip.get("nome_completo") or "")
        righe.append({"nome": nome, "celle": celle, "note": note})
    return {"giorni": giorni, "righe": righe}


def ha_presenze(righe: Sequence[Dict[str, Any]]) -> bool:
    """Il foglio ha almeno un giorno con un codice (presenza, ferie, riposo...)."""
    return any(c for r in righe for c in (r.get("celle") or []))


async def mese_ha_presenze(anno: int, mese: int) -> bool:
    """Controllo leggero (senza costruire il foglio): presenze, turni o ferie nel mese."""
    db = _db()
    prefisso = f"{anno}-{mese:02d}"
    if await db.presenze_cloud.find_one({"data": {"$regex": f"^{prefisso}"}}, {"_id": 0, "id": 1}):
        return True
    if await db.presenze.find_one({"anno": anno, "mese": mese}, {"_id": 0, "id": 1}):
        return True
    giorni = calendar.monthrange(anno, mese)[1]
    settimane = sorted({_lunedi(date(anno, mese, g)) for g in range(1, giorni + 1)})
    if await db.assegnazioni_turni_cloud.find_one(
            {"settimana": {"$in": settimane}}, {"_id": 0, "id": 1}):
        return True
    fine = f"{prefisso}-{giorni:02d}"
    ferie = await db.ferie_cloud.find({}, {"_id": 0, "data_inizio": 1, "data_fine": 1}).to_list(1000)
    return any(str(f.get("data_inizio") or "") <= fine
               and str(f.get("data_fine") or f.get("data_inizio") or "") >= f"{prefisso}-01"
               for f in ferie)


async def invii_presenze(anno: int, mese: int) -> List[Dict[str, Any]]:
    """Gli invii riusciti del mese, dal piu' recente. Un errore non conta come inviato."""
    invii = await _db().presenze_invii.find(
        {"anno": int(anno), "mese": int(mese)}, {"_id": 0}).sort("data_invio", -1).to_list(500)
    return [i for i in invii if i.get("esito", ESITO_INVIATO) == ESITO_INVIATO]


async def registra_invio(anno: int, mese: int, destinatario: str, *, n_dipendenti: int,
                         con_pdf: bool, origine: str, esito: str = ESITO_INVIATO,
                         errore: Optional[str] = None) -> Dict[str, Any]:
    """Scrive l'invio nel registro unico. ``errore`` e' solo il nome del tipo di eccezione."""
    from app.hr.routers.dipendenti_cloud import _MESI_PRES

    if origine not in ORIGINI:
        raise ValueError(f"origine sconosciuta: {origine}")
    rec = {
        "id": str(uuid.uuid4()), "anno": int(anno), "mese": int(mese),
        "periodo": f"{_MESI_PRES[mese - 1]} {anno}", "destinatario": destinatario,
        "data_invio": datetime.now(timezone.utc).isoformat(), "n_dipendenti": n_dipendenti,
        "con_pdf": bool(con_pdf), "esito": esito, "origine": origine,
    }
    if errore:
        rec["errore"] = errore
    await _db().presenze_invii.insert_one(dict(rec))
    return rec


def allegati_presenze(anno: int, mese: int, giorni: int,
                      righe: Sequence[Dict[str, Any]]) -> List[Tuple[bytes, str, str, str]]:
    """PDF riepilogo + CSV, con gli stessi nomi file dell'invio dalla pagina HR."""
    from app.hr.routers.dipendenti_cloud import _csv_presenze, _pdf_riepilogo_periodi

    base = f"presenze_{anno}_{str(mese).zfill(2)}"
    allegati: List[Tuple[bytes, str, str, str]] = []
    try:
        allegati.append((_pdf_riepilogo_periodi(anno, mese, giorni, list(righe)),
                         "application", "pdf", f"{base}.pdf"))
    except Exception as exc:  # noqa: BLE001 - il CSV parte comunque, come da HR
        logger.warning("PDF presenze %s/%s non generato: %s", anno, mese, type(exc).__name__)
    allegati.append((_csv_presenze(anno, mese, giorni, list(righe)).encode("utf-8"),
                     "text", "csv", f"{base}.csv"))
    return allegati
