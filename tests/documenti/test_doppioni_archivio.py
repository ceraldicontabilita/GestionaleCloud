"""Doppioni d'archivio: la stessa busta, quietanza o bonifico spostati fra i «da eliminare»."""
import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.services import cedolini_manager
from app.services import doppioni_archivio as da

CF = "RSSMRA80A01H501U"


def run(coro):
    return asyncio.run(coro)


def _ced(id_, **kw):
    return {"id": id_, "codice_fiscale": CF, "anno": 2024, "mese": 2, "tipo_cedolino": "mensile",
            "netto": 1203.0, "netto_mese": 1203.0, "lordo": 1500.0, "totale_trattenute": 297.0,
            "created_at": kw.pop("created_at", "2026-01-01"), **kw}


def _db(monkeypatch):
    db = AsyncMongoMockClient()["t"]

    async def bonifica(db, dry_run=True, actor=None):
        return {"dry_run": dry_run}

    import app.services.bonifica_prima_nota_salari_doppioni as b
    monkeypatch.setattr(b, "esegui", bonifica)
    return db


def test_la_stessa_busta_da_piu_pdf_resta_una_sola_quella_pagata(monkeypatch):
    db = _db(monkeypatch)
    run(db["cedolini"].insert_many([
        _ced("libro_unico", created_at="2026-01-01"),
        _ced("singolo", pagato=True, created_at="2026-02-01"),
        _ced("variante", created_at="2026-03-01"),
        _ced("conguaglio", netto=150.0, netto_mese=150.0),                  # importo diverso: resta
        _ced("quattordicesima", tipo_cedolino="quattordicesima"),          # tipo diverso: resta
    ]))
    run(db["prima_nota_salari"].insert_one({"id": "pn1", "cedolino_id": "variante"}))

    prova = run(da.ripulisci(db, dry_run=True))
    assert prova["cedolini"]["copie"] == 2
    assert run(db["cedolini"].count_documents({})) == 5                    # dry_run non tocca nulla

    run(da.ripulisci(db, dry_run=False, actor="test"))
    rimasti = {d["id"] for d in run(db["cedolini"].find({}).to_list(None))}
    assert rimasti == {"singolo", "conguaglio", "quattordicesima"}
    cartella = {d["id"]: d for d in run(db["cedolini_quarantena"].find({}).to_list(None))}
    assert set(cartella) == {"libro_unico", "variante"}
    assert cartella["variante"]["duplicato_di"] == "singolo" and cartella["variante"]["motivo_quarantena"] == "doppione"
    assert run(db["prima_nota_salari"].find_one({"id": "pn1"}))["cedolino_id"] == "singolo"
    assert run(da.ripulisci(db, dry_run=True))["cedolini"]["copie"] == 0   # seconda passata: niente


def test_quietanze_per_protocollo_e_bonifici_per_cro(monkeypatch):
    db = _db(monkeypatch)
    run(db["quietanze_f24"].insert_many([
        {"id": "q1", "protocollo_telematico": "ABC123", "created_at": "2026-01-02"},
        {"id": "q2", "protocollo_telematico": "abc123 ", "f24_associati": ["f1"], "created_at": "2026-01-03"},
        {"id": "q3", "protocollo_telematico": "XYZ999"},
    ]))
    run(db["f24_unificato"].insert_one({"id": "f1", "quietanza_id": "q1"}))
    run(db["bonifici_transfers"].insert_many([
        {"id": "b1", "cro_trn": "0306912345", "importo": 1063.0, "beneficiario": {"nome": "VESPA VINCENZO"}},
        {"id": "b2", "cro_trn": "0306912345", "importo": 1063.0, "beneficiario": {"nome": "RICEVUTA PER ORDINANTE"},
         "created_at": "2020-01-01"},
        {"id": "b4", "cro_trn": "0306912345", "importo": 500.0, "beneficiario": {"nome": "ALTRO"}},
        {"id": "b3", "cro_trn": "", "data": "2026-03-01", "importo": 100, "beneficiario": {"nome": "Rossi"}},
    ]))
    run(da.ripulisci(db, dry_run=False))
    assert {d["id"] for d in run(db["quietanze_f24"].find({}).to_list(None))} == {"q2", "q3"}
    assert run(db["f24_unificato"].find_one({"id": "f1"}))["quietanza_id"] == "q2"
    # Resta la copia col beneficiario letto bene; un importo diverso sullo stesso CRO resta.
    assert {d["id"] for d in run(db["bonifici_transfers"].find({}).to_list(None))} == {"b1", "b3", "b4"}
    assert run(db["bonifici_transfers_quarantena"].find_one({"id": "b2"}))["duplicato_di"] == "b1"


def test_gli_f24_gia_in_quarantena_passano_nella_cartella(monkeypatch):
    db = _db(monkeypatch)
    run(db["f24_unificato"].insert_many([
        {"id": "resta", "status": "pagato"},
        {"id": "copia", "status": "eliminato", "motivo_quarantena": "doppione", "doppione_di": "resta"},
    ]))
    run(da.ripulisci(db, dry_run=False))
    assert [d["id"] for d in run(db["f24_unificato"].find({}).to_list(None))] == ["resta"]
    assert run(db["f24_unificato_quarantena"].find_one({"id": "copia"}))["duplicato_di"] == "resta"


def test_un_secondo_pdf_della_stessa_busta_non_crea_un_cedolino(monkeypatch):
    db = AsyncMongoMockClient()["t"]
    run(db["cedolini"].insert_one(_ced("gia")))
    chiamato = []

    async def v2(**kw):
        chiamato.append(kw)
        return {"success": True}

    import app.services.salari_unificati_v2 as sal
    monkeypatch.setattr(sal, "processa_cedolino_v2", v2)
    esito = {"errori": [], "cedolini_processati": 0, "buste_senza_netto": 0}
    busta = _ced(None, stato_netto="NETTO_VERIFICATO_DA_CEDOLINO")
    busta.pop("id")
    run(cedolini_manager.registra_busta(db, busta, filename="Libro unico (44).pdf", pdf_data=None,
                                        pdf_text="", results=esito))
    assert chiamato == [] and esito["gia_presenti"] == 1
    assert run(db["cedolini"].find_one({"id": "gia"}))["source_occurrences"][0]["filename"] == "Libro unico (44).pdf"


def test_la_pulizia_e_riservata_all_admin():
    from app.routers.doppioni_archivio import router
    from app.utils.ruoli import richiedi_admin

    assert richiedi_admin in [d.dependency for d in router.dependencies]
