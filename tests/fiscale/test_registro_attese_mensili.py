from app.services.registro_versamenti_f24 import costruisci


def _paga(mese, *, anno=2026, data="2026-04-16", origine="drive"):
    return {"chiave": f"q-{mese}", "data": data, "importo_cents": 10000, "origini": [origine],
            "_righe": [{"sezione": "sezione_erario", "codice": "1001", "anno": anno, "mese": mese,
                        "importo_debito_cents": 10000, "importo_credito_cents": 0}]}


def _1001(pagamenti=(), **kw):
    return next(c for c in costruisci(list(pagamenti), oggi="2026-05-20", **kw)["codici"]
                if c["codice"] == "1001")


def test_1001_atteso_anche_senza_documenti_o_con_soli_due_mesi_pagati():
    c = _1001(anno=2026)
    assert c["periodi_attesi"] == list(range(1, 13))
    assert c["mancanti"] == [1, 2, 3, 4]
    assert c["periodi_non_scaduti"] == list(range(5, 13))
    c = _1001([_paga(1), _paga(2)], anno=2026)
    assert c["mancanti"] == [3, 4]
    assert c["anno_riferimento"] == 2026


def test_filtrare_la_fonte_non_cancella_la_prova_del_pagamento():
    c = _1001([_paga(3, origine="drive")], anno=2026, origine="posta")
    assert 3 not in c["mancanti"]
    assert c["deleghe"] == 0


def test_dicembre_pagato_in_gennaio_usa_il_periodo_della_riga():
    c = _1001([_paga(12, anno=2025, data="2026-01-16")], anno=2025)
    assert c["periodi_pagati"] == [12]
    assert c["mancanti"] == list(range(1, 12))
