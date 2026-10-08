"""
Handler Corrispettivi: compatibilità eventi e controllo coerenza POS.

La Prima Nota è gestita dal servizio canonico di ingestione; il vecchio
evento non produce una seconda scrittura.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


async def handler_prima_nota_corrispettivi(payload: Dict[str, Any], db) -> Dict[str, Any]:
    """
    Compatibilita con il vecchio evento ``corrispettivi.importati``.

    La scrittura di Prima Nota viene prodotta esclusivamente dal servizio
    canonico di ingestione del corrispettivo. Questo handler non scrive piu
    movimenti: mantenerlo read-only evita doppie registrazioni quando un evento
    storico viene ripubblicato.
    """
    return {
        "skipped": True,
        "reason": "prima_nota_gestita_dal_servizio_canonico_corrispettivi",
        "prima_nota_scritti": 0,
    }


async def handler_check_coerenza_pos(payload: Dict[str, Any], db) -> Dict[str, Any]:
    """
    Verifica coerenza tra corrispettivi XML e dati POS Nexi.
    Crea alert se c'è differenza > €1.
    """
    if db is None:
        return {"skipped": True}

    corrispettivi: List[Dict] = payload.get("corrispettivi") or []
    if not corrispettivi:
        if payload.get("data"):
            corrispettivi = [payload]
        else:
            return {"skipped": True, "reason": "nessun corrispettivo"}

    anomalie = 0
    for corr in corrispettivi:
        data = (corr.get("data") or "")[:10]
        elettronico_dichiarato = float(
            corr.get("totale_elettronico") or
            corr.get("pagamento_elettronico") or
            # nome campo reale nei documenti creati da corrispettivi_service
            corr.get("pagato_pos") or
            corr.get("pagato_elettronico") or 0
        )

        if elettronico_dichiarato <= 0 or not data:
            continue

        # Cerca accredito Nexi per quella data (±1 giorno)
        try:
            from datetime import timedelta
            data_base = datetime.strptime(data, "%Y-%m-%d")
            data_min  = (data_base - timedelta(days=1)).strftime("%Y-%m-%d")
            data_max  = (data_base + timedelta(days=2)).strftime("%Y-%m-%d")

            accredito = await db["estratto_conto_movimenti"].find_one({
                "data": {"$gte": data_min, "$lte": data_max},
                "tipo": "entrata",
                "importo": {
                    "$gte": elettronico_dichiarato - 5,
                    "$lte": elettronico_dichiarato + 5,
                },
                "descrizione": {"$regex": "NEXI|POS|PAGAMENTI ELETTRONICI", "$options": "i"},
            })

            if accredito:
                diff = abs(elettronico_dichiarato - abs(float(accredito.get("importo", 0))))
                if diff > 1.0:
                    # Anomalia: differenza significativa
                    await db["agenti_segnalazioni"].insert_one({
                        "id": str(uuid.uuid4()),
                        "agente": "HandlerCorrispettivi",
                        "tipo": "avviso",
                        "titolo": f"Coerenza POS: differenza €{diff:.2f} il {data}",
                        "descrizione": (
                            f"I corrispettivi del {data} dichiarano €{elettronico_dichiarato:.2f} "
                            f"di pagamenti elettronici, ma l'accredito Nexi in banca è "
                            f"€{abs(float(accredito.get('importo', 0))):.2f}. "
                            f"Differenza: €{diff:.2f}."
                        ),
                        "azione": "Magazzino → Coerenza POS → verifica giornata",
                        "letta": False,
                        "risolta": False,
                        "dati": {"data": data, "differenza": diff},
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    })
                    anomalie += 1
        except Exception as e:
            logger.debug(f"[HandlerCorrispettivi] Check POS errore: {e}")

    return {"anomalie_pos": anomalie}
