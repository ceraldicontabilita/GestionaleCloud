"""Manutenzione del libro giornale (audit 27/09/2026, punti 4, 5 e 6).

Due giri, entrambi ``dry_run`` per difetto, in sottofondo con lo stato in
``sistema_stato`` (oltre i 5 minuti il proxy Render taglia la richiesta):

- ``rettifica_scritture_fatture``: le scritture di fattura acquisto
  SQUADRATE (DARE diverso da AVERE: 57 in produzione) o senza ``anno``
  (19) non si cancellano: si STORNANO con il motore unico
  (``registrazione_contabile._scrivi_storno``) e la fattura si registra di
  nuovo con il motore corretto, che ora rifiuta di salvare una scrittura che
  non quadra (esito ``da_verificare`` annotato sulla fattura, mai una
  quadratura d'ufficio). Idempotente: una scrittura gia' stornata non e'
  piu' candidata, e una rettifica interrotta fra storno e nuova
  registrazione si riprende al giro dopo.
- ``censisci_scritture_cancellate``: le scritture marcate ``deleted: true``
  (15 doppioni) restano FUORI dal giornale (``FILTRO_SCRITTURA_ATTIVA``) e
  non si cancellano di nuovo. Il giro le elenca con la scrittura attiva
  dello stesso documento, se c'e'; in applicazione annota su ognuna
  ``annullata_come_doppione`` (con ``duplicato_di``) oppure
  ``documento_senza_scrittura_attiva``: nessun conto si muove.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.constants.fattura_attiva import fattura_attiva
from app.services.registrazione_contabile import (
    FILTRO_SCRITTURA_ATTIVA,
    COLL_MOVIMENTI,
    _annota_esito,
    _audit,
    _scrivi_storno,
    registra_fattura,
    scrittura_attiva,
    scrittura_quadrata,
    totali_righe,
)
from app.utils.id_fattura import filtro_id

logger = logging.getLogger(__name__)

_STATO_RETTIFICA = "manutenzione_giornale_rettifica_fatture"
_STATO_CANCELLATE = "manutenzione_giornale_scritture_cancellate"
_locks: Dict[str, asyncio.Lock] = {}
_tasks: Dict[str, asyncio.Task] = {}
_PAUSA = 0.1

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fattura_attiva(fattura: Dict[str, Any]) -> bool:
    """Criterio unico di fattura attiva, piu' la collisione ancora da
    verificare che anche il recupero del pregresso tiene fuori: una fattura
    archiviata o cancellata si storna ma non si registra di nuovo."""
    return fattura_attiva(fattura) and fattura.get("duplicate_review_required") is not True


def motivi_rettifica(scrittura: Dict[str, Any]) -> List[str]:
    """Perche' una scrittura di fattura va rettificata (vuoto = va bene)."""
    motivi = []
    if not scrittura_quadrata(scrittura.get("righe") or []):
        motivi.append("non_quadrata")
    if scrittura.get("anno") in (None, ""):
        motivi.append("senza_anno")
    return motivi


def _voce(scrittura: Dict[str, Any], motivi: List[str]) -> Dict[str, Any]:
    dare, avere = totali_righe(scrittura.get("righe") or [])
    return {
        "movimento_id": scrittura.get("id"),
        "numero_registrazione": scrittura.get("numero_registrazione"),
        "anno": scrittura.get("anno"),
        "data": scrittura.get("data_documento") or scrittura.get("data"),
        "fattura_id": scrittura.get("fattura_id"),
        "descrizione": scrittura.get("descrizione"),
        "dare": dare, "avere": avere, "differenza": round(dare - avere, 2),
        "motivi": motivi,
    }


async def _scritture_fattura(db) -> List[Dict[str, Any]]:
    return await db[COLL_MOVIMENTI].find(
        {"tipo": "fattura_acquisto"}, {"_id": 0}).to_list(None)


async def _riregistra(db, fattura_id: str) -> Dict[str, Any]:
    fattura = await db["invoices"].find_one(filtro_id(fattura_id), {"_id": 0})
    if not fattura:
        return {"stato": "saltato", "motivo": "fattura non piu' in archivio"}
    if not _fattura_attiva(fattura):
        return {"stato": "saltato", "motivo": "fattura non attiva: resta solo lo storno"}
    # La fattura ha gia' un'altra scrittura valida (doppione registrato due
    # volte, o rettifica gia' ripresa dal pregresso): una terza no.
    valida = await db[COLL_MOVIMENTI].find_one(
        {"tipo": "fattura_acquisto", "fattura_id": fattura_id,
         "stato": {"$ne": "stornato"}, **FILTRO_SCRITTURA_ATTIVA},
        {"_id": 0, "id": 1})
    if valida:
        await db["invoices"].update_one(filtro_id(fattura_id), {"$set": {
            "registrata_contabilita": True, "movimento_contabile_id": valida.get("id")}})
        return {"stato": "gia_registrato", "movimento_id": valida.get("id")}
    esito = await registra_fattura(db, fattura, force=True)
    await _annota_esito(db, "invoices", fattura_id, esito)
    return esito


async def rettifica_scritture_fatture(db, *, dry_run: bool = True,
                                      pausa: float = 0.0) -> Dict[str, Any]:
    """Storna e registra di nuovo le scritture di fattura squadrate o senza anno."""
    scritture = await _scritture_fattura(db)
    valide_per_fattura: Dict[str, List[Dict[str, Any]]] = {}
    for s in scritture:
        if s.get("stato") != "stornato" and scrittura_attiva(s) and s.get("fattura_id"):
            valide_per_fattura.setdefault(str(s["fattura_id"]), []).append(s)

    candidati = []
    for s in scritture:
        if s.get("stato") == "stornato" or not scrittura_attiva(s):
            continue
        motivi = motivi_rettifica(s)
        if motivi:
            candidati.append((s, motivi))
    # Rettifiche interrotte fra storno e nuova registrazione: la fattura non
    # ha piu' nessuna scrittura valida e la rettifica non ha un esito.
    in_sospeso = [
        s for s in scritture
        if s.get("stato") == "stornato" and (s.get("rettifica_contabile") or {})
        and not (s["rettifica_contabile"].get("esito_riregistrazione"))
        and not valide_per_fattura.get(str(s.get("fattura_id")))
    ]

    risultato: Dict[str, Any] = {
        "dry_run": dry_run,
        "candidate": len(candidati),
        "non_quadrate": sum(1 for _, m in candidati if "non_quadrata" in m),
        "senza_anno": sum(1 for _, m in candidati if "senza_anno" in m),
        "differenza_totale": round(sum(_voce(s, m)["differenza"] for s, m in candidati), 2),
        "rettifiche_in_sospeso": len(in_sospeso),
        "dettaglio": [_voce(s, m) for s, m in candidati][:200],
    }
    if dry_run:
        return risultato

    stornate, esiti, errori = 0, [], []
    for scrittura, motivi in candidati:
        fattura_id = str(scrittura.get("fattura_id") or "")
        motivo = "rettifica: " + ", ".join(
            {"non_quadrata": "scrittura non quadrata (DARE diverso da AVERE)",
             "senza_anno": "scrittura senza anno di registrazione"}[m] for m in motivi)
        try:
            storno = await _scrivi_storno(
                db, scrittura, motivo, "storno_fattura_acquisto",
                {"fattura_id": scrittura.get("fattura_id")},
                f"reg:storno-rettifica:{scrittura.get('id')}")
            stornate += 1
            await db[COLL_MOVIMENTI].update_one({"id": scrittura.get("id")}, {"$set": {
                "rettifica_contabile": {"motivi": motivi, "storno_id": storno.get("id"), "at": _now()},
            }})
            if fattura_id:
                await db["invoices"].update_one(
                    filtro_id(fattura_id),
                    {"$set": {"registrata_contabilita": False,
                              "movimento_contabile_stornato_id": scrittura.get("id")},
                     "$unset": {"movimento_contabile_id": ""}})
            await _audit(db, "rettificato", scrittura.get("id"), f"{motivo} (fattura {fattura_id})")
            scrittura["rettifica_contabile"] = {"motivi": motivi}
            in_sospeso.append(scrittura)
        except Exception as exc:  # noqa: BLE001 - raccolgo e riporto, non silenzio
            logger.exception("Rettifica scrittura %s fallita", scrittura.get("id"))
            errori.append(f"{scrittura.get('id')}: {type(exc).__name__}: {exc}")
        if pausa:
            await asyncio.sleep(pausa)

    for scrittura in in_sospeso:
        fattura_id = str(scrittura.get("fattura_id") or "")
        try:
            esito = await _riregistra(db, fattura_id) if fattura_id else {
                "stato": "saltato", "motivo": "scrittura senza fattura_id"}
        except Exception as exc:  # noqa: BLE001
            logger.exception("Nuova registrazione fattura %s fallita", fattura_id)
            errori.append(f"{fattura_id}: {type(exc).__name__}: {exc}")
            continue
        stato = esito.get("stato") or "sconosciuto"
        esiti.append(stato)
        await db[COLL_MOVIMENTI].update_one({"id": scrittura.get("id")}, {"$set": {
            "rettifica_contabile.esito_riregistrazione": stato,
            "rettifica_contabile.motivo_riregistrazione": esito.get("motivo"),
            "rettifica_contabile.nuovo_movimento_id": (esito.get("movimento") or {}).get("id")
            or esito.get("movimento_id"),
        }})
        if pausa:
            await asyncio.sleep(pausa)

    risultato.update({
        "stornate": stornate,
        "esiti_riregistrazione": {s: esiti.count(s) for s in sorted(set(esiti))},
        "errori": errori[:20],
    })
    return risultato


async def censisci_scritture_cancellate(db, *, dry_run: bool = True) -> Dict[str, Any]:
    """Elenca (e in applicazione annota) le scritture marcate cancellate."""
    tutte = await db[COLL_MOVIMENTI].find({}, {"_id": 0}).to_list(None)
    attive_per_chiave: Dict[str, str] = {}
    for s in tutte:
        if not scrittura_attiva(s) or s.get("stato") == "stornato":
            continue
        for chiave in _chiavi_documento(s):
            attive_per_chiave.setdefault(chiave, str(s.get("id")))

    voci = []
    for s in tutte:
        if scrittura_attiva(s):
            continue
        gemella = next((attive_per_chiave[k] for k in _chiavi_documento(s)
                        if k in attive_per_chiave), None)
        dare, avere = totali_righe(s.get("righe") or [])
        voci.append({
            "movimento_id": s.get("id"),
            "tipo": s.get("tipo"),
            "numero_registrazione": s.get("numero_registrazione"),
            "anno": s.get("anno"),
            "data": s.get("data_documento") or s.get("data"),
            "descrizione": s.get("descrizione"),
            "dare": dare, "avere": avere,
            "duplicato_di": gemella,
            "esito": "annullata_come_doppione" if gemella else "documento_senza_scrittura_attiva",
            "gia_annotata": bool(s.get("annullamento")),
        })

    annotate = 0
    if not dry_run:
        for voce in voci:
            if voce["gia_annotata"]:
                continue
            await db[COLL_MOVIMENTI].update_one({"id": voce["movimento_id"]}, {"$set": {
                "annullamento": {
                    "esito": voce["esito"], "duplicato_di": voce["duplicato_di"],
                    "at": _now(),
                    "nota": "scrittura cancellata: fuori dal giornale, non si somma",
                },
            }})
            annotate += 1
    return {
        "dry_run": dry_run,
        "scritture_cancellate": len(voci),
        "con_scrittura_attiva": sum(1 for v in voci if v["duplicato_di"]),
        "documento_senza_scrittura_attiva": sum(1 for v in voci if not v["duplicato_di"]),
        "annotate": annotate,
        "dettaglio": voci[:200],
    }


def _chiavi_documento(scrittura: Dict[str, Any]) -> List[str]:
    chiavi = []
    if scrittura.get("fattura_id"):
        chiavi.append(f"fattura:{scrittura['fattura_id']}:{scrittura.get('tipo')}")
    if scrittura.get("corrispettivo_id") not in (None, ""):
        chiavi.append(f"corrispettivo:{scrittura['corrispettivo_id']}:{scrittura.get('tipo')}")
    chiave = scrittura.get("idempotency_key_originale") or scrittura.get("idempotency_key")
    if chiave:
        chiavi.append(f"chiave:{chiave}")
    return chiavi


# ---------------------------------------------------------------------------
# Esecuzione in sottofondo, stato in sistema_stato
# ---------------------------------------------------------------------------

_GIRI = {
    "rettifica_fatture": (_STATO_RETTIFICA, rettifica_scritture_fatture),
    "scritture_cancellate": (_STATO_CANCELLATE, censisci_scritture_cancellate),
}


async def _salva_stato(db, chiave: str, **campi: Any) -> None:
    campi["aggiornato_at"] = _now()
    await db["sistema_stato"].update_one({"chiave": chiave}, {"$set": campi}, upsert=True)


async def stato_giro(db, giro: str) -> Dict[str, Any]:
    chiave, _ = _GIRI[giro]
    stato = await db["sistema_stato"].find_one({"chiave": chiave}, {"_id": 0}) or {}
    stato.pop("chiave", None)
    stato["in_corso"] = giro in _locks and _locks[giro].locked()
    return stato


async def _esegui(db, giro: str) -> Optional[Dict[str, Any]]:
    chiave, funzione = _GIRI[giro]
    async with _locks[giro]:
        await _salva_stato(db, chiave, stato="in_corso", avviato_at=_now(),
                           risultato=None, errore=None)
        try:
            kwargs = {"pausa": _PAUSA} if giro == "rettifica_fatture" else {}
            risultato = await funzione(db, dry_run=False, **kwargs)
        except Exception as exc:  # noqa: BLE001 - lo stato deve restare leggibile
            logger.exception("Manutenzione giornale %s interrotta", giro)
            await _salva_stato(db, chiave, stato="errore",
                               errore=f"{type(exc).__name__}: {exc}", terminato_at=_now())
            return None
        await _salva_stato(db, chiave, stato="completato", terminato_at=_now(),
                           risultato={k: v for k, v in risultato.items() if k != "dettaglio"})
        return risultato


def avvia_in_background(db, giro: str) -> bool:
    """Parte in sottofondo; un secondo avvio mentre e' in corso non parte."""
    lock = _locks.setdefault(giro, asyncio.Lock())
    if lock.locked():
        return False
    _tasks[giro] = asyncio.create_task(_esegui(db, giro))
    return True
