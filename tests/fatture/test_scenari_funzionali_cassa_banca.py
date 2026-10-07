"""Collaudo funzionale 3: spostare una fattura fra Cassa e Banca.

CLAUDE.md: «Spostare una fattura fra Cassa e Banca cambia metodo, relazioni e scritture con lo stesso
ID» e «una riga con prova bancaria non si declassa mai». Dopo lo spostamento la riga e' una sola, ha il
conto di tesoreria del registro di arrivo, la fattura dice dove e' pagata e il saldo dei due registri
si e' mosso di un solo pagamento.
"""
from decimal import Decimal

import pytest

from tests.fatture._scenari_comuni import (
    FilePdf, app_prima_nota, archivio_scenari, crea_fornitore, e_pagata_su_ogni_campo, esegui, fattura,
    importa, importa_estratto, parser_pdf_con, richiesta, righe_che_contano, transazione_pdf, tutti, xml_fattura,
)

__all__ = ["archivio_scenari"]

ENDPOINT = ["/api/prima-nota/sposta-movimento", "/api/prima-nota/sposta-scrittura"]


def _d(valore) -> Decimal:
    return Decimal(str(valore))


def _corpo(endpoint: str, movimento_id: str, da: str, a: str) -> dict:
    if endpoint.endswith("sposta-movimento"):
        return {"movimento_id": movimento_id, "da": da, "a": a, "motivo": "collaudo", "conferma": True}
    return {"movimento_id": movimento_id, "destinazione": a}


async def _fattura_pagata_in_cassa(db):
    await crea_fornitore(db, metodo="contanti", iban=None)
    esito = await importa(db, xml_fattura(), "drive")
    # CLAUDE.md §29 (titolare 07/10/2026): fornitore cassa -> la riga in Prima
    # Nota Cassa nasce all'import con la data della fattura, senza conferma.
    f = await fattura(db, esito["id"])
    assert e_pagata_su_ogni_campo(f) and f["prima_nota_tipo"] == "cassa", f
    assert f["data_pagamento"] == "2026-09-10"
    return esito["id"], app_prima_nota()


@pytest.mark.parametrize("endpoint", ENDPOINT)
def test_cassa_verso_banca_stesso_id_una_riga_e_conti_del_registro_di_arrivo(archivio_scenari, endpoint):
    db = archivio_scenari

    async def scenario():
        fid, app = await _fattura_pagata_in_cassa(db)
        riga_cassa = (await tutti(db, "prima_nota_cassa"))[0]
        spostamento = await richiesta(app, "POST", endpoint, json=_corpo(endpoint, riga_cassa["id"], "cassa", "banca"))
        return {
            "fid": fid, "prima": riga_cassa, "spostamento": spostamento, "fattura": await fattura(db, fid),
            "cassa": await tutti(db, "prima_nota_cassa"), "banca": await tutti(db, "prima_nota_banca"),
            "saldo_cassa": _d((await richiesta(app, "GET", "/api/prima-nota/cassa?anno=2026&limit=100")).json()["saldo"]),
            "partite": await tutti(db, "partite_aperte"),
        }

    r = esegui(scenario())
    assert r["spostamento"].status_code == 200, r["spostamento"].text
    # lo stesso ID: la riga cambia registro, non si duplica
    assert r["cassa"] == [] and len(r["banca"]) == 1
    riga = r["banca"][0]
    assert riga["id"] == r["prima"]["id"] and riga["fattura_id"] == r["fid"]
    assert _d(riga["importo"]) == Decimal("122.00")
    # la scrittura porta il conto di tesoreria del registro di arrivo, non quello di partenza
    assert riga["conto_contabile"] == "19.01.01", riga["conto_contabile"]
    assert riga["conto_contropartita"] == "33.03.01"
    assert riga["metodo_pagamento"] == "banca"
    # la fattura dice dove e' pagata: metodo e relazioni seguono la riga
    f = r["fattura"]
    assert f["prima_nota_tipo"] == "banca" and f["prima_nota_banca_id"] == riga["id"]
    assert f["prima_nota_id"] == riga["id"] and not f.get("prima_nota_cassa_id")
    assert f["metodo_pagamento_effettivo"] == "banca", f["metodo_pagamento_effettivo"]
    assert e_pagata_su_ogni_campo(f)
    # la cassa non conta piu' il pagamento e nessuna partita si e' (ri)aperta:
    # pagata all'import, `fattura.created` non apre la partita (handler
    # on_fattura_created_crea_partita, «già pagata»)
    assert r["saldo_cassa"] == Decimal("0.00")
    assert all(p["stato"] not in ("aperta", "parziale") for p in r["partite"])


@pytest.mark.parametrize("endpoint", ENDPOINT)
def test_banca_con_prova_dell_estratto_non_si_declassa_a_cassa(archivio_scenari, monkeypatch, endpoint):
    db = archivio_scenari

    async def scenario():
        await crea_fornitore(db, metodo="bonifico")
        esito = await importa(db, xml_fattura(), "drive")
        fid = esito["id"]
        parser_pdf_con(monkeypatch, [transazione_pdf(
            "2026-09-15", "VS.DISP. RIF. MBVT12345678/001 FAVORE FORNITORE TEST SRL", -122.0)])
        await importa_estratto(FilePdf())
        app = app_prima_nota()
        prima = {"fattura": await fattura(db, fid), "banca": await tutti(db, "prima_nota_banca"),
                 "ec": await tutti(db, "estratto_conto_movimenti")}
        riga = (await righe_che_contano(db, "prima_nota_banca", fid))[0]
        spostamento = await richiesta(app, "POST", endpoint, json=_corpo(endpoint, riga["id"], "banca", "cassa"))
        return {"fid": fid, "prima": prima, "spostamento": spostamento, "fattura": await fattura(db, fid),
                "cassa": await tutti(db, "prima_nota_cassa"), "banca": await tutti(db, "prima_nota_banca"),
                "ec": await tutti(db, "estratto_conto_movimenti")}

    r = esegui(scenario())
    assert r["spostamento"].status_code == 409, r["spostamento"].text
    # nulla e' cambiato: nessuna uscita di cassa, la riga e l'addebito restano dove li ha messi la banca
    assert r["cassa"] == []
    assert r["banca"] == r["prima"]["banca"]
    assert r["ec"] == r["prima"]["ec"]
    assert r["fattura"]["prima_nota_tipo"] == "banca" == r["prima"]["fattura"]["prima_nota_tipo"]
    assert r["fattura"]["prima_nota_banca_id"] == r["prima"]["fattura"]["prima_nota_banca_id"]


def test_andata_e_ritorno_cassa_banca_cassa_conserva_id_e_non_duplica(archivio_scenari):
    db = archivio_scenari

    async def scenario():
        fid, app = await _fattura_pagata_in_cassa(db)
        riga = (await tutti(db, "prima_nota_cassa"))[0]
        andata = await richiesta(app, "POST", ENDPOINT[0], json=_corpo(ENDPOINT[0], riga["id"], "cassa", "banca"))
        ritorno = await richiesta(app, "POST", ENDPOINT[0], json=_corpo(ENDPOINT[0], riga["id"], "banca", "cassa"))
        return fid, riga, andata, ritorno, await tutti(db, "prima_nota_cassa"), await tutti(db, "prima_nota_banca"), \
            await fattura(db, fid)

    fid, riga, andata, ritorno, cassa, banca, f = esegui(scenario())
    assert andata.status_code == 200 and ritorno.status_code == 200, (andata.text, ritorno.text)
    assert banca == [] and len(cassa) == 1 and cassa[0]["id"] == riga["id"]
    assert cassa[0]["conto_contabile"] == "19.03.03"
    assert f["prima_nota_tipo"] == "cassa" and f["prima_nota_cassa_id"] == riga["id"]
    assert f["metodo_pagamento_effettivo"] == "cassa"
    assert e_pagata_su_ogni_campo(f)


def test_l_anteprima_dello_spostamento_non_scrive(archivio_scenari):
    db = archivio_scenari

    async def scenario():
        fid, app = await _fattura_pagata_in_cassa(db)
        riga = (await tutti(db, "prima_nota_cassa"))[0]
        prima = (await tutti(db, "prima_nota_cassa"), await tutti(db, "prima_nota_banca"), await fattura(db, fid))
        anteprima = await richiesta(app, "POST", "/api/prima-nota/sposta-movimento",
                                    json={"movimento_id": riga["id"], "da": "cassa", "a": "banca"})
        dopo = (await tutti(db, "prima_nota_cassa"), await tutti(db, "prima_nota_banca"), await fattura(db, fid))
        return anteprima, prima, dopo

    anteprima, prima, dopo = esegui(scenario())
    assert anteprima.status_code == 200 and anteprima.json()["preview"] is True
    assert prima == dopo
