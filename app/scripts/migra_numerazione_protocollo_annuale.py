"""Migrazione A7 (2026-07-14, scelta utente) — porta il protocollo delle
scritture di `movimenti_contabili` da progressivo GLOBALE a progressivo PER
ANNO (riparte da 1 a ogni anno solare), come nella prassi dei registri
contabili (Zucchetti/TeamSystem/GB/ViaLibera) e come richiesto dall'utente.

NON distruttiva: aggiorna solo il campo `numero_registrazione` delle
scritture ESISTENTI (quelle con `righe`, cioè le vere scritture in partita
doppia del motore §6.1); non tocca nient'altro (righe, importi, date, fonte
documento). Rinumera in ordine CRONOLOGICO (data_documento, poi il vecchio
protocollo a parità di data) per preservare l'ordine di registrazione
originale — la sequenza degli eventi non cambia, cambia solo l'etichetta.

Idempotente: se rilanciata quando i protocolli sono già per-anno, non cambia
nulla (dry-run lo segnala come "già corretto").

Uso:
    python -m app.scripts.migra_numerazione_protocollo_annuale          # dry-run
    python -m app.scripts.migra_numerazione_protocollo_annuale --esegui # applica
"""
import asyncio
import sys
from collections import defaultdict

from app.database import Database

COLL = "movimenti_contabili"


async def migra(esegui: bool) -> dict:
    db = Database.get_db()
    scritture = await db[COLL].find(
        {"righe": {"$exists": True, "$ne": []}, "numero_registrazione": {"$exists": True}},
        {"_id": 0, "id": 1, "numero_registrazione": 1, "anno": 1,
         "data_documento": 1, "data": 1},
    ).to_list(200000)

    per_anno = defaultdict(list)
    for s in scritture:
        anno = s.get("anno")
        per_anno[anno].append(s)

    report = {"anni": {}, "scritture_totali": len(scritture),
             "rinumerate": 0, "invariate": 0, "applicato": bool(esegui)}

    for anno, docs in per_anno.items():
        docs.sort(key=lambda d: (d.get("data_documento") or d.get("data") or "",
                                  d.get("numero_registrazione") or 0))
        cambi = []
        for nuovo_numero, doc in enumerate(docs, start=1):
            vecchio = doc.get("numero_registrazione")
            if vecchio != nuovo_numero:
                cambi.append((doc["id"], vecchio, nuovo_numero))
        report["anni"][str(anno)] = {
            "scritture": len(docs), "da_rinumerare": len(cambi),
        }
        report["rinumerate"] += len(cambi)
        report["invariate"] += len(docs) - len(cambi)
        if esegui:
            for doc_id, _vecchio, nuovo_numero in cambi:
                await db[COLL].update_one(
                    {"id": doc_id}, {"$set": {"numero_registrazione": nuovo_numero}})

    return report


async def _main():
    esegui = "--esegui" in sys.argv
    await Database.connect_db()
    r = await migra(esegui)
    print(f"Protocollo annuale: {r['scritture_totali']} scritture, "
          f"{r['rinumerate']} da rinumerare, {r['invariate']} già corrette "
          f"per anno, applicato={r['applicato']}")
    for anno, info in sorted(r["anni"].items()):
        print(f"  anno {anno}: {info['scritture']} scritture, "
              f"{info['da_rinumerare']} rinumerate")
    if not esegui and r["rinumerate"]:
        print("Dry-run: rilanciare con --esegui per applicare.")


if __name__ == "__main__":
    asyncio.run(_main())
