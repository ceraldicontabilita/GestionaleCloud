"""Base dei collaudi funzionali del personale (scenari end-to-end).

Due archivi in memoria separati, come in produzione: HR (``hr.app_*``) e
gestionale. Gli endpoint sono quelli veri (router HR montati su una FastAPI di
prova, auth superata con l'identita' del titolare), i motori sono quelli veri:
niente mock del codice sotto prova.
"""
import asyncio

import pytest
from bson import ObjectId
from fastapi import FastAPI
from fastapi.encoders import ENCODERS_BY_TYPE
from fastapi.testclient import TestClient

from app.services.archivio_documenti_memoria import ClientArchivioMemoria

ANNO = 2026


def run(coro):
    return asyncio.run(coro)


class Mondo:
    def __init__(self, hr, gest, client):
        self.hr, self.gest, self.client = hr, gest, client

    # -- scorciatoie sui dati ------------------------------------------------
    def dipendente(self, id_, nome, cognome, cf, **extra):
        doc = {"id": id_, "nome": nome, "cognome": cognome, "nome_completo": f"{cognome} {nome}",
               "codice_fiscale": cf, "attivo": True, **extra}
        run(self.hr.dipendenti.insert_one(doc))
        return doc

    def busta(self, dip_id, mese, netto, anno=ANNO, cedolino_extra=None, **paga_extra):
        """Una busta: la riga del cedolino HR e il registro paghe del mese."""
        ced = {"id": f"c-{dip_id}-{anno}-{mese}", "dipendente_id": dip_id, "anno": anno, "mese": mese,
               "tipo_cedolino": "ordinario", "netto": netto, **(cedolino_extra or {})}
        run(self.hr.cedolini.insert_one(dict(ced)))
        paga = {"dipendente_id": dip_id, "anno": anno, "mese": mese, "importo_busta": netto,
                "cedolino_id": ced["id"], "stato_pagamento": "in_attesa_pagamento", **paga_extra}
        run(self.hr.paghe_mensili.insert_one(dict(paga)))
        return ced

    def coda(self, id_, importo, data="2026-04-03", causale="VS.DISP. FAVORE BENEFICIARI VARI DISTINTA",
             **extra):
        riga = {"id": id_, "stato": "da_associare", "data": data, "importo": importo,
                "causale": causale, "created_at": "2026-04-03T00:00:00+00:00", **extra}
        run(self.hr.bonifici_da_associare.insert_one(dict(riga)))
        return riga

    # -- endpoint ------------------------------------------------------------
    def associa(self, coda_id, dip_id, tipo="stipendio", mese=3, anno=ANNO, **extra):
        return self.client.post(
            f"/api/dipendenti-cloud/bonifici-da-associare/{coda_id}/associa",
            json={"dipendente_id": dip_id, "tipo": tipo, "mese": mese, "anno": anno, **extra})

    def posizione(self, dip_id, anno=ANNO):
        r = self.client.get(f"/api/posizione-dipendente/dipendente/{dip_id}?anno={anno}")
        assert r.status_code == 200, r.text
        return r.json()

    def paga(self, dip_id, mese=3, anno=ANNO):
        return run(self.hr.paghe_mensili.find_one(
            {"dipendente_id": dip_id, "anno": anno, "mese": mese}, {"_id": 0}))

    def conta(self, collezione, filtro=None, db=None):
        return run((db or self.hr)[collezione].count_documents(filtro or {}))


@pytest.fixture
def mondo(monkeypatch):
    from app.database import Database as DatabaseGest
    from app.hr.database import Database as DatabaseHR
    from app.hr.routers import dipendenti_cloud as router
    from app.hr.routers import posizione_dipendente as router_pos
    from app.hr.routers import tfr as router_tfr
    from app.hr.utils.dependencies import require_staff

    # mongomock aggiunge `_id` ai dict inseriti; l'adattatore Supabase no.
    monkeypatch.setitem(ENCODERS_BY_TYPE, ObjectId, str)
    hr = ClientArchivioMemoria()["hr_scenari"]
    # il gestionale usa l'archivio in memoria dei test del runtime (accetta i Decimal del giornale)
    gest = ClientArchivioMemoria()["gest_scenari"]
    monkeypatch.setattr(DatabaseHR, "get_db", classmethod(lambda cls: hr))
    monkeypatch.setattr(DatabaseGest, "get_db", classmethod(lambda cls: gest))
    monkeypatch.setattr(router, "_db_gestionale", lambda: gest)
    app = FastAPI()
    app.include_router(router.router, prefix="/api")
    app.include_router(router_pos.router, prefix="/api/posizione-dipendente")
    app.include_router(router_tfr.router, prefix="/api/tfr")
    app.dependency_overrides[require_staff] = lambda: {"role": "admin", "name": "Titolare"}
    return Mondo(hr, gest, TestClient(app))
