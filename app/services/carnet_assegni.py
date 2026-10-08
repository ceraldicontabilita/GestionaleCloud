"""Numero dell'assegno e carnet a cui appartiene: un modulo solo.

Il numero BPM ha 10 cifre e comincia per zero (``0208770368``). Un export
passato da un foglio di calcolo perde lo zero: in archivio c'era
``208770369``, e il confronto per numero dei doppioni lo trattava come un
altro assegno. ``numero_canonico`` rimette **solo** lo zero perso (9 cifre
esatte): un frammento piu' corto, come il finale ``328`` di una causale, non
e' un numero intero e resta com'e'.

Il carnet BPM ha 10 assegni e comincia dal numero che finisce per 1
(``…071``–``…080``): lo ha detto il titolare il 28/09/2026. Prima l'interfaccia
chiamava «carnet» il numero intero, quindi ogni assegno era un carnet a se'.
Il carnet si ricava dal numero, non si scrive sulla scheda: un solo calcolo,
qui, letto dall'elenco e dal riepilogo.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

LARGHEZZA_NUMERO = 10
#: Assegni per carnet BPM (titolare, 28/09/2026).
ASSEGNI_PER_CARNET = 10

_NUMERO = re.compile(r"(\d+)(?:-(\d+))?")


def numero_canonico(valore: Any) -> str:
    """Il numero com'e' stampato sull'assegno, con lo zero iniziale se perso."""
    testo = re.sub(r"\s+", "", str(valore or ""))
    match = _NUMERO.fullmatch(testo)
    if not match:
        return testo
    base, suffisso = match.groups()
    if len(base) == LARGHEZZA_NUMERO - 1:
        base = "0" + base
    return f"{base}-{suffisso}" if suffisso else base


def carnet_del_numero(numero: Any) -> Optional[str]:
    """Il primo numero del carnet (id del carnet), o None se il numero non e' intero."""
    match = _NUMERO.fullmatch(numero_canonico(numero))
    if not match or len(match.group(1)) != LARGHEZZA_NUMERO:
        return None
    n = int(match.group(1))
    primo = ((n - 1) // ASSEGNI_PER_CARNET) * ASSEGNI_PER_CARNET + 1
    return f"{primo:0{LARGHEZZA_NUMERO}d}"


def riepilogo_carnet(assegni: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Un carnet per riga: numeri usati, buchi e stati; il piu' recente per primo."""
    carnet: Dict[str, Dict[str, Any]] = {}
    senza_carnet = 0
    for assegno in assegni:
        numero = numero_canonico(assegno.get("numero"))
        carnet_id = carnet_del_numero(numero)
        if not carnet_id:
            senza_carnet += 1
            continue
        voce = carnet.setdefault(carnet_id, {"carnet_id": carnet_id, "numeri": {}, "stati": {}, "ultima_data": ""})
        voce["numeri"][numero.split("-")[0]] = assegno.get("stato") or "vuoto"
        stato = assegno.get("stato") or "vuoto"
        voce["stati"][stato] = voce["stati"].get(stato, 0) + 1
        data = str(assegno.get("data_emissione") or assegno.get("data") or "")
        voce["ultima_data"] = max(voce["ultima_data"], data)
    righe = []
    for carnet_id, voce in carnet.items():
        primo = int(carnet_id)
        tutti = [f"{primo + i:0{LARGHEZZA_NUMERO}d}" for i in range(ASSEGNI_PER_CARNET)]
        righe.append({
            "carnet_id": carnet_id,
            "primo": tutti[0],
            "ultimo": tutti[-1],
            "in_archivio": len(voce["numeri"]),
            "mancanti": [n for n in tutti if n not in voce["numeri"]],
            "stati": voce["stati"],
            "ultima_data": voce["ultima_data"] or None,
        })
    righe.sort(key=lambda r: (r["ultima_data"] or "", r["carnet_id"]), reverse=True)
    if senza_carnet:
        logger.info("Carnet: %s assegni senza un numero intero a 10 cifre", senza_carnet)
    return righe


async def normalizza_numeri(db) -> Dict[str, Any]:
    """Riporta al numero canonico, per id, le schede che l'hanno perso; il valore di prima va nello storico."""
    esito = {"viste": 0, "corrette": 0, "esempi": []}
    schede = await db["assegni"].find(
        {"entity_status": {"$ne": "deleted"}}, {"_id": 0, "id": 1, "numero": 1},
    ).to_list(None)
    now = datetime.now(timezone.utc).isoformat()
    for scheda in schede:
        esito["viste"] += 1
        prima = scheda.get("numero")
        dopo = numero_canonico(prima)
        if not scheda.get("id") or not prima or dopo == prima:
            continue
        await db["assegni"].update_one({"id": scheda["id"]}, {
            "$set": {"numero": dopo, "updated_at": now},
            "$push": {"storico": {"at": now, "azione": "numero_normalizzato",
                                  "campi": {"numero": {"prima": prima, "dopo": dopo}},
                                  "motivo": "zero iniziale perso nell'import"}},
        })
        esito["corrette"] += 1
        if len(esito["esempi"]) < 20:
            esito["esempi"].append({"id": scheda["id"], "prima": prima, "dopo": dopo})
    return esito
