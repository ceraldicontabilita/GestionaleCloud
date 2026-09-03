"""
haccp_periodi_speciali.py
════════════════════════════════════════════════════════════════════
Gestione periodi speciali HACCP: manutenzione, chiusura, spento.

PERIODI CONFIGURATI:
  A) 26/01/2026 → 04/03/2026  MANUTENZIONE
     - Cancella temperature esistenti in quel periodo
     - Scrive "MANUTENZIONE" su ogni giorno
     - Registra anomalia nel registro per ogni apparecchio

  B) 15/09/2024 → 15/03/2028  CHIUSO / TEMPERATURA NON RILEVATA
     - Scrive "CHIUSO" su ogni giorno
     - Temperatura = None / nota = "Chiuso - temperatura non rilevata"
     - Registra anomalia nel registro

STRUTTURA ANOMALIA:
  {
    tipo:       "manutenzione" | "chiusura" | "spento"
    data_inizio, data_fine
    apparecchio: "frigorifero_1" | "congelatore_3" | ...
    note:       testo descrittivo
    registrato_il: timestamp
  }
════════════════════════════════════════════════════════════════════
"""

import uuid
import logging
from datetime import date, timedelta, datetime, timezone
from fastapi import APIRouter
from app.lotti.db import database as db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/haccp-periodi", tags=["HACCP Periodi Speciali"])


# ── Periodi speciali ───────────────────────────────────────────────────────────
# NESSUN periodo hardcoded: i due periodi-demo che stavano qui (una "chiusura
# stagionale" 15/09/2024->15/03/2028 e una "manutenzione" gen-mar 2026) erano dati
# finti rimasti dal prototipo e hanno timbrato CHIUSO ~4500 celle vere di frigo e
# congelatori piu' 242 anomalie inventate. I giorni di chiusura veri vivono nel
# router /chiusure; eventuali periodi reali futuri andranno su DB, mai nel codice.
PERIODI = []


def iter_giorni(d_inizio: date, d_fine: date):
    """Genera tutti i giorni tra d_inizio e d_fine inclusi."""
    d = d_inizio
    while d <= d_fine:
        yield d
        d += timedelta(days=1)


async def applica_periodo(
    periodo: dict,
    tipo_apparecchio: str,  # "positive" | "negative"
    num_apparecchi: int,
    forza: bool = False,
) -> dict:
    """
    Applica un periodo speciale a tutti gli apparecchi di un tipo.

    - Scrive la nota/label su ogni cella del giorno
    - Sovrascrive SEMPRE (cancella temperature esistenti per quei giorni)
    - Registra un'anomalia nel registro anomalie per ogni apparecchio
    """
    collection_temp = (
        db.temperature_positive if tipo_apparecchio == "positive" else db.temperature_negative
    )
    campo_numero = "frigorifero_numero" if tipo_apparecchio == "positive" else "congelatore_numero"

    anni_coinvolti = set()
    d = periodo["data_inizio"]
    while d <= periodo["data_fine"]:
        anni_coinvolti.add(d.year)
        d += timedelta(days=1)

    celle_aggiornate = 0
    anomalie_create = 0
    ts = datetime.now(timezone.utc).isoformat()

    for anno in sorted(anni_coinvolti):
        # Prendi le schede dell'anno per questo tipo di apparecchio
        schede = await collection_temp.find(
            {"anno": anno},
            {
                "_id": 1,
                campo_numero: 1,
                "frigorifero_nome": 1,
                "congelatore_nome": 1,
                "temperature": 1,
            },
        ).to_list(30)

        # Se non ci sono schede, creale
        if not schede:
            for num in range(1, num_apparecchi + 1):
                nome_campo = (
                    "frigorifero_nome" if tipo_apparecchio == "positive" else "congelatore_nome"
                )
                label_app = "Frigorifero" if tipo_apparecchio == "positive" else "Congelatore"
                doc = {
                    "id": str(uuid.uuid4()),
                    "anno": anno,
                    campo_numero: num,
                    nome_campo: f"{label_app} N°{num}",
                    "temperature": {str(m): {} for m in range(1, 13)},
                    "temp_min": 0.0 if tipo_apparecchio == "positive" else -22.0,
                    "temp_max": 4.0 if tipo_apparecchio == "positive" else -18.0,
                    "created_at": ts,
                    "updated_at": ts,
                }
                await collection_temp.insert_one(doc)
            schede = await collection_temp.find(
                {"anno": anno}, {"_id": 1, campo_numero: 1}
            ).to_list(30)

        for scheda in schede:
            num_app = scheda.get(campo_numero, 1)
            nome_app = (
                scheda.get("frigorifero_nome") or scheda.get("congelatore_nome") or f"App.{num_app}"
            )

            # Aggiorna ogni giorno del periodo in questo anno
            upd = {}
            for d in iter_giorni(periodo["data_inizio"], periodo["data_fine"]):
                if d.year != anno:
                    continue
                m_str = str(d.month)
                g_str = str(d.day)
                campo = f"temperature.{m_str}.{g_str}"
                upd[campo] = {
                    "temp": None,
                    "operatore": "Sistema",
                    "note": periodo["nota_cella"],
                    "label": periodo["label"],
                    "tipo": periodo["tipo"],
                    "timestamp": f"{d.isoformat()}T00:00:00+00:00",
                    "auto": True,
                    "periodo_id": periodo["id"],
                }
                celle_aggiornate += 1

            if upd:
                upd["updated_at"] = ts
                await collection_temp.update_one({"_id": scheda["_id"]}, {"$set": upd})

            # Registra anomalia nel registro
            anomalia_esistente = await db.anomalie_registro.find_one(
                {
                    "periodo_id": periodo["id"],
                    "apparecchio": f"{tipo_apparecchio}_{num_app}",
                    "anno": anno,
                }
            )

            if not anomalia_esistente:
                await db.anomalie_registro.insert_one(
                    {
                        "id": str(uuid.uuid4()),
                        "periodo_id": periodo["id"],
                        "tipo": periodo["tipo"],
                        "apparecchio": f"{tipo_apparecchio}_{num_app}",
                        "nome_apparecchio": nome_app,
                        "tipo_apparecchio": (
                            "Frigorifero" if tipo_apparecchio == "positive" else "Congelatore"
                        ),
                        "anno": anno,
                        "data_inizio": periodo["data_inizio"].isoformat(),
                        "data_fine": periodo["data_fine"].isoformat(),
                        "nota": periodo["nota_anomalia"],
                        "label": periodo["label"],
                        "registrato_il": ts,
                        "stato": "registrato",
                    }
                )
                anomalie_create += 1

    return {
        "periodo": periodo["id"],
        "tipo": periodo["tipo"],
        "celle_aggiornate": celle_aggiornate,
        "anomalie_create": anomalie_create,
    }


# ── Endpoint ──────────────────────────────────────────────────────────────────


@router.post("/applica-tutti")
async def applica_tutti_periodi():
    """
    Applica TUTTI i periodi speciali a frigoriferi e congelatori.
    Chiamato una volta sola (o per rieseguire dopo modifiche).
    """
    risultati = []

    for periodo in PERIODI:
        # Frigoriferi (positivi)
        r_pos = await applica_periodo(periodo, "positive", 12)
        r_pos["apparecchio"] = "frigoriferi"
        risultati.append(r_pos)

        # Congelatori (negativi)
        r_neg = await applica_periodo(periodo, "negative", 12)
        r_neg["apparecchio"] = "congelatori"
        risultati.append(r_neg)

    totale_celle = sum(r["celle_aggiornate"] for r in risultati)
    totale_anomalie = sum(r["anomalie_create"] for r in risultati)

    # auto-pulizia: via le anomalie generate da periodi che non esistono piu'
    ids_validi = [p["id"] for p in PERIODI]
    res_pulizia = await db.anomalie_registro.delete_many(
        {"periodo_id": {"$exists": True, "$nin": ids_validi}})

    return {
        "ok": True,
        "anomalie_orfane_rimosse": res_pulizia.deleted_count,
        "periodi_applicati": len(PERIODI),
        "totale_celle": totale_celle,
        "totale_anomalie": totale_anomalie,
        "dettaglio": risultati,
    }


@router.get("/anomalie")
async def lista_anomalie(tipo: str = None):
    """Lista tutte le anomalie registrate (manutenzione, chiusura, spento)."""
    filtro = {}
    if tipo:
        filtro["tipo"] = tipo
    docs = await db.anomalie_registro.find(filtro, {"_id": 0}).sort("data_inizio", -1).to_list(500)
    return docs


@router.get("/verifica/{periodo_id}")
async def verifica_periodo(periodo_id: str):
    """Verifica quante celle hanno il label del periodo."""
    periodo = next((p for p in PERIODI if p["id"] == periodo_id), None)
    if not periodo:
        from fastapi import HTTPException

        raise HTTPException(404, "Periodo non trovato")

    count_pos = 0
    count_neg = 0

    anni = set()
    d = periodo["data_inizio"]
    while d <= periodo["data_fine"]:
        anni.add(d.year)
        d += timedelta(days=1)

    for anno in anni:
        schede = await db.temperature_positive.find({"anno": anno}).to_list(20)
        for s in schede:
            for m, giorni in s.get("temperature", {}).items():
                for g, val in giorni.items():
                    if isinstance(val, dict) and val.get("periodo_id") == periodo_id:
                        count_pos += 1

        schede_neg = await db.temperature_negative.find({"anno": anno}).to_list(20)
        for s in schede_neg:
            for m, giorni in s.get("temperature", {}).items():
                for g, val in giorni.items():
                    if isinstance(val, dict) and val.get("periodo_id") == periodo_id:
                        count_neg += 1

    anomalie = await db.anomalie_registro.count_documents({"periodo_id": periodo_id})

    return {
        "periodo_id": periodo_id,
        "label": periodo["label"],
        "data_inizio": periodo["data_inizio"].isoformat(),
        "data_fine": periodo["data_fine"].isoformat(),
        "celle_frigo": count_pos,
        "celle_cong": count_neg,
        "anomalie": anomalie,
    }
