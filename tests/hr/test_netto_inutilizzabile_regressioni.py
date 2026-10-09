"""Un errore di lettura non riattiva importi precedenti o campi alternativi."""
import asyncio
from decimal import Decimal
import pytest
from app.constants.stati_netto import STATI_NON_UTILIZZABILI, NETTO_VERIFICATO_DA_CEDOLINO
from app.services.hr_cedolini_deposito import mappa_cedolino_per_hr
from app.services.posizione_dipendente import dovuto_busta
from app.services.archivio_documenti_memoria import ArchivioDocumenti


@pytest.mark.parametrize("stato", STATI_NON_UTILIZZABILI)
def test_mappa_non_riattiva_fallback_e_conserva_prova(stato):
    originale = {"codice_fiscale": "RSSMRA80A01H501U", "anno": 2025, "mese": 10,
                 "netto": None, "netto_mese": 900, "netto_pagato": 800,
                 "stato_netto": stato, "dati_chiave": {"prova": "pagina 1"}}
    doc = mappa_cedolino_per_hr(originale)
    assert doc["netto"] is None
    assert doc["stato_netto"] == stato
    assert doc["dati_chiave"]["prova"] == "pagina 1"
    assert doc["dati_chiave"]["netto_non_verificato"]["netto_mese"] == 900
    assert originale["dati_chiave"] == {"prova": "pagina 1"}


@pytest.mark.parametrize("stato", STATI_NON_UTILIZZABILI)
def test_dovuto_non_riattiva_registro_o_cella_storica(stato):
    ced = {"netto": 900, "netto_busta": 800, "stato_netto": stato}
    assert dovuto_busta({"importo_busta": 1000}, ced)["dovuto"] is None
    manuale = dovuto_busta({"importo_busta": 1100, "importo_busta_manuale": True,
                           "netto_confermato": 1100}, ced)
    assert manuale["dovuto"] == Decimal("1100.00") and manuale["manuale"] is True


def test_legacy_senza_stato_e_zero_verificato_restano_utilizzabili():
    assert dovuto_busta({}, {"netto": 900})["dovuto"] == Decimal("900.00")
    doc = mappa_cedolino_per_hr({"codice_fiscale": "RSSMRA80A01H501U", "anno": 2025,
                               "mese": 10, "netto_pagato": 800})
    assert doc["netto"] == 800
    assert dovuto_busta({"importo_busta": 900}, {"netto": 0,
        "stato_netto": NETTO_VERIFICATO_DA_CEDOLINO})["dovuto"] == Decimal("0.00")


def test_sync_ambiguo_annulla_importo_storico_preserva_documento_e_segnala_verifica(monkeypatch):
    from app.hr.services.sincronizza_paghe_mensili import sincronizza
    from app.hr.routers import dipendenti_cloud as router
    db, erp = ArchivioDocumenti("hr"), ArchivioDocumenti("erp")
    monkeypatch.setattr(router, "_db_gestionale", lambda: erp)
    async def scenario():
        await db.dipendenti.insert_one({"id": "d"})
        await db.cedolini.insert_one({"id": "c", "dipendente_id": "d", "anno": 2025,
            "mese": 10, "tipo_cedolino": "ordinario", "netto": 900,
            "stato_netto": "MULTIPLE_NETS_DA_VERIFICARE", "dati_chiave": {"prova": [900, 800]}})
        await db.paghe_mensili.insert_one({"dipendente_id": "d", "anno": 2025, "mese": 10,
            "importo_busta": 1000, "origine": "cedolino"})
        for _ in range(2):
            await sincronizza(db)
            paga = await db.paghe_mensili.find_one({"dipendente_id": "d"})
            assert paga["importo_busta"] is None and paga["saldo"] is None
            assert paga["stato_pagamento"] == "da_verificare"
        ced = await db.cedolini.find_one({"id": "c"})
        assert ced["netto"] == 900 and ced["dati_chiave"] == {"prova": [900, 800]}
    asyncio.run(scenario())


def test_versione_vincente_ambigua_invalida_netto_hr_precedente():
    import json
    from app.services.hr_cedolini_deposito import _segui_vincitore
    class Connessione:
        def __init__(self):
            self.patch = None
        async def execute(self, sql, id_, patch):
            assert id_ == "c"
            self.patch = json.loads(patch)
    con = Connessione()
    doc = {"codice_fiscale": "CF", "anno": 2025, "mese": 10, "tipo_cedolino": "ordinario",
           "netto": None, "stato_netto": "MULTIPLE_NETS_DA_VERIFICARE",
           "dati_chiave": {"netto_non_verificato": {"netto_mese": 900}}}
    esito = asyncio.run(_segui_vincitore(con, {"id": "c", "netto": 900}, doc, "k", dry_run=False))
    assert esito["esito"] == "aggiornato"
    assert con.patch["netto"] is None
    assert con.patch["stato_netto"] == "MULTIPLE_NETS_DA_VERIFICARE"
    assert con.patch["storico_netto"][-1]["prima"] == 900
    assert con.patch["storico_netto"][-1]["dopo"] is None


def test_documento_tfr_separato_non_contamina_busta_stesso_mese():
    from app.services.posizione_dipendente import componi_movimenti
    docs = [{"id": "b", "dipendente_id": "d", "anno": 2025, "mese": 10,
             "tipo_cedolino": "ordinario", "netto": 900},
            {"id": "t", "dipendente_id": "d", "anno": 2025, "mese": 10,
             "tipo_cedolino": "tfr", "netto": 1000}]
    risultato = componi_movimenti(paghe=[], cedolini=docs, esiti=[], acconti=[],
        pagamenti_senza_competenza=[], conciliazioni=[], rapporto={})
    buste = [m for m in risultato["registro"] if m["tipo"] == "busta"]
    assert len(buste) == 1
    assert buste[0]["dare"] == Decimal("900.00")
    assert buste[0]["link"]["cedolino_id"] == "b"


@pytest.mark.parametrize("anagrafica_esistente", [True, False])
def test_writer_tfr_archivia_senza_stipendio_evento_o_netto_anagrafica(monkeypatch, anagrafica_esistente):
    from app.services.salari_unificati_v2 import processa_cedolino_v2
    from app.services import hr_cedolini_deposito, event_bus, cedolini_manager
    db = ArchivioDocumenti("erp")
    depositati, eventi, riconciliazioni = [], [], []
    async def deposito(doc):
        depositati.append(dict(doc))
        return {"esito": "inserito"}
    async def evento(*args, **kwargs):
        eventi.append(args)
    async def riconcilia(*args, **kwargs):
        riconciliazioni.append(args)
        return False
    monkeypatch.setattr(hr_cedolini_deposito, "deposita_cedolino_in_hr", deposito)
    monkeypatch.setattr(event_bus, "propagate_event", evento)
    monkeypatch.setattr(cedolini_manager, "riconcilia_stipendio_automatico", riconcilia)
    async def scenario():
        if anagrafica_esistente:
            await db.dipendenti.insert_one({"id": "d", "codice_fiscale": "CF", "ultimo_netto": 900,
                                            "ultimo_cedolino": "09/2026"})
        risultato = await processa_cedolino_v2(db, {"codice_fiscale": "CF", "nome_dipendente": "Mario Rossi",
            "anno": 2026, "mese": 10, "tipo_cedolino": "tfr", "netto": 1000, "lordo": 1200,
            "stato_netto": NETTO_VERIFICATO_DA_CEDOLINO}, filename="tfr.pdf")
        assert risultato["success"] is True
        doc = await db.cedolini.find_one({"id": risultato["cedolino_id"]})
        assert doc["tipo_cedolino"] == "tfr" and doc["netto"] == 1000
        assert len(depositati) == 1 and depositati[0]["netto"] == 1000
        assert await db.prima_nota_salari.count_documents({}) == 0
        assert eventi == [] and riconciliazioni == []
        dip = await db.dipendenti.find_one({"codice_fiscale": "CF"})
        assert dip["id"] == doc["dipendente_id"]
        if anagrafica_esistente:
            assert dip["ultimo_netto"] == 900 and dip["ultimo_cedolino"] == "09/2026"
        else:
            assert "ultimo_netto" not in dip and "ultimo_cedolino" not in dip
    asyncio.run(scenario())
