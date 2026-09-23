"""Due chiusure RT dello stesso giorno si sommano; la giornata storica senza
documento la sostituisce il suo XML, anche con qualche euro di differenza.

Casi veri del 23/09/2026 (ZIP «fileProdotto1» delle chiusure RT):
- 06/09: progressivi 2637 (597,40) e 2638 (1.599,50); la seconda era
  scartata come doppione perche' stesso giorno e stesso registratore.
- 08/07: chiusura storica 2.082,50 (imponibile + IVA) e XML 2.077,30
  (contanti + elettronico): non si riconoscevano, e i contanti entravano
  due volte in Prima Nota Cassa.
- 17/07: la seconda chiusura e' vuota (0 scontrini) e non sostituisce nulla.
"""
import asyncio

from app.routers.invoices.corrispettivi_helpers import (
    ingest_corrispettivo_parsed,
    ritira_giornate_superate,
)
from app.services.archivio_documenti_memoria import ClientArchivioMemoria

RT = "99MEY026532"


def _db():
    return ClientArchivioMemoria()["chiusure_stesso_giorno"]


def _xml(data, progressivo, contanti, elettronico, documenti=50):
    totale = round(contanti + elettronico, 2)
    iva = round(totale / 11, 2)
    return {
        "corrispettivo_key": f"04523831214_{data}_{RT}_{progressivo}",
        "data": data, "matricola_rt": RT, "numero_documento": progressivo,
        "partita_iva": "04523831214",
        "pagato_contanti": contanti, "pagato_elettronico": elettronico,
        "totale_imponibile": round(totale - iva, 2), "totale_iva": iva,
        "totale": totale, "numero_documenti": documenti,
    }


async def _storica(db, data, totale, contanti, elettronico, id_=606):
    await db["corrispettivi"].insert_one({
        "id": id_, "data": data, "totale": totale, "pagato_contanti": contanti,
        "pagato_elettronico": elettronico, "status": "DA_VERIFICARE",
        "fonte": "legacy_staging_2026",
    })
    await db["prima_nota_cassa"].insert_one({
        "id": f"pn-{id_}", "data": data, "tipo": "entrata", "categoria": "Corrispettivi",
        "importo": contanti, "corrispettivo_id": str(id_), "source": "corrispettivo_import",
    })


async def _attivi(db, data):
    return [r for r in await db["corrispettivi"].find({"data": data}).to_list(20)
            if r.get("status") != "deleted"]


async def _cassa(db, data):
    return sorted(r["importo"] for r in await db["prima_nota_cassa"].find(
        {"data": data, "categoria": "Corrispettivi"}).to_list(20))


def test_due_chiusure_dello_stesso_giorno_si_sommano():
    async def scenario():
        db = _db()
        prima = await ingest_corrispettivo_parsed(db, _xml("2026-09-06", "2637", 132.30, 465.10))
        seconda = await ingest_corrispettivo_parsed(db, _xml("2026-09-06", "2638", 400.00, 1199.50))
        ancora = await ingest_corrispettivo_parsed(db, _xml("2026-09-06", "2638", 400.00, 1199.50))
        return prima, seconda, ancora, await _attivi(db, "2026-09-06"), await _cassa(db, "2026-09-06")

    prima, seconda, ancora, righe, cassa = asyncio.run(scenario())
    assert (prima["action"], seconda["action"], ancora["action"]) == ("created", "created", "duplicate")
    assert round(sum(r["totale"] for r in righe), 2) == 2196.90
    assert cassa == [132.30, 400.00]  # la seconda non cancella la cassa della prima


def test_xml_sostituisce_la_giornata_storica_con_totale_diverso():
    async def scenario():
        db = _db()
        await _storica(db, "2026-07-08", 2082.50, 730.40, 1346.90)
        esito = await ingest_corrispettivo_parsed(db, _xml("2026-07-08", "2584", 730.40, 1346.90))
        di_nuovo = await ingest_corrispettivo_parsed(db, _xml("2026-07-08", "2584", 730.40, 1346.90))
        vecchia = await db["corrispettivi"].find_one({"id": 606})
        return esito, di_nuovo, vecchia, await _attivi(db, "2026-07-08"), await _cassa(db, "2026-07-08")

    esito, di_nuovo, vecchia, righe, cassa = asyncio.run(scenario())
    assert esito["action"] == "created"
    assert esito["sostituisce"]["prima_nota_rimosse"] == 1
    assert di_nuovo["action"] == "duplicate"
    assert vecchia["status"] == "deleted" and vecchia["sostituito_da"] == esito["corrispettivo_id"]
    assert [r["totale"] for r in righe] == [2077.30]
    assert cassa == [730.40]  # i contanti una volta sola


def test_chiusura_vuota_non_sostituisce_la_giornata():
    async def scenario():
        db = _db()
        await _storica(db, "2026-07-17", 2375.40, 568.10, 1807.30, id_=615)
        await ingest_corrispettivo_parsed(db, _xml("2026-07-17", "2594", 0, 0, documenti=0))
        return await _attivi(db, "2026-07-17"), await _cassa(db, "2026-07-17")

    righe, cassa = asyncio.run(scenario())
    assert sorted(r["totale"] for r in righe) == [0, 2375.40]
    assert cassa == [568.10]


def test_ritiro_una_tantum_delle_giornate_gia_doppie():
    async def scenario():
        db = _db()
        await _storica(db, "2026-07-10", 2446.80, 641.80, 1802.50, id_=608)
        # l'XML entrato prima della correzione: riga propria accanto alla storica
        await db["corrispettivi"].insert_one({
            "id": "xml-0710", "data": "2026-07-10", "totale": 2444.30, "pagato_contanti": 641.80,
            "corrispettivo_key": f"04523831214_2026-07-10_{RT}_2586",
            "matricola_rt": RT, "status": "imported",
        })
        await db["prima_nota_cassa"].insert_one({
            "id": "pn-xml-0710", "data": "2026-07-10", "tipo": "entrata",
            "categoria": "Corrispettivi", "importo": 641.80, "corrispettivo_id": "xml-0710",
        })
        anteprima = await ritira_giornate_superate(db, dry_run=True)
        fatto = await ritira_giornate_superate(db, dry_run=False)
        ancora = await ritira_giornate_superate(db, dry_run=False)
        return anteprima, fatto, ancora, await _attivi(db, "2026-07-10"), await _cassa(db, "2026-07-10")

    anteprima, fatto, ancora, righe, cassa = asyncio.run(scenario())
    assert anteprima["giornate"] == 1 and anteprima["dry_run"] is True
    assert fatto["dettaglio"][0]["sostituito_da"] == "xml-0710"
    assert ancora["giornate"] == 0
    assert [r["id"] for r in righe] == ["xml-0710"]
    assert cassa == [641.80]


def test_contanti_diversi_non_provano_la_stessa_chiusura():
    """Stesso giorno ma contanti diversi: non e' provato che sia la stessa
    chiusura, e la riga storica non si tocca."""
    async def scenario():
        db = _db()
        await _storica(db, "2026-07-12", 1695.00, 500.00, 1195.00, id_=612)
        esito = await ingest_corrispettivo_parsed(db, _xml("2026-07-12", "2588", 480.00, 1209.70))
        return esito, await _attivi(db, "2026-07-12")

    esito, righe = asyncio.run(scenario())
    assert esito["action"] == "created" and not esito.get("sostituisce")
    assert len(righe) == 2


def test_ricaricare_completa_una_sostituzione_interrotta():
    """Riavvio a meta' (23/09/2026, 16:21): la chiusura XML era entrata ma la
    giornata storica no ritirata. Ricaricare lo stesso file la ritira."""
    async def scenario():
        db = _db()
        await _storica(db, "2026-07-07", 1762.40, 595.10, 1167.30, id_=605)
        await db["corrispettivi"].insert_one({
            "id": "xml-0707", "data": "2026-07-07", "totale": 1762.40, "pagato_contanti": 595.10,
            "corrispettivo_key": f"04523831214_2026-07-07_{RT}_2583", "matricola_rt": RT,
            "numero_documento": "2583", "status": "imported",
        })
        esito = await ingest_corrispettivo_parsed(db, _xml("2026-07-07", "2583", 595.10, 1167.30))
        vecchia = await db["corrispettivi"].find_one({"id": 605})
        return esito, vecchia, await _attivi(db, "2026-07-07")

    esito, vecchia, righe = asyncio.run(scenario())
    assert esito["action"] == "duplicate"
    assert vecchia["status"] == "deleted" and vecchia["sostituito_da"] == "xml-0707"
    assert [r["id"] for r in righe] == ["xml-0707"]


def test_il_ritiro_toglie_la_cassa_ricreata_per_la_giornata_ritirata():
    async def scenario():
        db = _db()
        await db["corrispettivi"].insert_one({
            "id": 606, "data": "2026-07-08", "totale": 2082.50, "pagato_contanti": 730.40,
            "status": "deleted", "deleted_reason": "sostituita_da_chiusura_xml",
        })
        await db["prima_nota_cassa"].insert_one({
            "id": "pn-ricreata", "data": "2026-07-08", "categoria": "Corrispettivi",
            "importo": 730.40, "corrispettivo_id": "606",
        })
        esito = await ritira_giornate_superate(db, dry_run=False)
        return esito, await _cassa(db, "2026-07-08")

    esito, cassa = asyncio.run(scenario())
    assert esito["prima_nota_ritirate_rimosse"] == 1
    assert cassa == []


def test_il_giro_della_prima_nota_salta_le_giornate_ritirate(monkeypatch):
    from app.routers.prima_nota_module import sync as modulo

    db = _db()
    monkeypatch.setattr(modulo.Database, "get_db", staticmethod(lambda: db))

    async def scenario():
        await db["corrispettivi"].insert_one({
            "id": 606, "data": "2026-07-08", "anno": 2026, "totale": 2082.50,
            "pagato_contanti": 730.40, "status": "deleted",
            "deleted_reason": "sostituita_da_chiusura_xml",
        })
        await modulo._sync_corrispettivi_impl(2026)
        return await _cassa(db, "2026-07-08")

    assert asyncio.run(scenario()) == []
