"""«Pulisci duplicati» dei verbali non cancella: le copie dello stesso numero
vanno in quarantena per id (`stato=quarantena`, `motivo_quarantena`,
`doppione_di`), il canonico riceve i campi che gli mancano, il secondo giro
trova zero gruppi. Solo admin.
"""
import asyncio

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.constants.stati_verbale import STATO_QUARANTENA, e_chiuso
from app.routers import verbali_riconciliazione as rotta
from app.services.archivio_documenti_memoria import ClientArchivioMemoria


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _db():
    db = ClientArchivioMemoria()["verbali_duplicati"]

    async def _carica():
        await db["verbali_noleggio"].insert_one({"id": "v-povero", "numero_verbale": "A1", "stato": "da_pagare",
                                                 "created_at": "2026-01-01"})
        await db["verbali_noleggio"].insert_one({"id": "v-ricco", "numero_verbale": "A1", "stato": "da_pagare",
                                                 "importo": 120.51, "targa": "GX037HJ", "created_at": "2026-01-02"})
        await db["verbali_noleggio"].insert_one({"id": "v-driver", "numero_verbale": "A1", "stato": "da_pagare",
                                                 "driver": "Rossi", "created_at": "2026-01-03"})
        await db["verbali_noleggio"].insert_one({"id": "altro", "numero_verbale": "B2", "stato": "da_pagare"})
    _run(_carica())
    return db


def _verbali(db):
    return {v["id"]: v for v in _run(db["verbali_noleggio"].find({}, {"_id": 0}).to_list(20))}


def test_l_anteprima_non_scrive():
    db = _db()
    esito = _run(rotta.quarantena_duplicati_verbali(db, dry_run=True))
    assert esito["gruppi_duplicati_trovati"] == 1 and esito["documenti_in_quarantena"] == 2
    [d] = esito["dettaglio"]
    assert d["canonico_id"] == "v-ricco" and sorted(d["ids_in_quarantena"]) == ["v-driver", "v-povero"]
    assert "driver" in d["campi_recuperati"]
    assert all(v.get("stato") == "da_pagare" for v in _verbali(db).values())


def test_le_copie_vanno_in_quarantena_per_id_e_niente_si_cancella():
    db = _db()
    esito = _run(rotta.quarantena_duplicati_verbali(db, dry_run=False))
    assert esito["documenti_in_quarantena"] == 2
    verbali = _verbali(db)
    assert len(verbali) == 4  # nessuna cancellazione
    assert verbali["v-ricco"]["stato"] == "da_pagare" and verbali["v-ricco"]["driver"] == "Rossi"
    for copia in ("v-povero", "v-driver"):
        v = verbali[copia]
        assert v["stato"] == STATO_QUARANTENA and v["doppione_di"] == "v-ricco"
        assert v["motivo_quarantena"] == rotta.MOTIVO_DOPPIONE_VERBALE and v["stato_precedente"] == "da_pagare"
        assert e_chiuso(v["stato"])
    assert verbali["altro"]["stato"] == "da_pagare"
    # secondo giro: le copie in quarantena non contano piu'
    secondo = _run(rotta.quarantena_duplicati_verbali(db, dry_run=False))
    assert secondo["gruppi_duplicati_trovati"] == 0 and secondo["documenti_in_quarantena"] == 0


def test_la_rotta_e_solo_admin():
    from app.utils.dependencies import get_current_admin_user

    app = FastAPI()
    app.include_router(rotta.router, prefix="/api/verbali-riconciliazione")

    def _nega():
        raise HTTPException(status_code=403, detail="Solo admin")
    app.dependency_overrides[get_current_admin_user] = _nega
    assert TestClient(app).post("/api/verbali-riconciliazione/pulisci-duplicati?dry_run=true").status_code == 403
