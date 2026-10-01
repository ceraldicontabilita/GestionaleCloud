"""Collaudo funzionale: versamento e prelievo di contanti.

CLAUDE.md: uscita Cassa ed entrata Banca (o viceversa), stesso `operation_id`,
collegate da `trasferimento_collegato_id`, categoria `trasferimento_interno`.
E' **un'operazione della banca, non una riga d'archivio**: le copie (vecchio
archivio, CSV, Enable Banking) fanno una coppia sola, il numero vero e' il
massimo per fonte nello stesso giorno e importo. Rileggere non scrive niente.
Un trasferimento non e' ne' un ricavo ne' un costo: sposta soldi fra due conti.
"""
from app.database import Collections
from app.services.versamenti_contanti import riconosci_versamenti

from ._comune import D, attive, nuovo_db, righe, run, somma

DATA = "2026-09-10"
FONTI = ("Enable Banking API", "Elenco_entrate_uscite_2026.csv", "archivio_legacy.xlsx")


def _ec(id_, fonte, importo=1000.0, verso="entrata", data=DATA,
        causale="VERS. CONTANTI - VVVVV SPORTELLO"):
    return {"id": id_, "data": data, "importo": importo, "tipo": verso,
            "descrizione_originale": causale, "source_filename": fonte}


def _carica(db, movimenti):
    run(db[Collections.BANK_STATEMENTS].insert_many(movimenti))


def _coppie(db):
    return run(attive(db, "prima_nota_cassa")), run(attive(db, "prima_nota_banca"))


def test_un_versamento_scrive_una_coppia_collegata_e_completa():
    db = nuovo_db("s6_versamento")
    _carica(db, [_ec("EC1", FONTI[0])])

    esito = run(riconosci_versamenti(db, dry_run=False))

    cassa, banca = _coppie(db)
    assert len(cassa) == 1 and len(banca) == 1
    (c,), (b,) = cassa, banca
    # Il contante ESCE dalla cassa ed ENTRA in banca.
    assert (c["tipo"], b["tipo"]) == ("uscita", "entrata")
    assert D(c["importo"]) == D(b["importo"]) == D("1000.00")
    assert c["categoria"] == b["categoria"] == "trasferimento_interno"
    assert c["operation_id"] == b["operation_id"] and c["operation_id"]
    assert c["trasferimento_collegato_id"] == b["id"] and b["trasferimento_collegato_id"] == c["id"]
    assert esito["versamenti"] == 1 and esito["gambe_cassa_create"] == 1 and esito["gambe_banca_create"] == 1
    # Sposta soldi fra due conti: effetto netto zero sulla liquidita' totale.
    assert D(b["importo"]) - D(c["importo"]) == D("0.00")


def test_un_prelievo_e_la_coppia_speculare():
    db = nuovo_db("s6_prelievo")
    _carica(db, [_ec("EC1", FONTI[0], importo=500.0, verso="uscita",
                     causale="PRELIEVO CONTANTI SPORTELLO")])

    esito = run(riconosci_versamenti(db, dry_run=False))

    (c,), (b,) = _coppie(db)
    assert (c["tipo"], b["tipo"]) == ("entrata", "uscita")           # entra in cassa, esce dalla banca
    assert c["categoria"] == b["categoria"] == "trasferimento_interno"
    assert c["operation_id"] == b["operation_id"]
    assert c["trasferimento_collegato_id"] == b["id"] and b["trasferimento_collegato_id"] == c["id"]
    assert esito["prelievi"] == 1


def test_lo_stesso_versamento_da_tre_fonti_fa_una_coppia_sola():
    db = nuovo_db("s6_tre_fonti")
    _carica(db, [_ec(f"EC{i}", fonte) for i, fonte in enumerate(FONTI, start=1)])

    esito = run(riconosci_versamenti(db, dry_run=False))

    cassa, banca = _coppie(db)
    assert len(cassa) == 1 and len(banca) == 1
    assert esito["versamenti"] == 1 and esito["copie_estratto_conto"] == 2
    # Il contante uscito dalla cassa e' UNO.
    assert somma(r["importo"] for r in cassa) == D("1000.00")


def test_rileggere_lo_stesso_estratto_o_una_copia_non_scrive_niente():
    db = nuovo_db("s6_idempotente")
    _carica(db, [_ec("EC1", FONTI[0])])
    run(riconosci_versamenti(db, dry_run=False))
    prima = {c: sorted(r["id"] for r in run(righe(db, c))) for c in ("prima_nota_cassa", "prima_nota_banca")}

    _carica(db, [_ec("EC2", FONTI[1])])                      # arriva la copia dall'altro export
    secondo = run(riconosci_versamenti(db, dry_run=False))
    terzo = run(riconosci_versamenti(db, dry_run=False))

    for esito in (secondo, terzo):
        assert esito["gambe_cassa_create"] == 0 and esito["gambe_banca_create"] == 0
        assert esito["doppioni_cassa_tolti"] == 0 and esito["doppioni_banca_tolti"] == 0
    dopo = {c: sorted(r["id"] for r in run(righe(db, c))) for c in ("prima_nota_cassa", "prima_nota_banca")}
    assert dopo == prima


def test_due_versamenti_uguali_dello_stesso_giorno_sono_due_coppie():
    """Due versamenti da 1.000 lo stesso giorno compaiono due volte NELLO STESSO export."""
    db = nuovo_db("s6_due_veri")
    _carica(db, [_ec("EC1", FONTI[0]), _ec("EC2", FONTI[0]),      # due versamenti veri
                 _ec("EC3", FONTI[1]), _ec("EC4", FONTI[1])])     # e le loro copie nell'altro export

    esito = run(riconosci_versamenti(db, dry_run=False))

    cassa, banca = _coppie(db)
    assert len(cassa) == 2 and len(banca) == 2 and esito["versamenti"] == 2
    assert len({r["operation_id"] for r in cassa}) == 2
    assert {r["trasferimento_collegato_id"] for r in cassa} == {r["id"] for r in banca}


def test_la_gamba_di_cassa_scritta_a_mano_si_collega_non_si_duplica():
    """Il contante e' spesso gia' in Prima Nota Cassa il giorno in cui esce dal negozio."""
    db = nuovo_db("s6_a_mano")
    run(db["prima_nota_cassa"].insert_one({
        "id": "cassa-mano", "data": DATA, "tipo": "uscita", "importo": 1000.0,
        "categoria": "Versamento Banca", "descrizione": "Versamento in banca", "source": "manuale"}))
    _carica(db, [_ec("EC1", FONTI[0])])

    esito = run(riconosci_versamenti(db, dry_run=False))

    cassa, banca = _coppie(db)
    assert [r["id"] for r in cassa] == ["cassa-mano"]                  # nessuna seconda uscita
    assert esito["gambe_cassa_collegate"] == 1 and esito["gambe_cassa_create"] == 0
    assert cassa[0]["trasferimento_collegato_id"] == banca[0]["id"]
    assert cassa[0]["categoria"] == "trasferimento_interno"


def test_un_pagamento_fornitore_in_contanti_dello_stesso_importo_non_diventa_un_versamento():
    db = nuovo_db("s6_fornitore")
    run(db["prima_nota_cassa"].insert_one({
        "id": "pagamento-fornitore", "data": DATA, "tipo": "uscita", "importo": 1000.0,
        "categoria": "Fornitori", "descrizione": "Pagamento fattura 55 Rossi Srl", "source": "manuale"}))
    _carica(db, [_ec("EC1", FONTI[0])])

    run(riconosci_versamenti(db, dry_run=False))

    cassa, _banca = _coppie(db)
    assert len(cassa) == 2                                             # il pagamento resta com'e'
    pagamento = next(r for r in cassa if r["id"] == "pagamento-fornitore")
    assert pagamento["categoria"] == "Fornitori" and "trasferimento_collegato_id" not in pagamento


def test_uno_storno_o_un_segno_contrario_non_e_un_versamento():
    db = nuovo_db("s6_storno")
    _carica(db, [
        _ec("EC1", FONTI[0], causale="STORNO VERS. CONTANTI"),
        _ec("EC2", FONTI[0], importo=700.0, verso="uscita", causale="VERS. CONTANTI - VVVVV"),
    ])

    esito = run(riconosci_versamenti(db, dry_run=False))

    assert esito["versamenti"] == 0 and esito["prelievi"] == 0
    assert _coppie(db) == ([], [])


def test_l_anteprima_non_scrive():
    db = nuovo_db("s6_anteprima")
    _carica(db, [_ec("EC1", FONTI[0])])

    esito = run(riconosci_versamenti(db))                  # dry_run per difetto

    assert esito["dry_run"] is True and _coppie(db) == ([], [])


def test_incasso_in_contanti_poi_versamento_la_cassa_si_azzera_e_i_ricavi_non_cambiano(monkeypatch):
    """Dall'XML al versamento: +300 in cassa dai corrispettivi, -300 dal versamento,
    +300 in banca. Il trasferimento non e' un ricavo: il giornale resta a una scrittura."""
    from ._comune import Importatore, xml_chiusura

    db = nuovo_db("s6_catena")
    Importatore(db, monkeypatch).importa("2700.xml", xml_chiusura())          # 10/09: contanti 300
    _carica(db, [_ec("EC1", FONTI[0], importo=300.0, data="2026-09-11")])      # versati l'11/09

    run(riconosci_versamenti(db, dry_run=False))

    cassa, banca = _coppie(db)
    saldo_cassa = somma(r["importo"] for r in cassa if r["tipo"] == "entrata") \
        - somma(r["importo"] for r in cassa if r["tipo"] == "uscita")
    assert saldo_cassa == D("0.00")
    assert somma(r["importo"] for r in banca if r["tipo"] == "entrata") == D("300.00")
    assert len(run(attive(db, "movimenti_contabili"))) == 1                    # nessun ricavo in piu'
    assert len(run(attive(db, "corrispettivi"))) == 1
