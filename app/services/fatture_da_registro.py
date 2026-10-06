"""Ricostruzione delle fatture dagli XML gia' letti: registro della cartella unica -> Drive -> smistatore.

Quando la collezione `invoices` e' vuota (azzerata) gli XML restano in ``ELABORATE`` e il registro
`drive_cartella_unica` li conosce come «elaborato»: lo smistatore non li rilegge piu'. Qui si riprendono
SOLO i file che il registro dichiara `tipo=fattura` in ELABORATE (non l'intero archivio), si scaricano
per id e passano dallo stesso smistatore di Documenti > Import: stesse regole (anno attivo, parcelle con
ritenuta, collisioni di identita', evento `fattura.created`), stessa idempotenza (un secondo giro dice
`gia_presenti`). Niente si sposta e niente si cancella su Drive.

Si accende con `RICOSTRUZIONE_FATTURE_DA_REGISTRO=true` (giro dello scheduler a tempo, riprendibile da un
cursore in `sistema_stato`); a lavoro finito scrive `stato=completato` e non riparte.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

CHIAVE = "fatture_da_registro"
REGISTRO = "drive_cartella_unica"
BUDGET_SECONDI = 480          # un giro dello scheduler lavora al massimo 8 minuti
MAX_ELENCO = 50
_lock = asyncio.Lock()


def acceso() -> bool:
    return os.getenv("RICOSTRUZIONE_FATTURE_DA_REGISTRO", "").strip().lower() in {"1", "true", "si", "yes"}


async def _stato(db) -> Dict[str, Any]:
    return await db["sistema_stato"].find_one({"chiave": CHIAVE}, {"_id": 0}) or {}


async def _salva(db, **campi) -> None:
    await db["sistema_stato"].update_one(
        {"chiave": CHIAVE},
        {"$set": {**campi, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )


async def _file_da_rileggere(db) -> List[Dict[str, Any]]:
    righe = await db[REGISTRO].find(
        {"cartella": "ELABORATE", "tipo": "fattura"},
        {"_id": 0, "id": 1, "drive_file_id": 1, "nome": 1, "md5": 1},
    ).to_list(None)
    righe = [r for r in righe if (r.get("drive_file_id") or r.get("id")) and r.get("nome")]
    # Ordine stabile: il cursore e' una posizione in questo elenco.
    return sorted(righe, key=lambda r: (str(r.get("nome")), str(r.get("drive_file_id") or r.get("id"))))


async def anteprima(db) -> Dict[str, Any]:
    file = await _file_da_rileggere(db)
    return {"dry_run": True, "file": len(file),
            "xml": sum(1 for f in file if str(f["nome"]).lower().endswith((".xml", ".p7m")))}


async def giro(db, *, budget: int = BUDGET_SECONDI) -> Dict[str, Any]:
    """Un giro a tempo: riprende dal cursore, elabora per id e salva l'avanzamento ogni 10 file."""
    if _lock.locked():
        return {"saltato": "giro gia' in corso"}
    async with _lock:
        from app.services.drive_cartella_unica import _smista
        from app.services.drive_download import scarica_originale

        stato = await _stato(db)
        if stato.get("stato") == "completato":
            return {"saltato": "gia' completato"}
        file = await _file_da_rileggere(db)
        indice = int(stato.get("indice") or 0)
        contatori = {"importati": 0, "gia_presenti": 0, "non_fatture": 0, "errori": 0,
                     **(stato.get("contatori") or {})}
        errori: List[Dict[str, Any]] = list(stato.get("errori") or [])
        inizio = time.monotonic()
        await _salva(db, stato="in_corso", totale=len(file))
        while indice < len(file) and time.monotonic() - inizio < budget:
            f = file[indice]
            drive_id = f.get("drive_file_id") or f.get("id")
            try:
                dati = await scarica_originale(drive_id, f.get("md5"))
                if not dati:
                    raise OSError("contenuto non leggibile da Drive")
                risultato = await _smista(f["nome"], dati, {
                    "archive_filename": "ricostruzione_fatture", "archive_path": f["nome"],
                    "archive_group": "ricostruzione_fatture", "archive_sha256": "",
                })
                if risultato.get("duplicate"):
                    contatori["gia_presenti"] += 1
                elif risultato.get("success"):
                    contatori["importati"] += 1
                elif risultato.get("tipo_rilevato") not in ("fattura", "fattura_xml", None):
                    contatori["non_fatture"] += 1
                else:
                    # Fuori dall'anno attivo o senza esito scritto: contato, non un guasto del file.
                    contatori["non_fatture"] += 1
            except Exception as exc:  # una voce guasta non ferma le altre
                contatori["errori"] += 1
                logger.warning("[fatture-da-registro] %s non riletta: %s: %s",
                               f["nome"], type(exc).__name__, exc)
                if len(errori) < MAX_ELENCO:
                    errori.append({"file": f["nome"], "motivo": f"{type(exc).__name__}: {exc}"[:300]})
            indice += 1
            if indice % 10 == 0:
                await _salva(db, indice=indice, contatori=contatori, errori=errori)
        finito = indice >= len(file)
        await _salva(db, stato="completato" if finito else "in_corso", indice=indice,
                     totale=len(file), contatori=contatori, errori=errori)
        logger.info("[fatture-da-registro] %s/%s file, %s", indice, len(file), contatori)
        return {"indice": indice, "totale": len(file), "completato": finito, "contatori": contatori}


async def giro_schedulato(db) -> Dict[str, Any]:
    if not acceso():
        return {"saltato": "RICOSTRUZIONE_FATTURE_DA_REGISTRO spento"}
    return await giro(db)
