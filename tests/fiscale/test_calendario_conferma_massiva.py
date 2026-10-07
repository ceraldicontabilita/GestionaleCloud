"""Conferma massiva del calendario fiscale decisa dal titolare (07/10/2026):
«dal 2015 ad oggi tranne Intrastat», con lo stesso writer della pagina."""
import asyncio
from datetime import date

from app.routers import fiscalita_italiana as fi
from app.services import calendario_conferme as cc
from app.services.archivio_documenti_memoria import ClientArchivioMemoria

OGGI = date(2026, 10, 7)


def _db(nome):
    return ClientArchivioMemoria()[nome]


def test_la_simulazione_conta_senza_scrivere():
    db = _db("simulazione")
    r = asyncio.run(cc.conferma_massiva(db, dal=2025, al=2026, oggi=OGGI, escludi_tipi=("INTRASTAT",), dry_run=True))
    assert r["dry_run"] and r["confermate"] > 0 and r["escluse"] > 0 and r["future"] > 0
    assert all(v["id"] for v in r["confermate_elenco"]) and all(v["tipo"] != "INTRASTAT" for v in r["confermate_elenco"])
    assert all(v["data"] <= "2026-10-07" for v in r["confermate_elenco"])
    assert asyncio.run(db["calendario_fiscale"].count_documents({})) == 0
    assert asyncio.run(db["audit_log"].count_documents({})) == 0


def test_conferma_il_passato_non_il_futuro_e_non_intrastat():
    db = _db("massiva")
    # una scadenza gia' provata dalla quietanza non si tocca
    asyncio.run(db["calendario_fiscale"].insert_one({
        "id": "iva_2026_03", "anno": 2026, "tipo": "IVA", "data": "2026-03-16", "completato": True,
        "completato_da": "quietanza_f24", "quietanza_id": "q1"}))
    r = asyncio.run(cc.conferma_massiva(db, dal=2015, oggi=OGGI, escludi_tipi=("INTRASTAT",),
                                        note="conferma del titolare", utente="titolare"))
    assert r["al"] == 2026 and set(r["per_anno"]) == {str(a) for a in range(2015, 2027)}
    assert r["confermate"] > 100 and r["gia_completate"] >= 1 and r["future"] > 0
    righe = asyncio.run(db["calendario_fiscale"].find({}, {"_id": 0}).to_list(5000))
    confermate = [x for x in righe if x.get("completato_da") == cc.COMPLETATO_DA]
    assert len(confermate) == r["confermate"]
    assert all(x["data"] <= "2026-10-07" and x["tipo"] != "INTRASTAT" for x in confermate)
    assert all(x["note_completamento"] == "conferma del titolare" for x in confermate)
    quietanza = next(x for x in righe if x["id"] == "iva_2026_03")
    assert quietanza["completato_da"] == "quietanza_f24" and quietanza["quietanza_id"] == "q1"
    # il calendario letto dalla pagina le vede come conferme manuali
    anno_2020 = asyncio.run(fi._leggi_calendario_anno(db, 2020))
    assert anno_2020 and all(s["completato"] and s["provenienza_stato"] == "conferma_manuale"
                             for s in anno_2020 if s["tipo"] != "INTRASTAT")
    assert any(not s["completato"] for s in anno_2020 if s["tipo"] == "INTRASTAT")
    # un evento di audit per scadenza confermata, con la fonte della massiva
    eventi = asyncio.run(db["audit_log"].find({"modulo": "calendario_fiscale"}, {"_id": 0}).to_list(10000))
    assert len(eventi) == r["confermate"] and {e["fonte"] for e in eventi} == {cc.FONTE_MASSIVA}
    # secondo giro: niente di nuovo
    bis = asyncio.run(cc.conferma_massiva(db, dal=2015, oggi=OGGI, escludi_tipi=("INTRASTAT",)))
    assert bis["confermate"] == 0 and bis["gia_completate"] == r["confermate"] + 1


def test_una_volta_sola_con_marcatore(monkeypatch):
    db = _db("una_volta")
    monkeypatch.setattr(cc, "_oggi", lambda: OGGI)
    prima = asyncio.run(cc.conferma_massiva_una_volta(db))
    assert prima["eseguita"] and prima["confermate"] > 100
    stato = asyncio.run(db["sistema_stato"].find_one({"chiave": cc.CONFERMA_MASSIVA_TITOLARE["chiave"]}, {"_id": 0}))
    assert stato["eseguito_il"] and stato["confermate"] == prima["confermate"]
    dopo = asyncio.run(cc.conferma_massiva_una_volta(db))
    assert dopo["eseguita"] is False and dopo["gia_fatta_il"] == stato["eseguito_il"]


def test_la_pagina_e_la_massiva_scrivono_la_stessa_riga():
    db = _db("stessa_riga")
    template = next(s for s in fi.genera_scadenze_anno(2024) if s["tipo"] == "IVA")
    uno = asyncio.run(cc.conferma_scadenza(db, anno=2024, scadenza_id=template["id"], note="a mano", template=template))
    assert uno["esito"] == "confermata"
    bis = asyncio.run(cc.conferma_scadenza(db, anno=2024, scadenza_id=template["id"], note="di nuovo", template=template))
    assert bis["esito"] == "gia_completata"
    assert asyncio.run(cc.conferma_scadenza(db, anno=2024, scadenza_id="inesistente", note=None, template=None))["esito"] == "non_trovata"
    riga = asyncio.run(db["calendario_fiscale"].find_one({"id": template["id"]}, {"_id": 0}))
    assert riga["completato"] and riga["completato_da"] == "conferma_manuale" and riga["note_completamento"] == "a mano"
