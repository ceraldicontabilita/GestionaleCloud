"""Riepilogo paghe (Paghe Infinity) ed Elenco netti: cosa il consulente dice di versare e di bonificare."""
import asyncio
from datetime import date

from mongomock_motor import AsyncMongoMockClient

from app.services import elenchi_netti as en
from app.services import piano_tributi as piano
from app.services import prospetti_contabili as pc

RIEPILOGO = """[PAGINA 1]
Prospetto riepilogativo elaborazione paghe
Dal Giugno  2026 Agg.1 - Al Giugno  2026 Norm.
000026 AZIENDA DI PROVA S.R.L.
Paghe Infinity: 26.07.01
RIEPILOGO IMPORTI A DEBITO/CREDITO
Totale netti 1.000,00
9001 I.N.P.S. Id. 1 500,00 Periodo versamento 06/2026
9005 I.N.P.S. - Gestione separata Id. 2 100,00 Periodo versamento 06/2026
IRPEF Ant. 50,00 Periodo versamento 06/2026
05 ADD.REGIONALE Ant.CAMPANIA 20,00
Totale addizionale regionale Anticipata 20,00 Periodo versamento 06/2026
[PAGINA 2]
RIEPILOGO IMPORTI A DEBITO/CREDITO
TOTALE COMPLESSIVO 1.670,00
"""

ELENCO = """[PAGINA 1]
Elenco netti
Periodo di elaborazione:   Giugno 2026 Tipo cedolino Norm.
Azienda:   000026 AZIENDA DI PROVA S.R.L.
Progressivo ripartizione n.1:   Cod tipo pagamento: // ; Cod gruppo addebito: // ;
0300001    ROSSI MARIO     600,00
0300002    BIANCHI ANNA    300,00
Totale di ripartizioneTotale di ripartizione     900,00     Nr dipendenti   2
[PAGINA 2]
Elenco netti
Periodo di elaborazione:   Giugno 2026 Tipo cedolino Norm.
Azienda:   000026 AZIENDA DI PROVA S.R.L.
Progressivo ripartizione n.1:   Cod tipo pagamento: ZA - Accredito su c/c bancario ; Cod gruppo addebito: 000001 - BANCA ;
0300003    VERDI LUCA     100,00  IT60X0542811101000000123456  05034 03406 BANCO BPM
Totale di ripartizione     100,00     Nr dipendenti   1
Totale aziendale     1.000,00     Nr dipendenti   3
"""


def run(c):
    return asyncio.run(c)


def test_il_riepilogo_si_riconosce_e_quadra_al_centesimo():
    assert pc.riconosci(RIEPILOGO) and pc.e_riepilogo_paghe(RIEPILOGO)
    r = pc.leggi_prospetto(RIEPILOGO)
    assert r["mancanti"] == [] and (r["mese"], r["anno"], r["codice_ditta"]) == (6, 2026, "000026")
    assert {(a["codice"], a["importo_cents"]) for a in r["attesi"]} == {("DM10", 50000), ("CXX", 10000)}
    # IRPEF e addizionali si dividono nell'F24 su piu' codici e periodi: si vedono, non si usano.
    assert {v["etichetta"] for v in r["non_mappate"]} == {"IRPEF Ant", "Totale addizionale regionale Anticipata"}
    assert r["netti_cents"] == 100000 and r["totale_complessivo_cents"] == 167000


def test_un_riepilogo_che_non_quadra_non_si_deposita():
    r = pc.leggi_prospetto(RIEPILOGO.replace("TOTALE COMPLESSIVO 1.670,00", "TOTALE COMPLESSIVO 1.671,00"))
    assert "quadratura" in r["mancanti"]
    assert run(pc.deposita_prospetto(AsyncMongoMockClient()["x"], r, documento_id=None, filename="r.pdf", sha256="a")) is None


def test_il_piano_mostra_l_atteso_dalle_buste_e_la_differenza_con_l_f24():
    db = AsyncMongoMockClient()["piano"]
    r = pc.leggi_prospetto(RIEPILOGO)
    run(pc.deposita_prospetto(db, r, documento_id=None, filename="riepilogo.pdf", sha256="abc"))
    # secondo giro: stesso file, niente doppioni
    assert run(pc.deposita_prospetto(db, r, documento_id=None, filename="riepilogo.pdf", sha256="abc"))
    assert run(db["prospetti_contabili"].count_documents({})) == 1
    f24 = {"id": "f1", "status": "da_pagare",
           "dati_generali": {"data_versamento": "2026-07-16", "saldo_delega_cents": 10100},
           "sezione_inps": [{"causale": "CXX", "anno": "2026", "mese": "06", "importo_debito_cents": 10100,
                             "importo_credito_cents": 0}]}
    run(db["f24_unificato"].insert_one(f24))
    g = run(piano.griglia(db, 2026, oggi=date(2026, 9, 26)))
    cxx = next(c for r_ in g["voci"] if r_["voce"]["id"] == "inps_cxx" for c in r_["caselle"] if c["periodo"] == "06")
    assert cxx["atteso_da_buste"]["importo_cents"] == 10000 and cxx["atteso_da_buste"]["differenza_cents"] == 100
    dm10 = next(c for r_ in g["voci"] if r_["voce"]["id"] == "inps_dm10" for c in r_["caselle"] if c["periodo"] == "06")
    assert dm10["atteso_da_buste"]["importo_cents"] == 50000 and dm10["atteso_da_buste"]["differenza_cents"] is None
    # un mese senza prospetto non porta nessun atteso
    assert "atteso_da_buste" not in next(
        c for r_ in g["voci"] if r_["voce"]["id"] == "inps_cxx" for c in r_["caselle"] if c["periodo"] == "05")


def test_elenco_netti_riconosciuto_dal_contenuto_e_quadrato():
    assert en.riconosci(ELENCO)
    e = en.leggi_elenco(ELENCO)
    assert e["mancanti"] == [] and e["numero_righe"] == 3 and e["totale_cents"] == 100000
    assert [len(r["righe"]) for r in e["ripartizioni"]] == [2, 1]
    assert e["ripartizioni"][1]["righe"][0]["iban"].startswith("IT60")
    storto = en.leggi_elenco(ELENCO.replace("Totale aziendale     1.000,00", "Totale aziendale     1.100,00"))
    assert "totale_aziendale" in storto["mancanti"]
    db = AsyncMongoMockClient()["e"]
    assert run(en.deposita_elenco(db, storto, documento_id=None, filename="e.pdf", sha256="z")) is None
    primo = run(en.deposita_elenco(db, e, documento_id=None, filename="e.pdf", sha256="a"))
    assert run(en.deposita_elenco(db, e, documento_id=None, filename="e.pdf", sha256="a")) == primo
    assert run(db["elenchi_netti"].count_documents({})) == 1


def test_rc01_e_il_ravvedimento_del_dm10_non_un_alias():
    from app.services.prospetti_contabili import valuta_modello
    atteso = [{"codice": "DM10", "mese": 5, "anno": 2026, "lato": "debito", "importo_cents": 100000}]
    riga = lambda cod, imp: {"codice": cod, "mese": 5, "anno": 2026, "importo_debito_cents": imp, "importo_credito_cents": 0}
    # Pagato in ritardo: RC01 con sanzioni e interessi -> ravveduto, la differenza e' dichiarata.
    v = valuta_modello(atteso, [riga("RC01", 101500)])
    d = v["dettaglio"][0]
    assert d["esito"] == "RAVVEDUTO" and d["codice_trovato"] == "RC01" and d["sanzioni_interessi_cents"] == 1500
    assert v["ok"] == 1
    # Meno dell'atteso non e' un ravvedimento: differenza.
    assert valuta_modello(atteso, [riga("RC01", 90000)])["dettaglio"][0]["esito"] == "DIFFERENZA"
    # Pagamento regolare: DM10 al centesimo.
    assert valuta_modello(atteso, [riga("DM10", 100000)])["dettaglio"][0]["esito"] == "OK"
