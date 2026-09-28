"""Controllo mensile: le somme di Cassa e corrispettivi le fa il server.

La pagina scaricava fino a 10.000 righe per sommarle. Questi test provano che
i totali del server sono la somma di tutte le righe del periodo, con le stesse
regole che stavano nel browser.
"""
import asyncio
from decimal import Decimal

from app.routers.prima_nota_module import controllo_mensile as cm
from app.services.archivio_documenti_memoria import ClientArchivioMemoria

CASSA = [
    {"id": "a", "data": "2026-01-02", "tipo": "entrata", "importo": 100.10, "categoria": "Corrispettivi"},
    {"id": "b", "data": "2026-01-03", "tipo": "uscita", "importo": 20.05, "categoria": "Versamento"},
    {"id": "c", "data": "2026-01-03", "tipo": "uscita", "importo": 7.00, "categoria": "Altro",
     "descrizione": "VERSAMENTO contanti in banca"},
    {"id": "d", "data": "2026-01-15", "tipo": "entrata", "importo": 40.00, "categoria": "Altro",
     "source": "excel_corrispettivi"},
    {"id": "e", "data": "2026-02-01", "tipo": "uscita", "importo": 3.30, "categoria": "Fatture"},
    # Fuori da ogni conto: eliminata e riga d'archivio del ripiego in cassa.
    {"id": "x", "data": "2026-01-04", "tipo": "entrata", "importo": 999, "categoria": "Corrispettivi",
     "status": "deleted"},
    {"id": "y", "data": "2026-01-05", "tipo": "uscita", "importo": 888, "categoria": "Fatture",
     "source": "metodo_fornitore_assente_provvisorio"},
    {"id": "z", "data": "2025-12-31", "tipo": "entrata", "importo": 5, "categoria": "Corrispettivi"},
]
XML = [
    {"id": "x1", "data": "2026-01-02", "totale": 300.0, "pagato_contanti": 100.10,
     "numero_documenti": 12, "annulli": 1, "pagato_non_riscosso": 15.5,
     "totale_ammontare_annulli": 2.2},
    {"id": "x2", "data": "2026-01-15", "totale": 80.0, "pagato_contanti": "40.00",
     "numero_documenti": "3", "pagato_non_riscosso": 0, "totale_ammontare_annulli": 0},
    {"id": "x3", "data": "2026-02-10", "totale": 50.0, "numero_documenti": 2},
    {"id": "x4", "data": "2026-01-20", "totale": 1000.0, "pagato_contanti": 1, "status": "deleted"},
]


def _db(monkeypatch):
    db = ClientArchivioMemoria()["controllo_mensile_test"]
    monkeypatch.setattr(cm.Database, "get_db", staticmethod(lambda: db))
    asyncio.run(db["prima_nota_cassa"].insert_many([dict(r) for r in CASSA]))
    asyncio.run(db["corrispettivi"].insert_many([dict(r) for r in XML]))
    return db


def _vive(riga):
    return riga.get("status") != "deleted" and riga.get("source") != "metodo_fornitore_assente_provvisorio" \
        and riga["data"].startswith("2026")


def test_anno_totali_uguali_alla_somma_di_tutte_le_righe(monkeypatch):
    _db(monkeypatch)
    r = asyncio.run(cm.riepilogo_controllo_mensile(anno=2026))
    assert [p["periodo"] for p in r["periodi"]] == [f"2026-{m:02d}" for m in range(1, 13)]
    cassa = [c for c in CASSA if _vive(c)]
    xml = [x for x in XML if _vive(x)]
    tot = r["totale"]
    assert Decimal(str(tot["entrate_cassa"])) == sum(Decimal(str(c["importo"])) for c in cassa if c["tipo"] == "entrata")
    assert Decimal(str(tot["uscite_cassa"])) == sum(Decimal(str(c["importo"])) for c in cassa if c["tipo"] == "uscita")
    assert Decimal(str(tot["corrispettivi_xml"])) == sum(Decimal(str(x["totale"])) for x in xml)
    assert tot["documenti_commerciali"] == 17
    assert tot["movimenti_cassa"] == len(cassa) and tot["righe_xml"] == len(xml)
    # Il totale dell'anno e' la somma dei mesi, voce per voce.
    for chiave in ("entrate_cassa", "uscite_cassa", "versamenti", "corrispettivi_cassa",
                   "corrispettivi_xml", "pagato_non_riscosso", "ammontare_annulli"):
        somma = sum(Decimal(str(p[chiave])) for p in r["periodi"])
        assert somma == Decimal(str(tot[chiave])), chiave

    gennaio = r["periodi"][0]
    assert gennaio["corrispettivi_cassa"] == 140.10
    assert gennaio["versamenti"] == 27.05
    assert gennaio["saldo_cassa"] == 113.05
    assert gennaio["contanti_xml"] == 140.10
    assert gennaio["differenza_contanti"] == 0.0
    assert (gennaio["pagato_non_riscosso"], gennaio["pagato_non_riscosso_count"]) == (15.5, 1)
    assert (gennaio["ammontare_annulli"], gennaio["ammontare_annulli_count"]) == (2.2, 1)
    # Febbraio: un XML senza contanti non si confronta con la Cassa.
    assert r["periodi"][1]["xml_senza_contanti"] == 1
    assert r["periodi"][1]["differenza_contanti"] is None
    assert "versamenti_dettaglio" not in r


def test_mese_per_giorno_con_dettaglio_versamenti(monkeypatch):
    _db(monkeypatch)
    r = asyncio.run(cm.riepilogo_controllo_mensile(anno=2026, mese=1))
    assert len(r["periodi"]) == 31
    giorni = {p["periodo"]: p for p in r["periodi"]}
    assert giorni["2026-01-02"]["corrispettivi_cassa"] == 100.10
    assert giorni["2026-01-02"]["corrispettivi_xml"] == 300.0
    assert giorni["2026-01-03"]["versamenti"] == 27.05
    assert giorni["2026-01-20"]["righe_xml"] == 0
    assert [v["id"] for v in r["versamenti_dettaglio"]] == ["b", "c"]
    assert sum(Decimal(str(abs(v["importo"]))) for v in r["versamenti_dettaglio"]) == \
        Decimal(str(r["totale"]["versamenti"]))


def test_differenza_solo_sulla_quota_contanti():
    # Totale XML 100, di cui 30 in contanti: in Cassa entrano 30 e basta.
    riga = cm.riga_periodo(
        [{"tipo": "entrata", "categoria": "Corrispettivi", "importo": 30}],
        [{"totale": 100, "pagato_contanti": 30, "pagato_elettronico": 70}],
    )
    assert riga["differenza_contanti"] == 0.0
    assert cm.riga_periodo([{"tipo": "entrata", "categoria": "Corrispettivi", "importo": 100}],
                           [{"totale": 100, "pagato_contanti": 30}])["differenza_contanti"] == -70.0
    assert cm.riga_periodo([], [{"totale": 100}])["differenza_contanti"] is None
    # Cassa senza nessun XML: tutta la Cassa e' da spiegare.
    assert cm.riga_periodo([{"tipo": "entrata", "categoria": "Corrispettivi", "importo": 30}],
                           [])["differenza_contanti"] == -30.0
    assert cm.numero("12.5abc") == Decimal("12.5") and cm.numero("") is None
