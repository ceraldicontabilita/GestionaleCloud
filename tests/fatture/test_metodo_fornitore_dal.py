"""«Sempre per cassa dal 01/01/2025»: il metodo del fornitore vale nel tempo, senza forzare."""
import asyncio

import pytest
from fastapi import HTTPException

from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services import metodo_fornitore_dal as md

PIVA = "06356400637"


def _run(coro):
    return asyncio.run(coro)


def _fattura(idf, data, importo, **extra):
    return {"id": idf, "invoice_number": f"N{idf}", "invoice_date": data, "total_amount": importo,
            "supplier_vat": PIVA, "supplier_name": "BIG FOOD SRL", "tipo_documento": "TD01",
            "status": "imported", **extra}


@pytest.fixture
def db(monkeypatch):
    from app.database import Database

    d = ClientArchivioMemoria()["metodo_dal"]
    monkeypatch.setattr(Database, "get_db", classmethod(lambda cls: d))
    return d


async def _scenario_dati(db):
    await db["fornitori"].insert_one({
        "id": 381, "partita_iva": PIVA, "ragione_sociale": "BIG FOOD SRL",
        "metodo_pagamento": "cassa", "metodo_pagamento_dal": "2025-01-01"})
    await db["invoices"].insert_many([
        _fattura("a1", "2026-09-23", 784.43, stato_finanziario="provvisoria"),          # aperta: da chiudere
        _fattura("a2", "2026-09-25", 425.08, stato_finanziario="provvisoria"),          # aperta: da chiudere
        _fattura("p1", "2026-01-09", 34.73, pagato=True, prima_nota_tipo="cassa",
                 prima_nota_id="pn1"),                                                   # gia' in cassa
        _fattura("b1", "2026-07-16", 663.69, pagato=True, prima_nota_tipo="banca",
                 prima_nota_id="pnb1"),                                                  # banca: non si tocca
        _fattura("d1", "2026-07-30", 131.93, prima_nota_tipo="banca", pagato=True,
                 in_attesa_riscontro_banca=True, stato_finanziario="pagata_dichiarata_in_attesa_banca"),
        _fattura("n1", "2026-06-08", 16.88, tipo_documento="TD04"),                      # nota di credito aperta
        _fattura("v1", "2024-12-20", 500.0),                                             # prima del «dal»
        _fattura("x1", "2026-05-15", 235.97, status="archived"),                         # copia archiviata: fuori
    ])
    await db["prima_nota_cassa"].insert_one({
        "id": "pn1", "fattura_id": "p1", "importo": 34.73, "source": "conferma_provvisori"})
    await db["prima_nota_banca"].insert_one({
        "id": "pnb1", "fattura_id": "b1", "importo": 663.69, "estratto_conto_id": "ec1"})


def test_piano_elenca_cosa_chiude_e_cosa_non_tocca(db):
    async def scenario():
        await _scenario_dati(db)
        f = await db["fornitori"].find_one({"id": 381})
        return await md.piano(db, f)

    p = _run(scenario())
    assert p["dal"] == "2025-01-01" and p["metodo"] == "cassa"
    assert p["fatture_dal"] == 6  # la 2024 e la copia archiviata non contano
    assert [r["id"] for r in p["da_chiudere_in_cassa"]] == ["a1", "a2"]
    assert p["residuo_da_chiudere"] == 1209.51
    assert [r["id"] for r in p["gia_in_cassa"]] == ["p1"]
    assert sorted(r["id"] for r in p["conflitto_banca_o_assegno"]) == ["b1", "d1"]
    assert [(r["id"], r["motivo"]) for r in p["non_forzate"]] == [
        ("n1", "nota di credito: la decide il titolare")]


def test_solo_la_cassa_si_applica_e_serve_la_data(db):
    with pytest.raises(HTTPException) as e1:
        md.leggi_regola({"metodo_pagamento": "banca", "metodo_pagamento_dal": "2025-01-01"})
    assert e1.value.status_code == 409
    with pytest.raises(HTTPException) as e2:
        md.leggi_regola({"metodo_pagamento": "cassa"})
    assert e2.value.status_code == 409


def test_dry_run_non_scrive_e_l_applicazione_e_idempotente(db, monkeypatch):
    chiamate = []

    async def conferma(dati):
        chiamate.append(dati)
        fid = dati["fattura_id"]
        await db["prima_nota_cassa"].insert_one({
            "id": f"pn-{fid}", "fattura_id": fid, "importo": 1.0, "source": "conferma_provvisori"})
        await db["invoices"].update_one({"id": fid}, {"$set": {"pagato": True, "prima_nota_tipo": "cassa"}})
        return {"success": True}

    monkeypatch.setattr("app.routers.prima_nota_module.sync.conferma_fattura_provvisoria", conferma)

    async def scenario():
        await _scenario_dati(db)
        f = await db["fornitori"].find_one({"id": 381})
        anteprima = await md.applica(db, f, dry_run=True)
        assert chiamate == []  # l'anteprima non scrive nulla
        # applicazione: parte in background; si attende il suo stato
        avvio = await md.applica(db, f, dry_run=False)
        for _ in range(100):
            st = await md.stato(db, f)
            if st.get("stato") in ("completato", "errore"):
                break
            await asyncio.sleep(0.05)
        secondo = await md.piano(db, await db["fornitori"].find_one({"id": 381}))
        return anteprima, avvio, st, secondo

    anteprima, avvio, st, secondo = _run(scenario())
    assert anteprima["dry_run"] is True and len(anteprima["da_chiudere_in_cassa"]) == 2
    assert avvio["avviato"] is True
    assert st["stato"] == "completato" and st["registrate"] == 2 and st["scartate"] == 0
    assert {c["fattura_id"] for c in chiamate} == {"a1", "a2"}
    assert all(c["metodo"] == "cassa" and c["approva_metodo_fattura"] is True for c in chiamate)
    assert secondo["da_chiudere_in_cassa"] == []  # secondo giro: zero
    assert sorted(r["id"] for r in secondo["conflitto_banca_o_assegno"]) == ["b1", "d1"]  # la banca resta com'e'


def test_un_rifiuto_della_conferma_non_ferma_le_altre_e_si_legge(db, monkeypatch):
    async def conferma(dati):
        if dati["fattura_id"] == "a1":
            raise HTTPException(status_code=409, detail="La fattura ha gia' un pagamento parziale confermato.")
        return {"success": True}

    monkeypatch.setattr("app.routers.prima_nota_module.sync.conferma_fattura_provvisoria", conferma)

    async def scenario():
        await _scenario_dati(db)
        f = await db["fornitori"].find_one({"id": 381})
        await md.applica(db, f, dry_run=False)
        for _ in range(100):
            st = await md.stato(db, f)
            if st.get("stato") in ("completato", "errore"):
                return st
            await asyncio.sleep(0.05)

    st = _run(scenario())
    assert st["registrate"] == 1 and st["scartate"] == 1
    assert [e for e in st["esiti"] if e["esito"] == "rifiutata"][0]["motivo"].startswith("La fattura ha gia'")
