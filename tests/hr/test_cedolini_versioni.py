"""Versioni della stessa busta (MINI-03): un motore solo decide chi vale.

Stampa di controllo e definitiva, «Variante 1» e «Variante 2», pagina del
Libro Unico letta a meta': nel registro ``cedolini`` la stessa busta esisteva
in piu' righe con netti diversi (108 gruppi al 30/09/2026). Qui si prova che:

- la definitiva batte la stampa di controllo, in entrambi gli ordini d'arrivo;
- la Variante 2 batte la Variante 1;
- due netti senza marcatore restano tutti e due, marcati ``varianti_da_decidere``;
- una riga pagata non si sostituisce mai;
- la riga HR segue il vincitore e conserva il vecchio netto in ``storico_netto``;
- ``netto_fonte`` e' ``non_letto_da_lul`` su una pagina LUL senza cella del
  netto (netto nullo, mai zero) e ``cella`` su una busta normale.
"""
import asyncio
import base64
import json

import fitz
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.constants.stati_netto import (
    NETTO_FONTE_CELLA,
    NETTO_FONTE_NON_LETTO_DA_LUL,
    NETTO_NON_PRESENTE_O_NON_LEGGIBILE,
    NETTO_VERIFICATO_DA_CEDOLINO,
)
from app.services import cedolini_manager as manager
from app.services import cedolini_versioni as versioni
from app.services import hr_cedolini_deposito as deposito
from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from tests.hr.test_hr_cedolini_deposito import ConnessioneFinta, _configura

CF = "RSSMRA80A01H501U"


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _pdf(testo: str) -> bytes:
    documento = fitz.open()
    pagina = documento.new_page()
    pagina.insert_text((72, 72), testo)
    contenuto = documento.tobytes()
    documento.close()
    return contenuto


def _busta(netto, **extra):
    # Giugno 2025: fuori dalla finestra della Prima Nota salari (dal 12/2025),
    # cosi' la prima versione non nasce con una riga di Prima Nota, che per
    # regola rende il gruppo `da_decidere` (vedi il test sull'archivio).
    base = {
        "codice_fiscale": CF, "nome_dipendente": "ROSSI MARIO", "anno": 2025, "mese": 6,
        "tipo_cedolino": "mensile", "netto": netto, "netto_mese": netto, "lordo": 2000.0,
        "totale_trattenute": 2000.0 - netto, "stato_netto": NETTO_VERIFICATO_DA_CEDOLINO,
        "netto_fonte": NETTO_FONTE_CELLA, "canale": "drive",
    }
    base.update(extra)
    return base


def _risultati():
    return {"cedolini_processati": 0, "buste_senza_netto": 0, "anagrafiche_create": 0,
            "prima_nota_create": 0, "riconciliati": 0, "errori": []}


def _pipeline(monkeypatch):
    depositi = []

    async def _prop(*a, **k):
        return {}

    async def _no(*a, **k):
        return False

    async def _deposito(cedolino, **k):
        depositi.append(dict(cedolino))
        return {"esito": "inserito", "id": "hr-1"}

    monkeypatch.setattr("app.services.event_bus.propagate_event", _prop)
    monkeypatch.setattr(manager, "riconcilia_stipendio_automatico", _no)
    monkeypatch.setattr(deposito, "deposita_cedolino_in_hr", _deposito)
    db = ClientArchivioMemoria()["versioni-test"]
    return db, depositi


def _registra(db, busta, *, filename, pdf_text="", results=None):
    results = results if results is not None else _risultati()
    # Un PDF diverso per file: la chiave documentale del registro ne usa l'impronta.
    pdf_data = base64.b64encode(b"%PDF-1.4 " + filename.encode()).decode()
    _run(manager.registra_busta(db, dict(busta), filename=filename, pdf_data=pdf_data,
                                pdf_text=pdf_text, results=results))
    return results


def _righe(db):
    return _run(db["cedolini"].find({}, {"_id": 0, "pdf_data": 0}).sort("created_at", 1).to_list(None))


# ── regole di decisione ──────────────────────────────────────────────────────

def test_la_definitiva_batte_la_stampa_di_controllo():
    bozza = {"id": "a", "netto": 1400.0, "filename": "busta.pdf",
             "pdf_text": "ELABORAZIONE VERSIONE 1.0 DI CONTROLLO", **_busta(1400.0)}
    definitiva = {"id": "b", "netto": 1500.0, "filename": "busta (2).pdf", **_busta(1500.0)}
    for ordine in ([bozza, definitiva], [definitiva, bozza]):
        esito = versioni.decidi(ordine)
        assert esito["esito"] == versioni.ESITO_VINCITORE
        assert esito["vincitore"]["id"] == "b" and [p["id"] for p in esito["perdenti"]] == ["a"]
        assert "stampa di controllo" in esito["motivo"]


def test_la_variante_due_batte_la_variante_uno_e_l_assente():
    v1 = {"id": "v1", "filename": "Cedolino Rossi VARIANTE 1.pdf", **_busta(1500.0)}
    v2 = {"id": "v2", "filename": "Cedolino Rossi Variante 2.pdf", **_busta(1520.0)}
    senza = {"id": "s", "filename": "LUL 2026-06.pdf", **_busta(1490.0)}
    esito = versioni.decidi([senza, v1, v2])
    assert esito["esito"] == versioni.ESITO_VINCITORE and esito["vincitore"]["id"] == "v2"
    assert sorted(p["id"] for p in esito["perdenti"]) == ["s", "v1"]
    assert versioni.variante_di(v2) == 2 and versioni.variante_di(senza) is None


def test_due_netti_senza_marcatore_non_si_decidono():
    esito = versioni.decidi([{"id": "a", "filename": "a.pdf", **_busta(1500.0)},
                             {"id": "b", "filename": "b.pdf", **_busta(1490.0)}])
    assert esito["esito"] == versioni.ESITO_DA_DECIDERE and esito["vincitore"] is None
    assert "decide il titolare" in esito["motivo"]
    # stesso netto: sono copie, non versioni (se ne occupa doppioni_archivio)
    assert versioni.decidi([{"id": "a", **_busta(1500.0)}, {"id": "b", **_busta(1500.0)}])["esito"] == "stesso_netto"


# ── all'arrivo di una busta ─────────────────────────────────────────────────

def test_definitiva_dopo_stampa_di_controllo_la_sostituisce(monkeypatch):
    db, depositi = _pipeline(monkeypatch)
    r1 = _registra(db, _busta(1400.0), filename="Rossi 2026-06.pdf",
                   pdf_text="ELABORAZIONE VERSIONE 1.0 DI CONTROLLO\nTOTALE NETTO 1.400,00")
    assert r1["cedolini_processati"] == 1
    r2 = _registra(db, _busta(1500.0), filename="Rossi 2026-06 (2).pdf", pdf_text="TOTALE NETTO 1.500,00")
    assert r2["cedolini_processati"] == 1 and r2.get("versioni_da_decidere") is None

    righe = {r["netto"]: r for r in _righe(db)}
    assert set(righe) == {1400.0, 1500.0}
    bozza, definitiva = righe[1400.0], righe[1500.0]
    assert bozza["status"] == versioni.STATUS_SOSTITUITO and bozza["sostituito_da"] == definitiva["id"]
    assert bozza["stampa_di_controllo"] is True and definitiva["stampa_di_controllo"] is False
    assert definitiva.get("status") != versioni.STATUS_SOSTITUITO
    assert definitiva["rettificato"] is True and definitiva["n_versioni_totali"] == 2
    assert [s["id"] for s in definitiva["versioni_scartate"]] == [bozza["id"]]
    assert definitiva["storico_netto"][-1]["prima"] == 1400.0 and definitiva["storico_netto"][-1]["dopo"] == 1500.0
    assert definitiva["netto_fonte"] == NETTO_FONTE_CELLA
    # la riga HR segue il vincitore: l'ultimo deposito porta `rettificato`
    assert depositi[-1]["id"] == definitiva["id"] and depositi[-1]["rettificato"] is True
    # una versione sostituita non si conta come costo del personale
    assert all(r["netto"] == 1500.0 for r in _run(db["cedolini"].find(
        {"status": {"$nin": list(versioni.STATI_NON_ATTIVI)}}, {"_id": 0}).to_list(None)))


def test_stampa_di_controllo_dopo_la_definitiva_nasce_gia_sostituita(monkeypatch):
    db, depositi = _pipeline(monkeypatch)
    _registra(db, _busta(1500.0), filename="Rossi 2026-06.pdf", pdf_text="TOTALE NETTO 1.500,00")
    prima_nota_prima = _run(db["prima_nota_salari"].count_documents({}))
    depositi.clear()
    r2 = _registra(db, _busta(1400.0), filename="Rossi 2026-06 (dup2).pdf",
                   pdf_text="ELABORAZIONE VERSIONE 1.0 DI CONTROLLO\nTOTALE NETTO 1.400,00")
    assert r2["cedolini_processati"] == 0 and r2["sostituite"] == 1
    assert r2["dettaglio"][-1]["esito"] == "sostituita"
    righe = {r["netto"]: r for r in _righe(db)}
    definitiva, bozza = righe[1500.0], righe[1400.0]
    assert bozza["status"] == versioni.STATUS_SOSTITUITO and bozza["sostituito_da"] == definitiva["id"]
    assert _run(db["cedolini"].find_one({"id": bozza["id"]}))["pdf_data"]   # il PDF resta consultabile
    assert definitiva.get("status") != versioni.STATUS_SOSTITUITO
    # niente Prima Nota, niente HR, niente anagrafica per la versione superata
    assert _run(db["prima_nota_salari"].count_documents({})) == prima_nota_prima
    assert depositi == []
    assert _run(db["dipendenti"].find_one({"codice_fiscale": CF}))["ultimo_netto"] == 1500.0
    # `processa_tutti_cedolini_pdf` tratta la sostituita come un esito, non un guasto
    assert (r2["cedolini_processati"] or r2["buste_senza_netto"] or r2.get("gia_presenti") or r2.get("sostituite"))


def test_variante_due_dopo_variante_uno(monkeypatch):
    db, _ = _pipeline(monkeypatch)
    _registra(db, _busta(1500.0), filename="Rossi 2026-06 Variante 1.pdf")
    _registra(db, _busta(1520.0), filename="Rossi 2026-06 Variante 2.pdf")
    righe = {r["netto"]: r for r in _righe(db)}
    assert righe[1500.0]["status"] == versioni.STATUS_SOSTITUITO and righe[1500.0]["variante"] == 1
    assert righe[1520.0]["variante"] == 2 and "Variante 2" in righe[1500.0]["sostituito_motivo"]


def test_senza_marcatore_restano_tutte_e_due_da_decidere(monkeypatch):
    db, _ = _pipeline(monkeypatch)
    _registra(db, _busta(1500.0), filename="Rossi 2026-06.pdf")
    r2 = _registra(db, _busta(1490.0), filename="LUL 2026-06 pagina 3.pdf")
    assert r2["cedolini_processati"] == 1 and r2["versioni_da_decidere"] == 1
    righe = _righe(db)
    assert len(righe) == 2
    assert all(r["varianti_da_decidere"] is True and r.get("status") != versioni.STATUS_SOSTITUITO for r in righe)
    assert "decide il titolare" in righe[0]["varianti_motivo"]


def test_una_riga_pagata_non_si_sostituisce_mai(monkeypatch):
    db, _ = _pipeline(monkeypatch)
    _registra(db, _busta(1400.0), filename="Rossi 2026-06.pdf",
              pdf_text="ELABORAZIONE VERSIONE 1.0 DI CONTROLLO")
    bozza = _righe(db)[0]
    _run(db["cedolini"].update_one({"id": bozza["id"]}, {"$set": {"pagato": True, "importo_pagato": 1400.0}}))
    r2 = _registra(db, _busta(1500.0), filename="Rossi 2026-06 (2).pdf")
    assert r2["cedolini_processati"] == 1 and r2["versioni_da_decidere"] == 1
    righe = {r["netto"]: r for r in _righe(db)}
    assert righe[1400.0]["pagato"] is True and righe[1400.0].get("status") != versioni.STATUS_SOSTITUITO
    assert righe[1400.0]["varianti_da_decidere"] is True and righe[1500.0]["varianti_da_decidere"] is True
    assert "pagata" in righe[1500.0]["varianti_motivo"]


def test_una_riga_in_prima_nota_non_si_sostituisce_dal_giro_d_archivio():
    db = ClientArchivioMemoria()["versioni-archivio"]
    _run(db["cedolini"].insert_one({"id": "a", "filename": "Rossi Variante 1.pdf", **_busta(1500.0)}))
    _run(db["cedolini"].insert_one({"id": "b", "filename": "Rossi Variante 2.pdf", **_busta(1520.0)}))
    _run(db["prima_nota_salari"].insert_one({"id": "pn", "cedolino_id": "a", "importo_busta": 1500.0}))
    rapporto = _run(versioni.rapporto_archivio(db))
    assert rapporto["gruppi"] == 1 and rapporto["conteggi"] == {versioni.ESITO_DA_DECIDERE: 1}
    assert "Prima Nota" in rapporto["voci"][0]["motivo"]
    # lo stesso vale all'arrivo: la Variante 3 non supera una versione gia' in Prima Nota
    arrivo = _run(versioni.decidi_arrivo(db, {**_busta(1530.0), "cedolino_dedup_key": "z"},
                                         filename="Rossi Variante 3.pdf"))
    assert arrivo["esito"] == versioni.ESITO_DA_DECIDERE and "Prima Nota" in arrivo["motivo"]
    esito = _run(versioni.giro(db, dry_run=False))
    assert esito["conteggi"] == {versioni.ESITO_DA_DECIDERE: 1}
    assert _run(db["cedolini"].find_one({"id": "a"}))["varianti_da_decidere"] is True
    assert _run(db["cedolini"].find_one({"id": "a"})).get("status") != versioni.STATUS_SOSTITUITO


# ── HR segue il vincitore ───────────────────────────────────────────────────

class _ConnessioneConAggiornamento(ConnessioneFinta):
    """La finta del deposito piu' l'UPDATE `doc || patch` della versione vincente."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.aggiornamenti = []

    async def fetch(self, sql, *args):
        righe = await super().fetch(sql, *args)
        if "app_cedolini" in sql:
            per_id = {d["id"]: d for d in self.cedolini}
            for r in righe:
                r["netto"] = per_id[r["id"]].get("netto")
                r["storico_netto"] = per_id[r["id"]].get("storico_netto")
        return righe

    async def execute(self, sql, *args):
        if sql.startswith("UPDATE"):
            riga_id, patch = args
            self.aggiornamenti.append((riga_id, json.loads(patch)))
            return "UPDATE 1"
        return await super().execute(sql, *args)


def test_la_riga_hr_segue_il_vincitore_e_conserva_il_netto_di_prima(monkeypatch):
    hr = {"id": "hr-1", "codice_fiscale": CF, "anno": 2025, "mese": 6, "tipo_cedolino": "ordinario",
          "netto": 1400.0, "cedolino_dedup_key": "vecchia", "storico_netto": [{"prima": 1399.0, "dopo": 1400.0}]}
    con = _ConnessioneConAggiornamento(cedolini=[hr])
    _configura(monkeypatch, con)
    vincitore = {"id": "erp-2", "cedolino_dedup_key": "nuova", "filename": "definitiva.pdf",
                 "rettificato": True, **_busta(1500.0)}
    esito = _run(deposito.deposita_cedolino_in_hr(vincitore))
    assert esito["esito"] == "aggiornato" and esito["id"] == "hr-1" and esito["netto_prima"] == 1400.0
    (riga_id, patch), = con.aggiornamenti
    assert riga_id == "hr-1" and patch["netto"] == 1500.0 and patch["rettificato"] is True
    assert patch["storico_netto"] == [{"prima": 1399.0, "dopo": 1400.0},
                                      {"prima": 1400.0, "dopo": 1500.0, "at": patch["storico_netto"][1]["at"],
                                       "fonte": "cedolini_versioni"}]
    assert patch["gestionale_cedolino_id"] == "erp-2" and patch["netto_fonte"] == NETTO_FONTE_CELLA
    assert patch["netto_riverificato_versione"] is None
    assert con.inseriti == []
    # senza `rettificato` la riga HR non si tocca (regola: mai sovrascritta)
    con.aggiornamenti.clear()
    assert _run(deposito.deposita_cedolino_in_hr({**vincitore, "rettificato": False}))["esito"] == "gia_presente"
    assert con.aggiornamenti == []


def test_una_busta_sostituita_non_crea_una_riga_hr(monkeypatch):
    con = ConnessioneFinta()
    _configura(monkeypatch, con)
    esito = _run(deposito.deposita_cedolino_in_hr({**_busta(1400.0), "status": versioni.STATUS_SOSTITUITO}))
    assert esito["esito"] == "sostituita" and con.inseriti == []


# ── netto_fonte ─────────────────────────────────────────────────────────────

def test_pagina_lul_senza_netto_ha_fonte_non_letto_da_lul_e_netto_nullo():
    from app.parsers.busta_paga_multi_template import extract_summary, parse_busta_paga_from_bytes
    from app.services.cedolini_motore import _summary_cedolino

    letto = parse_busta_paga_from_bytes(_pdf("LIBRO UNICO DEL LAVORO\nZucchetti spa\n"
                                             f"ROSSI MARIO {CF}\nPERIODO DI RETRIBUZIONE GIUGNO 2026\n"
                                             "PAGA BASE 1.396,08000\n"))
    totali = letto["totali"]
    assert totali.get("netto") is None and totali["netto_fonte"] == NETTO_FONTE_NON_LETTO_DA_LUL
    assert totali["stato_netto"] == NETTO_NON_PRESENTE_O_NON_LEGGIBILE
    busta = _summary_cedolino(extract_summary(letto), "", pdf_bytes=b"", page_start=1, page_end=1, document_pages=1)
    assert busta["netto"] is None and busta["netto_mese"] is None
    assert busta["netto_fonte"] == NETTO_FONTE_NON_LETTO_DA_LUL
    assert busta["stato_netto"] == NETTO_NON_PRESENTE_O_NON_LEGGIBILE


def test_una_busta_normale_ha_fonte_cella():
    from app.parsers.busta_paga_multi_template import _verifica_netto, extract_summary
    from app.services.cedolini_motore import _summary_cedolino

    dalla_cella = {"totali": {"netto": 1500.0, "netto_da_cella": True, "competenze": 2000.0, "trattenute": 500.0}}
    _verifica_netto(dalla_cella, "TOTALE NETTO 1.500,00")
    assert dalla_cella["totali"]["netto_fonte"] == NETTO_FONTE_CELLA
    assert dalla_cella["totali"]["stato_netto"] == NETTO_VERIFICATO_DA_CEDOLINO
    busta = _summary_cedolino(extract_summary(dalla_cella), "", pdf_bytes=b"", page_start=1, page_end=1, document_pages=1)
    assert busta["netto"] == 1500.0 and busta["netto_fonte"] == NETTO_FONTE_CELLA
    # netto dal testo (non dalla cella) o busta normale senza netto: fonte nulla
    dal_testo = {"totali": {"netto": 1500.0}}
    _verifica_netto(dal_testo, "")
    assert dal_testo["totali"]["netto_fonte"] is None
    senza = {"totali": {}}
    _verifica_netto(senza, "Zucchetti spa TOTALE NETTO")
    assert senza["totali"]["netto_fonte"] is None and senza["totali"]["stato_netto"] == NETTO_NON_PRESENTE_O_NON_LEGGIBILE
    # e la fonte arriva sul record del registro e sul deposito HR
    assert deposito.mappa_cedolino_per_hr(_busta(1500.0))["netto_fonte"] == NETTO_FONTE_CELLA


def test_il_registro_porta_la_fonte_del_netto(monkeypatch):
    db, depositi = _pipeline(monkeypatch)
    _registra(db, _busta(1500.0), filename="Rossi 2025-06.pdf", pdf_text="TOTALE NETTO 1.500,00")
    riga = _righe(db)[0]
    assert riga["netto_fonte"] == NETTO_FONTE_CELLA and riga["variante"] is None
    assert riga["stampa_di_controllo"] is False     # letto dal testo, non dedotto dal nome
    assert depositi[0]["netto_fonte"] == NETTO_FONTE_CELLA


# ── endpoint ────────────────────────────────────────────────────────────────

def test_endpoint_rapporto_e_applicazione_a_lotti(monkeypatch):
    from app.database import Database
    from app.routers import cedolini_versioni as router_versioni
    from app.utils.dependencies import get_current_admin_user

    db = ClientArchivioMemoria()["versioni-endpoint"]
    _run(db["cedolini"].insert_one({"id": "a", "filename": "Rossi 2025-06.pdf", "created_at": "2025-07-01",
                                    "pdf_data": "xx", **_busta(1400.0), "stampa_di_controllo": True}))
    _run(db["cedolini"].insert_one({"id": "b", "filename": "Rossi 2025-06 (2).pdf", "created_at": "2025-07-02",
                                    "pdf_data": "yy", **_busta(1500.0)}))
    _run(db["cedolini"].insert_one({"id": "c", "filename": "Bianchi.pdf", **_busta(900.0, codice_fiscale="BNCLGU80A01H501Z")}))
    _run(db["cedolini"].insert_one({"id": "d", "filename": "Bianchi (2).pdf", **_busta(910.0, codice_fiscale="BNCLGU80A01H501Z")}))
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))
    monkeypatch.setattr(router_versioni, "_job_task", None)

    async def _deposito(cedolino, **k):
        return {"esito": "aggiornato", "id": "hr-1"}

    monkeypatch.setattr(deposito, "deposita_cedolino_in_hr", _deposito)
    app = FastAPI()
    app.include_router(router_versioni.router, prefix="/api/cedolini")
    app.dependency_overrides[get_current_admin_user] = lambda: {"sub": "a", "role": "admin"}
    with TestClient(app) as client:
        rapporto = client.get("/api/cedolini/versioni", params={"dry_run": "true"})
        assert rapporto.status_code == 200, rapporto.text
        corpo = rapporto.json()
        assert corpo["dry_run"] is True and corpo["gruppi"] == 2
        assert corpo["conteggi"] == {versioni.ESITO_VINCITORE: 1, versioni.ESITO_DA_DECIDERE: 1}
        rossi = next(v for v in corpo["voci"] if v["chiave"]["codice_fiscale"] == "RSSMRA***")
        assert rossi["vincitore"] == "b" and rossi["perdenti"] == ["a"]
        assert {r["id"] for r in rossi["righe"]} == {"a", "b"}
        assert {"id", "filename", "netto", "stato_netto", "tipo", "canale", "pagato"} <= set(rossi["righe"][0])
        # il rapporto non scrive
        assert _run(db["cedolini"].find_one({"id": "a"})).get("status") is None

        prova = client.post("/api/cedolini/versioni/applica", params={"dry_run": "true"})
        assert prova.status_code == 200 and prova.json()["avviato"] is True
        for _ in range(50):
            stato = client.get("/api/cedolini/versioni/stato").json()
            if stato.get("stato") == "completato":
                break
        assert stato["simulazione"]["rimasti"] == 2 and stato["simulazione"]["dry_run"] is True
        assert stato["simulazione"]["conteggi"] == {versioni.ESITO_VINCITORE: 1, versioni.ESITO_DA_DECIDERE: 1}
        assert _run(db["cedolini"].find_one({"id": "a"})).get("status") is None

        vero = client.post("/api/cedolini/versioni/applica", params={"dry_run": "false"})
        assert vero.json()["avviato"] is True
        for _ in range(50):
            stato = client.get("/api/cedolini/versioni/stato").json()
            if stato.get("stato") == "completato":
                break
    assert stato["rimasti"] == 0 and stato["simulazione"] is None
    assert stato["conteggi"] == {versioni.ESITO_VINCITORE: 1, versioni.ESITO_DA_DECIDERE: 1}
    a = _run(db["cedolini"].find_one({"id": "a"}))
    b = _run(db["cedolini"].find_one({"id": "b"}))
    assert a["status"] == versioni.STATUS_SOSTITUITO and a["sostituito_da"] == "b"
    assert b["rettificato"] is True and b["versioni_scartate"][0]["id"] == "a"
    assert _run(db["cedolini"].find_one({"id": "c"}))["varianti_da_decidere"] is True
    assert _run(db["sistema_stato"].find_one({"chiave": versioni.CHIAVE_STATO}))["rimasti"] == 0
