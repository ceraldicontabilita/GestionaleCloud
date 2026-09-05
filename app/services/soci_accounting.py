"""Contabilizzazione canonica degli apporti/rimborsi soci.

Un fatto economico ha un solo ``operation_id``. La scheda socio e la Prima
Nota sono proiezioni dello stesso fatto, non due operazioni economiche.

Regole:
- cassa: la prova e' l'inserimento manuale autorizzato, quindi la riga di
  Prima Nota Cassa nasce confermata;
- banca: l'inserimento manuale crea una riga di Prima Nota Banca in attesa
  dell'estratto ufficiale. Solo il movimento bancario reale la conferma;
- un reimport o un secondo submit con lo stesso operation_id e' idempotente;
- la riconciliazione di un'attesa bancaria aggiorna la riga esistente invece
  di crearne una seconda.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
import re
import uuid

from app.services.finanziamenti_soci import COLLECTION, SOCI, classifica_finanziamento_ec
from app.services.scritture_contabili import scrivi_movimento


def _socio(socio_id: Optional[str]) -> Optional[Dict[str, Any]]:
    return next((s for s in SOCI if s["id"] == socio_id), None)


def _data_iso(raw: Any) -> str:
    value = str(raw or "")[:10]
    return value if re.match(r"^\d{4}-\d{2}-\d{2}$", value) else ""


async def registra_movimento_socio(
    db,
    *,
    socio_id: Optional[str],
    tipo: str,
    importo: float,
    data: str,
    destinazione: str,
    descrizione: str = "",
    operation_id: Optional[str] = None,
    source: str = "manuale",
) -> Dict[str, Any]:
    socio = _socio(socio_id)
    if not socio:
        raise ValueError("socio_id non valido")
    if tipo not in {"apporto", "rimborso"}:
        raise ValueError("tipo deve essere apporto o rimborso")
    destinazione = str(destinazione or "").lower()
    if destinazione not in {"cassa", "banca"}:
        raise ValueError("destinazione deve essere cassa o banca")
    importo = round(abs(float(importo or 0)), 2)
    if importo <= 0:
        raise ValueError("importo non valido")
    data = _data_iso(data)
    if not data:
        raise ValueError("data non valida (YYYY-MM-DD)")

    operation_id = operation_id or f"socio:{uuid.uuid4().hex}"
    esistente = await db[COLLECTION].find_one({"operation_id": operation_id})
    if esistente:
        return {
            "success": True,
            "idempotente": True,
            "operation_id": operation_id,
            "movimento": esistente,
        }

    now = datetime.now(timezone.utc).isoformat()
    pn_id = str(uuid.uuid4())
    entrata = tipo == "apporto"
    registro = "cassa" if destinazione == "cassa" else "banca"
    stato_finanziario = "confermato" if destinazione == "cassa" else "in_attesa_estratto"

    pn = {
        "id": pn_id,
        "operation_id": operation_id,
        "data": data,
        "tipo": "entrata" if entrata else "uscita",
        "importo": importo,
        "descrizione": descrizione or (
            f"Apporto socio {socio['nome']}" if entrata else f"Rimborso socio {socio['nome']}"
        ),
        "categoria": "Finanziamento soci",
        "socio_id": socio["id"],
        "socio_nome": socio["nome"],
        "tipo_finanziamento": tipo,
        "source": source,
        "created_at": now,
        "idempotency_key": f"socio_pn:{operation_id}:{registro}",
        "riconciliato": destinazione == "cassa",
        "stato_riconciliazione": stato_finanziario,
    }
    if destinazione == "banca":
        pn.update({
            "in_attesa_estratto_ufficiale": True,
            "expectation_type": "finanziamento_socio",
            "expectation_status": "attesa_evidenza_bancaria",
            "expectation_owner": socio["id"],
            "status": "in_attesa_estratto_bancario_ufficiale",
        })

    await scrivi_movimento(db, registro, pn)

    movimento = {
        "id": str(uuid.uuid4()),
        "operation_id": operation_id,
        "socio_id": socio["id"],
        "socio_nome": socio["nome"],
        "tipo": tipo,
        "importo": importo,
        "data": data,
        "descrizione": pn["descrizione"],
        "destinazione": destinazione,
        "prima_nota_id": pn_id,
        "prima_nota_tipo": registro,
        "estratto_conto_id": None,
        "stato_finanziario": stato_finanziario,
        "source": source,
        "created_at": now,
        "updated_at": now,
    }
    await db[COLLECTION].insert_one(movimento)
    return {
        "success": True,
        "idempotente": False,
        "operation_id": operation_id,
        "prima_nota_id": pn_id,
        "movimento": movimento,
    }


async def riconcilia_attese_soci_da_ec(
    db, *, anno: Optional[int] = None, movimento_ids=None,
) -> Dict[str, int]:
    """Conferma attese banca soci quando arriva una prova bancaria univoca.

    Match automatico solo se socio, verso, importo e finestra temporale sono
    coerenti e la candidata manuale e' unica. In caso contrario non tocca nulla.
    """
    query_ec: Dict[str, Any] = {}
    if movimento_ids:
        query_ec["id"] = {"$in": list(movimento_ids)}
    stats = {"analizzati": 0, "riconciliati": 0, "ambigui": 0}
    async for ec in db["estratto_conto_movimenti"].find(query_ec):
        c = classifica_finanziamento_ec(ec)
        if not c:
            continue
        if anno and not str(c.get("data") or "").startswith(f"{anno}-"):
            continue
        stats["analizzati"] += 1
        try:
            data_ec = datetime.strptime(c["data"], "%Y-%m-%d")
        except ValueError:
            continue
        data_min = (data_ec - timedelta(days=15)).strftime("%Y-%m-%d")
        data_max = (data_ec + timedelta(days=15)).strftime("%Y-%m-%d")
        candidati = await db[COLLECTION].find({
            "socio_id": c["socio_id"],
            "tipo": c["tipo"],
            "destinazione": "banca",
            "stato_finanziario": "in_attesa_estratto",
            "importo": c["importo"],
            "data": {"$gte": data_min, "$lte": data_max},
        }, {"_id": 0}).to_list(3)
        if len(candidati) != 1:
            if len(candidati) > 1:
                stats["ambigui"] += 1
            continue

        attesa = candidati[0]
        operation_id = attesa.get("operation_id")
        pn_id = attesa.get("prima_nota_id")
        ec_id = c["estratto_conto_id"]
        now = datetime.now(timezone.utc).isoformat()

        await db[COLLECTION].update_one({"id": attesa["id"]}, {"$set": {
            "estratto_conto_id": ec_id,
            "stato_finanziario": "confermato_banca",
            "updated_at": now,
        }})
        if pn_id:
            await db["prima_nota_banca"].update_one({"id": pn_id}, {"$set": {
                "estratto_conto_id": ec_id,
                "movimento_estratto_conto_id": ec_id,
                "riconciliato": True,
                "stato_riconciliazione": "riconciliato",
                "in_attesa_estratto_ufficiale": False,
                "expectation_status": "confermata_da_estratto",
                "status": "confirmed",
                "updated_at": now,
            }})
        await db["estratto_conto_movimenti"].update_one({"id": ec_id}, {"$set": {
            "riconciliato": True,
            "tipo_riconciliazione": "finanziamento_socio",
            "operation_id": operation_id,
            "socio_id": c["socio_id"],
            "documento_collection": COLLECTION,
            "documento_id": attesa["id"],
            "updated_at": now,
        }})
        stats["riconciliati"] += 1
    return stats
