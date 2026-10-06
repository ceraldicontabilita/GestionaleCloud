"""Le fatture di un altro anno entrano come archivio storico (titolare, 06/10/2026).

Il titolare carica due anni di XML su Drive: devono stare nel gestionale, ma solo
come consultazione, fuori da Prima Nota, partite, giornale, IVA e costi.
"""
from tests.fatture._scenari_comuni import archivio_scenari, esegui, xml_fattura  # noqa: F401


def test_fattura_di_un_altro_anno_entra_come_archivio_storico(archivio_scenari):
    from app.routers.invoices.fatture_upload import process_xml_bytes

    db = archivio_scenari

    async def scenario():
        xml = xml_fattura(numero="77", data="2024-05-10")
        esito = await process_xml_bytes(db, xml, "f.xml", source="drive", applica_filtro_anno=True)
        assert esito["status"] == "imported" and esito["archivio_storico"] is True
        fatture = [f async for f in db["invoices"].find({})]
        assert len(fatture) == 1
        f = fatture[0]
        assert f["stato_import"] == "archivio_storico" and f["stato_derivati"] == "non_applicabile"
        assert f["invoice_date"] == "2024-05-10"
        # Nessun derivato contabile: niente Prima Nota, partite, giornale.
        for collezione in ("prima_nota_cassa", "prima_nota_banca", "partite_aperte", "movimenti_contabili"):
            assert [r async for r in db[collezione].find({})] == []
        # Il secondo import della stessa fattura non ne scrive una seconda.
        bis = await process_xml_bytes(db, xml, "f.xml", source="drive", applica_filtro_anno=True)
        assert bis["status"] == "duplicate"
        assert len([x async for x in db["invoices"].find({})]) == 1

    esegui(scenario())


def test_fattura_dell_anno_attivo_resta_nel_flusso_normale(archivio_scenari):
    from app.routers.invoices.fatture_upload import process_xml_bytes

    db = archivio_scenari

    async def scenario():
        esito = await process_xml_bytes(db, xml_fattura(numero="78", data="2026-05-10"), "g.xml",
                                        source="drive", applica_filtro_anno=True)
        assert esito["status"] == "imported" and not esito.get("archivio_storico")
        [f] = [x async for x in db["invoices"].find({})]
        assert f["stato_import"] == "attivo"

    esegui(scenario())
