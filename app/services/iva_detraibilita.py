"""Detraibilita' IVA di una fattura: decisa subito, all'arrivo.

All'import `fattura.created` fa girare prima il motore IVA
(`on_fattura_created_iva`) e poi la classificazione per centro di costo
(`handlers/learning.handler_classifica_cdc`), che scrive `iva_detraibile`.
Il motore IVA, arrivato per primo, trovava la detraibilita' non ancora decisa
e scriveva `DA_VERIFICARE`; nessuno lo ricalcolava, e ogni mese restava
«non calcolato». Ora la classificazione, appena scritta, ricalcola i campi IVA
della stessa fattura (`ricalcola_iva_fattura`).

Per le fatture gia' in archivio lo stesso lavoro lo fa
`completa_iva_pregresso`, nel job bancario corto, a lotti: classifica quelle
mai classificate e ricalcola quelle ferme. Idempotente: una fattura che dopo
il ricalcolo resta da verificare (righe da rivedere, periodo mancante) si
annota con l'impronta dei suoi dati e non si ripassa finche' non cambiano.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Dict
from app.utils.id_fattura import filtro_id

logger = logging.getLogger(__name__)

#: Fatture lavorate per giro: il job corto gira ogni 30 minuti.
LIMITE_PER_GIRO = 60

_CAMPI_IMPRONTA = (
    "iva_detraibile", "stato_classificazione", "periodo_iva_attribuito",
    "invoice_date", "data_ricezione", "iva", "iva_utilizzata",
)


def _impronta(fattura: Dict[str, Any]) -> str:
    dati = {campo: fattura.get(campo) for campo in _CAMPI_IMPRONTA}
    return hashlib.sha256(json.dumps(dati, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _iva_documento(fattura: Dict[str, Any]) -> float:
    try:
        return abs(float(fattura.get("iva") or 0))
    except (TypeError, ValueError):
        return 0.0


async def ricalcola_iva_fattura(db, fattura_id: str) -> Dict[str, Any]:
    """Ricalcola e salva i campi IVA di una fattura (solo se cambiano)."""
    from app.engines import iva_fatture

    fattura = await db["invoices"].find_one(filtro_id(fattura_id))
    if not fattura:
        return {"stato": "saltato", "motivo": "fattura non trovata"}
    campi = iva_fatture.campi_iva_da_fattura(fattura)
    cambiati = {k: v for k, v in campi.items() if fattura.get(k) != v}
    if campi.get("stato_detrazione_iva") == "DA_VERIFICARE":
        # Impronta dello stato che resta salvato (22 e 22.0 sono uguali e
        # non si riscrivono): solo un dato cambiato la fa ripassare.
        impronta = _impronta({**fattura, **cambiati})
        if fattura.get("iva_ricalcolo_impronta") != impronta:
            cambiati["iva_ricalcolo_impronta"] = impronta
    if cambiati:
        await db["invoices"].update_one(filtro_id(fattura_id), {"$set": cambiati})
    return {"stato": campi.get("stato_detrazione_iva"), "aggiornata": bool(cambiati)}


def _da_lavorare(fattura: Dict[str, Any]) -> str | None:
    """Che lavoro serve alla fattura: classificarla, ricalcolarla o niente."""
    if fattura.get("iva_utilizzata") is True:
        return None
    senza_detraibilita = fattura.get("iva_detraibile") is None
    if senza_detraibilita and _iva_documento(fattura) > 0:
        return None if fattura.get("classificazione_iva_tentata_at") else "classifica"
    stato = fattura.get("stato_detrazione_iva")
    if stato in (None, ""):
        return "ricalcola"
    if stato == "DA_VERIFICARE" and not senza_detraibilita:
        if fattura.get("iva_ricalcolo_impronta") == _impronta(fattura):
            return None
        return "ricalcola"
    return None


async def completa_iva_pregresso(db, limite: int = LIMITE_PER_GIRO) -> Dict[str, int]:
    """Classifica e ricalcola, a lotti, le fatture attive rimaste indietro."""
    from app.constants.fattura_attiva import FILTRO_FATTURA_ATTIVA
    from app.handlers.learning import handler_classifica_cdc
    from app.services.eventi_fattura import costruisci_evento_fattura_created

    proiezione = {"_id": 0, "id": 1, "stato_detrazione_iva": 1,
                  "iva_ricalcolo_impronta": 1, "classificazione_iva_tentata_at": 1,
                  **{campo: 1 for campo in _CAMPI_IMPRONTA}}
    fatture = await db["invoices"].find(FILTRO_FATTURA_ATTIVA, proiezione).to_list(None)
    esito = {"candidate": 0, "classificate": 0, "ricalcolate": 0, "sbloccate": 0, "errori": 0}
    lavori = [(f["id"], _da_lavorare(f)) for f in fatture if f.get("id")]
    lavori = [(fid, lavoro) for fid, lavoro in lavori if lavoro]
    esito["candidate"] = len(lavori)
    for fattura_id, lavoro in lavori[:limite]:
        try:
            if lavoro == "classifica":
                completa = await db["invoices"].find_one(filtro_id(fattura_id), {"_id": 0})
                if not completa:
                    continue
                await handler_classifica_cdc(costruisci_evento_fattura_created(completa), db)
                await db["invoices"].update_one(
                    filtro_id(fattura_id),
                    {"$set": {"classificazione_iva_tentata_at": _ora()}})
                esito["classificate"] += 1
            else:
                r = await ricalcola_iva_fattura(db, fattura_id)
                esito["ricalcolate"] += 1
                if r.get("stato") and r.get("stato") != "DA_VERIFICARE":
                    esito["sbloccate"] += 1
        except Exception as exc:  # noqa: BLE001 - una fattura non ferma il lotto
            esito["errori"] += 1
            logger.warning("IVA fattura %s (%s) non completata: %s: %s",
                           fattura_id, lavoro, type(exc).__name__, exc)
    return esito


def _ora() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
