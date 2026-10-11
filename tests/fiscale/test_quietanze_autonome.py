"""Quietanza autonoma: competenza, ente, scadenze e avvisi senza modello/banca."""
import asyncio
from copy import deepcopy
from datetime import date

from mongomock_motor import AsyncMongoMockClient

from app.services import f24_controllo_incrociato as reg
from app.services import piano_tributi as piano
from app.services import quietanze_import as qi
from app.services.scadenzario_tributi import righe_modello_con_scadenza


def run(coro):
    return asyncio.run(coro)


def db():
    return AsyncMongoMockClient()["quietanze_autonome"]


def quietanza(qid="q", **sezioni):
    return {"id": qid, "protocollo_telematico": "PROTO-" + qid,
            "data_pagamento": "2026-10-01", "saldo": 100.0,
            "stato_associazione": "f24_mancante", "calcolo_fiscale_sospeso": True,
            **sezioni}


def riga(codice, anno=2026, mese=5, importo=10000, **kw):
    return {"codice_tributo": codice, "anno": str(anno),
            "mese": f"{mese:02d}" if mese else "", "importo_debito_cents": importo, **kw}


def casella(g, vid, periodo):
    voce = next(v for v in g["voci"] if v["voce"]["id"] == vid)
    return next(c for c in voce["caselle"] if c["periodo"] == periodo)


def test_tutte_le_sezioni_dalla_sola_quietanza_e_competenza_anche_in_ritardo():
    archivio = db()
    q = quietanza(sezione_erario=[riga("1001")],
        sezione_inps=[{"causale": "DM10", "periodo_da": "05/2026", "periodo_a": "05/2026",
                       "codice_sede": "5100", "matricola": "123", "importo_debito_cents": 20000}],
        sezione_regioni=[riga("3802", anno=2025, codice_regione="15")],
        sezione_tributi_locali=[riga("3848", anno=2025, codice_comune="F839"),
                              riga("3847", codice_comune="F839")])
    run(archivio.quietanze_f24.insert_one(q))
    g = run(piano.griglia(archivio, 2026, oggi=date(2026, 10, 11)))
    for vid in ("ritenute_1001", "inps_dm10", "add_regionale_3802",
                "add_comunale_saldo_3848", "add_comunale_acconto_3847"):
        maggio = casella(g, vid, "05")
        assert maggio["stato"] == piano.PAGATO_QUIETANZA
        assert maggio["residuo_cents"] == 0
        assert maggio["quietanze_pagamento"][0]["pdf_url"] == "/api/originale/quietanza/q"
        assert casella(g, vid, "06")["stato"] == piano.MANCA_F24
    assert run(archivio.f24_unificato.count_documents({})) == 0


def test_imu_acconto_tardivo_non_chiude_saldo():
    archivio = db()
    q = quietanza(sezione_tributi_locali=[riga("3918", mese=None, acconto=True, saldo=False,
                                               codice_comune="F839")])
    run(archivio.quietanze_f24.insert_one(q))
    g = run(piano.griglia(archivio, 2026, oggi=date(2026, 12, 20)))
    acconto = casella(g, "imu_acconto", "06")
    assert acconto["stato"] == piano.PAGATO_QUIETANZA
    assert acconto["scadenza"] == "2026-06-16" and acconto["giorni_ritardo"] == 107
    assert casella(g, "imu_saldo", "12")["stato"] == piano.MANCA_F24
    assert run(qi._marca_scadenze_calendario(archivio, q, q["data_pagamento"], "q")) == ["imu_acconto_2026"]
    assert righe_modello_con_scadenza(q)[0]["scadenza"] == date(2026, 6, 16)


def test_enti_diversi_non_si_compensano_tra_loro():
    archivio = db()
    righe = [riga("3847", codice_comune="F839"), riga("3847", codice_comune="B990")]
    run(archivio.f24_unificato.insert_one({"id": "modello", "sezione_tributi_locali": righe}))
    run(archivio.quietanze_f24.insert_one(quietanza(sezione_tributi_locali=[
        riga("3847", codice_comune="F839", importo=20000)])))
    maggio = casella(run(piano.griglia(archivio, 2026, oggi=date(2026, 10, 11))),
                     "add_comunale_acconto_3847", "05")
    assert maggio["stato"] == piano.SCADUTO_NON_PAGATO and maggio["residuo_cents"] == 10000


def test_addizionale_pagata_nel_2025_non_salda_il_periodo_futuro_2026():
    archivio = db()
    q = quietanza(sezione_regioni=[riga("3802", anno=2025, mese=10, codice_regione="05")])
    q["data_pagamento"] = "2025-11-17"
    run(archivio.quietanze_f24.insert_one(q))
    g = run(piano.griglia(archivio, 2026, oggi=date(2026, 12, 20)))
    assert casella(g, "add_regionale_3802", "10")["stato"] == piano.MANCA_F24
    assert run(qi._marca_scadenze_calendario(archivio, q, q["data_pagamento"], "q")) == ["ritenute_2025_10"]


def test_copia_quietanza_un_solo_pdf_e_documento_fiscale_senza_legacy():
    archivio = db()
    q = quietanza(sezione_erario=[riga("1001")], category="quietanza_f24")
    run(archivio.fiscal_documents.insert_one(q))
    run(archivio.quietanze_f24.insert_one({**q, "id": "copia"}))
    maggio = casella(run(piano.griglia(archivio, 2026, oggi=date(2026, 10, 11))), "ritenute_1001", "05")
    assert maggio["debito_cents"] == 10000
    assert len(maggio["quietanze_pagamento"]) == 1
    assert maggio["quietanze_pagamento"][0]["pdf_url"] == "/api/originale/documento_fiscale/q"
    verifica = run(reg.verifica_codice(archivio, "1001", anno="2026", mese="05"))
    assert verifica["pagato"] and len(verifica["quietanze"]) == 1


def test_riallineamento_idempotente_senza_cambiare_righe_importi_e_banca():
    archivio = db()
    q = quietanza(sezione_erario=[riga("1001")], pagamento_verificato_banca=False)
    run(archivio.quietanze_f24.insert_many([q, {**q, "id": "err", "validazione": {"saldo_quadrato": False}},
                                         {**q, "id": "del", "entity_status": "deleted"}]))
    run(archivio[qi.COLL_F24_ALERTS].insert_one({"id": "a", "quietanza_id": "q",
        "tipo": "quietanza_senza_match", "status": "pending", "bloccante": True}))
    assert run(qi.allinea_quietanze_autonome(archivio)) == {"controllate": 3, "aggiornate": 1, "alert_chiusi": 1}
    dopo = run(archivio.quietanze_f24.find_one({"id": "q"}))
    assert dopo["stato_associazione"] == "autonoma" and dopo["calcolo_fiscale_sospeso"] is False
    for campo in ("sezione_erario", "saldo", "data_pagamento", "pagamento_verificato_banca"):
        assert dopo[campo] == q[campo]
    assert run(qi.allinea_quietanze_autonome(archivio))["aggiornate"] == 0


def test_codice_fuori_piano_con_piu_righe_nella_stessa_quietanza():
    archivio = db()
    run(archivio.quietanze_f24.insert_one(quietanza(sezione_tributi_locali=[
        riga("3944", codice_comune="F839", importo=5000),
        riga("3944", codice_comune="B990", importo=10000)])))
    g = run(piano.griglia(archivio, 2026, oggi=date(2026, 10, 11)))
    tassa = next(v for v in g["fuori_piano"] if v["codice"] == "3944")
    assert tassa["casella"]["debito_cents"] == 15000
    assert tassa["casella"]["stato"] == piano.PAGATO_QUIETANZA


def test_solleciti_controllano_tributi_pagati_senza_riutilizzarli_o_inventare_abbinamento():
    f = {"id": "f", "sezione_erario": [riga("1001")]}
    q = quietanza(sezione_erario=[riga("1001")])
    pagate = [reg._quietanza_legacy(q), reg._quietanza_legacy({**q, "id": "copia"})]
    assert reg.modelli_coperti_da_tributi_pagati([f, {**f, "id": "f-copia"}], pagate) == {"f", "f-copia"}
    altro_dovuto = {"id": "secondo", "sezione_erario": [riga("1001", importo=5000)]}
    assert reg.modelli_coperti_da_tributi_pagati([f, altro_dovuto], pagate) == set()
    altro_cf = {**f, "codice_fiscale": "altro contribuente"}
    assert reg.modelli_coperti_da_tributi_pagati([altro_cf], pagate) == set()
    sbagliato = deepcopy(q)
    sbagliato["sezione_erario"][0]["mese"] = "06"
    assert not reg.modelli_coperti_da_tributi_pagati([f], [reg._quietanza_legacy(sbagliato)])
