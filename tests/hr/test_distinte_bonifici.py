"""Distinte «beneficiari vari»: i dati messi in fila per l'associazione a mano."""
import asyncio

from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.hr.routers.dipendenti_cloud import indici_da_dipendenti
from app.services.distinte_bonifici import elenco_distinte

INDICI = indici_da_dipendenti([
    {"id": "d1", "nome": "Uno", "cognome": "Bianchi", "nome_completo": "Bianchi Uno"},
    {"id": "d2", "nome": "Due", "cognome": "Verdi", "nome_completo": "Verdi Due"},
])


def _run(coro):
    return asyncio.run(coro)


def _scenario():
    gest = ClientArchivioMemoria()["gest"]
    hr = ClientArchivioMemoria()["hr"]

    async def prepara():
        await gest.estratto_conto_movimenti.insert_many([
            {"id": "m1", "data": "2026-06-15", "importo": -1000.0,
             "descrizione": "VS.DISP. RIF. MB0B00000001/9043 FAVORE BENEFICIARI VARI DISTINTA - ADD.TOT",
             "livello_evidenza": "ufficiale", "ignorata": True,
             "source_filename_ufficiale": "Estratto conto corrente_30-06-2026.pdf"},
            {"id": "m2", "data": "2026-06-15", "importo": -0.5,
             "descrizione": "VS.DISP. RIF. MB0B00000001/9043 FAVORE BENEFICIARI VARI DISTINTA - ADD.SPE"},
            {"id": "m3", "data": "2026-07-10", "importo": -1234.0,
             "descrizione": "VS.DISP. RIF. MB0B00000002/9044 FAVORE BENEFICIARI VARI DISTINTA - ADD.TOT - Bianchi acc stipendio",
             "livello_evidenza": "provvisoria"},
            # gia' associata: nessuna voce in coda
            {"id": "m4", "data": "2026-07-11", "importo": -50.0,
             "descrizione": "VS.DISP. RIF. MB0B00000003/9045 FAVORE BENEFICIARI VARI DISTINTA - ADD.TOT"},
            # non e' una distinta
            {"id": "m5", "data": "2026-07-12", "importo": -70.0,
             "descrizione": "VS.DISP. RIF. MB0B00000004/9046 FAVORE ROSSI MARIO - ADD.TOT"},
        ])
        await gest.bonifici_transfers.insert_one(
            {"cro_trn": "MB0B00000001", "source_file": "ricevuta.pdf", "data": "2026-06-15",
             "importo": 1000.0, "causale": "AGGIUNTIVA"})
        await gest.cedolini.insert_many([
            {"dipendente_id": "d1", "nome_dipendente": "Dip Uno", "anno": 2026, "mese": 6, "netto": 1234.0},
            {"dipendente_id": "d2", "nome_dipendente": "Dip Due", "anno": 2026, "mese": 7, "netto": 900.0},
        ])
        await hr.bonifici_da_associare.insert_many([
            {"id": "q1", "stato": "da_associare", "rif_banca": "MB0B00000001", "importo": 1000.0,
             "data": "2026-06-15", "causale": "AGGIUNTIVA", "pdf_filename": "ricevuta.pdf"},
            {"id": "q2", "stato": "da_associare", "rif_banca": "MB0B00000002", "importo": 1234.0,
             "data": "2026-07-10", "causale": "VS.DISP."},
            {"id": "q3", "stato": "associato", "rif_banca": "MB0B00000003", "importo": 50.0,
             "data": "2026-07-11", "causale": "x"},
        ])

    _run(prepara())
    return gest, hr


def test_una_riga_per_distinta_ancora_da_associare_con_tutti_i_dati():
    gest, hr = _scenario()
    righe = _run(elenco_distinte(gest, hr, INDICI))
    assert [r["id"] for r in righe] == ["q2", "q1"]  # piu' recente per prima
    q1 = next(r for r in righe if r["id"] == "q1")
    d = q1["distinta"]
    assert q1["importo"] == 1000.0 and d["rif"] == "MB0B00000001"
    assert d["commissione"] == 0.5 and d["ufficiale"] is True and d["ignorata"] is True
    assert d["estratto"] == "Estratto conto corrente_30-06-2026.pdf"
    assert d["ricevuta"][0]["file"] == "ricevuta.pdf"
    assert d["suggerimento"] is None  # nessun netto uguale a 1000


def test_il_suggerimento_c_e_solo_con_un_unico_dipendente_e_non_si_scrive_niente():
    gest, hr = _scenario()
    righe = _run(elenco_distinte(gest, hr, INDICI))
    q2 = next(r for r in righe if r["id"] == "q2")
    sug = q2["distinta"]["suggerimento"]
    assert sug["dipendente_id"] == "d1" and (sug["anno"], sug["mese"]) == (2026, 6)
    assert q2["distinta"]["nota"] == "Bianchi acc stipendio"
    # la nota nomina UN solo dipendente: e' un suggerimento, non una scrittura
    assert q2["distinta"]["suggerimento_nota"]["dipendente_id"] == "d1"
    # due dipendenti con lo stesso netto: nessun suggerimento
    _run(gest.cedolini.insert_one(
        {"dipendente_id": "d3", "nome_dipendente": "Dip Tre", "anno": 2026, "mese": 7, "netto": 1234.0}))
    q2 = next(r for r in _run(elenco_distinte(gest, hr, INDICI)) if r["id"] == "q2")
    assert q2["distinta"]["suggerimento"] is None
    assert _run(hr.bonifici_da_associare.count_documents({"stato": "associato"})) == 1


def test_nota_con_due_cognomi_o_senza_nome_non_suggerisce():
    gest, hr = _scenario()

    async def cambia():
        await gest.estratto_conto_movimenti.update_one(
            {"id": "m3"}, {"$set": {"descrizione":
             "VS.DISP. RIF. MB0B00000002/9044 FAVORE BENEFICIARI VARI DISTINTA - ADD.TOT - Bianchi e Verdi stipendi"}})
    _run(cambia())
    q2 = next(r for r in _run(elenco_distinte(gest, hr, INDICI)) if r["id"] == "q2")
    assert q2["distinta"]["suggerimento_nota"] is None
    q1 = next(r for r in _run(elenco_distinte(gest, hr, INDICI)) if r["id"] == "q1")
    assert q1["distinta"]["suggerimento_nota"] is None  # nessuna nota
