"""Giornate XML di Gestione IVA a pagine, con totali dell'intero periodo.

La pagina scaricava 5.000 corrispettivi e toglieva le copie nel browser. Ora
lo fa ``GET /api/corrispettivi/periodo``: le pagine in fila danno le stesse
giornate e i totali sono la somma di tutte le giornate uniche.
"""
import asyncio
from decimal import Decimal

from app.routers.invoices import corrispettivi as router_corrispettivi
from app.services.archivio_documenti_memoria import ClientArchivioMemoria

RIGHE = [
    {"id": "g1", "data": "2026-05-01", "matricola_rt": "RT1", "totale": 110.0, "totale_iva": 10.0,
     "totale_imponibile": 100.0, "pagato_contanti": 60.0, "pagato_elettronico": 50.0},
    # Copia della stessa giornata: stessa data, registratore e totale.
    {"id": "g1-copia", "data": "2026-05-01", "matricola_rt": "RT1", "totale": 110.0, "totale_iva": 10.0,
     "totale_imponibile": 100.0, "pagato_contanti": 60.0, "pagato_elettronico": 50.0},
    {"id": "g2", "data": "2026-05-02", "id_dispositivo": "RT1", "totale": 55.55, "iva": 5.05,
     "pagato_contanti": 5.55, "pagato_pos": 50.0},
    {"id": "g3", "data": "2026-05-03", "corrispettivo_key": "K3", "totale": 0, "totale_complessivo": 99,
     "totale_iva": 0, "totale_imponibile": 0},
    {"id": "g3-copia", "data": "2026-05-03", "corrispettivo_key": " K3 ", "totale": 12},
    {"id": "g4", "data": "2026-05-04", "matricola_rt": "RT2", "totale": 22.0, "totale_iva": 2.0,
     "totale_imponibile": 20.0, "pagato_contanti": 22.0},
    {"id": "fuori", "data": "2026-06-01", "matricola_rt": "RT1", "totale": 1000.0},
    {"id": "eliminata", "data": "2026-05-05", "totale": 1000.0, "status": "deleted"},
]


def _chiama(monkeypatch, **kwargs):
    db = ClientArchivioMemoria()["corrispettivi_periodo_test"]
    monkeypatch.setattr(router_corrispettivi.Database, "get_db", staticmethod(lambda: db))
    asyncio.run(db["corrispettivi"].insert_many([dict(r) for r in RIGHE]))
    argomenti = {"data_da": "2026-05-01", "data_a": "2026-05-31", "skip": 0, "limit": 200}
    argomenti.update(kwargs)
    return db, argomenti


def test_pagine_in_fila_e_totali_delle_giornate_uniche(monkeypatch):
    db, argomenti = _chiama(monkeypatch)
    intera = asyncio.run(router_corrispettivi.corrispettivi_del_periodo(**argomenti))
    assert [r["id"] for r in intera["corrispettivi"]] == ["g4", "g3", "g2", "g1"]
    assert intera["totale"] == 4
    assert intera["copie_escluse"] == 2

    pagine = [
        asyncio.run(router_corrispettivi.corrispettivi_del_periodo(**{**argomenti, "skip": s, "limit": 3}))
        for s in (0, 3)
    ]
    assert [r["id"] for p in pagine for r in p["corrispettivi"]] == ["g4", "g3", "g2", "g1"]
    for pagina in pagine:
        assert pagina["totali"] == intera["totali"]
        assert (pagina["totale"], pagina["copie_escluse"]) == (4, 2)

    uniche = [r for r in RIGHE if r["id"] in {"g1", "g2", "g3", "g4"}]
    assert Decimal(str(intera["totali"]["totale"])) == Decimal("110.0") + Decimal("55.55") + 0 + Decimal("22.0")
    assert intera["totali"] == {
        "totale": 187.55,
        # g2 senza imponibile: totale − IVA; g3 dichiara imponibile 0.
        "imponibile": 100.0 + 50.50 + 0 + 20.0,
        "iva": 17.05,
        "contanti": 87.55,
        "elettronico": 100.0,
    }
    assert len(uniche) == intera["totale"]


def test_chiave_giornata_xml():
    chiave = router_corrispettivi.chiave_giornata_xml
    assert chiave({"corrispettivo_key": " K1 "}) == "K1"
    assert chiave({"data": "2026-05-01", "matricola_rt": "RT1", "totale": 10.005}) == "2026-05-01|RT1|1001"
    assert chiave({"data_rilevazione": "2026-05-01", "matricola": "M", "totale_complessivo": 3}) == \
        "2026-05-01|M|300"
