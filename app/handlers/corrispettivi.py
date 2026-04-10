"""
Handler Corrispettivi — reagisce a corrispettivi.importati
Scrive automaticamente in prima_nota_cassa per ogni giornata importata.
Controlla anche la coerenza con i dati POS.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


async def handler_prima_nota_corrispettivi(payload: Dict[str, Any], db) -> Dict[str, Any]:
    """
    Quando arrivano i corrispettivi XML del registratore telematico:
    - Scrive entrata in prima_nota_cassa per ogni giorno
    - Distingue contanti da pagamento elettronico
    - Anti-duplicato su data + source
    """
    if db is None:
        return {"skipped": True, "reason": "db non disponibile"}

    corrispettivi: List[Dict] = payload.get("corrispettivi") or []
    if not corrispettivi:
        # Potrebbe essere un singolo corrispettivo
        if payload.get("data") and payload.get("totale"):
            corrispettivi = [payload]
        else:
            return {"skipped": True, "reason": "nessun corrispettivo"}

    scritti = 0
    saltati = 0
    errori  = []

    for corr in corrispettivi:
        try:
            data    = (corr.get("data") or "")[:10]
            totale  = float(corr.get("totale") or corr.get("importo") or 0)
            corr_id = corr.get("id") or corr.get("corrispettivo_id") or ""

            if totale <= 0 or not data:
                continue

            # Anti-duplicato: un solo movimento per data+source
            esistente = await db["prima_nota_cassa"].find_one({
                "data": data,
                "source": "corrispettivo_import",
                "categoria": "Corrispettivi",
            })
            if esistente:
                saltati += 1
                continue

            # Contanti vs elettronico
            contanti   = float(corr.get("totale_contanti")   or
                               corr.get("importo_contanti")   or totale)
            elettronico = float(corr.get("totale_elettronico") or
                                corr.get("pagamento_elettronico") or 0)
            imponibile  = float(corr.get("imponibile") or totale)
            iva         = float(corr.get("iva")         or
                                corr.get("totale_iva")  or 0)

            # Movimento principale
            movimento = {
                "id":              str(uuid.uuid4()),
                "corrispettivo_id": corr_id,
                "data":            data,
                "tipo":            "entrata",
                "importo":         totale,
                "imponibile":      imponibile,
                "iva":             iva,
                "contanti":        contanti,
                "elettronico":     elettronico,
                "descrizione":     f"Corrispettivo giornaliero {data}",
                "categoria":       "Corrispettivi",
                "source":          "corrispettivo_import",
                "anno":            int(data[:4]) if len(data) >= 4 else datetime.now().year,
                "mese":            int(data[5:7]) if len(data) >= 7 else datetime.now().month,
                "created_at":      datetime.now(timezone.utc).isoformat(),
            }

            await db["prima_nota_cassa"].insert_one(movimento.copy())
            scritti += 1

            # Se c'è quota elettronica significativa → segna per riconciliazione POS
            if elettronico > 1:
                await db["corrispettivi"].update_one(
                    {"id": corr_id},
                    {"$set": {
                        "da_riconciliare_pos": True,
                        "importo_elettronico_atteso": elettronico,
                    }},
                    upsert=False
                )

        except Exception as e:
            errori.append(str(e))
            logger.warning(f"[HandlerCorrispettivi] Errore su {corr.get('data')}: {e}")

    logger.info(f"[HandlerCorrispettivi] {scritti} scritti | {saltati} saltati | {len(errori)} errori")

    return {
        "prima_nota_scritti": scritti,
        "saltati_duplicato":  saltati,
        "errori":             errori,
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
            corr.get("pagamento_elettronico") or 0
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
