"""Ordini: miglior fornitore per articolo dalle righe delle fatture XML.

Le descrizioni sono quelle vere di Siro, Sud Ingrosso, Fiorentino e Top
Distribuzione lette dalle fatture 2026: lo stesso articolo scritto in modi
diversi, cartoni fatturati come «PZ», lotti che sembrano litri.
"""
import asyncio
from decimal import Decimal

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

from app.lotti.servizi import confronto_fornitori as cf


def run(coro):
    return asyncio.run(coro)


# ── lettura della descrizione ───────────────────────────────────────────────


@pytest.mark.parametrize("testo, misura, unita, pezzi", [
    ("ACQUA FERRARELLE CL.50 CTX24", Decimal(500), "ml", 24),
    ("ACQUA SORGESANA LT.1,5 CTX6", Decimal(1500), "ml", 6),
    ("ACQUA SORGESANA CL.150 CTX6", Decimal(1500), "ml", 6),
    ("SCHWEPPES CL18X24 LIMONE", Decimal(180), "ml", 24),
    ("RED BULL CL25X24PZ", Decimal(250), "ml", 24),
    ("SUCCO YOGA MAGIC ANANAS 200ML CTX24", Decimal(200), "ml", 24),
    ("YOGA SUCCO CL20X24BT ANANAS", Decimal(200), "ml", 24),
    ("FAGIOLI BORLOTTI da KG.3X6", Decimal(3000), "g", 6),
    ("LIEVITO X PANIFIC. G.500X5X2", Decimal(500), "g", 10),
    ("TASSONI CEDRATA-18CL", Decimal(180), "ml", None),
    ("OLIO EXTRAVERGINE OLIVA L.5", Decimal(5000), "ml", None),
])
def test_formato_e_confezione(testo, misura, unita, pezzi):
    art = cf.leggi(testo)
    assert (art.misura, art.unita, art.pezzi) == (misura, unita, pezzi)


def test_lotti_date_e_gradi_non_sono_misure():
    assert cf.leggi("Aglio L.372").misura is None
    assert cf.leggi("Ananas L. 055-000857-0003014").misura is None
    assert cf.leggi("RICOTTA FULVI INCARTATA LOTTO 111").chiave == cf.leggi("RICOTTA FULVI INCARTATA LOTTO 125").chiave
    assert cf.leggi("GIN PORTOFINO DRY CL.50 43Â°").chiave == cf.leggi("GIN PORTOFINO DRY CL.50").chiave
    assert cf.leggi("CREMA CUCINA e PIZZA UNÃ¬ ML500x20").descrizione.startswith("CREMA CUCINA E PIZZA UNI")


@pytest.mark.parametrize("a, b, esito", [
    # stesso articolo scritto in modo diverso da due fornitori
    ("SCHWEPPES LIMONE CL.18 CTX24", "SCHWEPPES CL18X24 LIMONE", "certo"),
    ("TONICA FEVER TREE INDIAN CL.20 CTX24", "FEVER-TREE CL20X24 INDIAN TONIC", "certo"),
    ("COCA COLA ZERO VETRO VAP CL.33 CTX24", "COCA COLA ZERO CL33X24 VETRO", "certo"),
    ("BIRRA CERES STRONG ALE CL.33 CTX24 - DANIMARCA", "BIRRA CERES CL33X24 STRONG ALE", "certo"),
    ("CRODINO CL.10 CTX48", "CRODINO CL.10X48", "certo"),
    ("ESTATHE LIMONE LATTINA CL.33 CTX24", "ESTATHE'CL33X24 LIMONE LATTINA", "certo"),
    ("TASSONI CEDRATA-18CL", "CEDRATA TASSONI CL.18 CTX25", "certo"),
    ("PANNA VEG GRAN CUCINA ML.500X20", "PANNA VEGETALE GRAN CUCINA ML.500X20", "certo"),
    # probabile: decide una persona
    ("APEROL BARBIERI CL.100", "APEROL CL100", "probabile"),
    ("APERITIVO L'APE CL.100 BAGNOLI", "L'APE'CL100 APERITIVO", "probabile"),
    ("SUCCO YOGA MAGIC ANANAS 200ML CTX24", "YOGA SUCCO CL20X24BT ANANAS", "probabile"),
    # mai lo stesso: variante, formato, confezione, contenitore
    ("COCA COLA VETRO VAP CL.33 CTX24", "COCA COLA ZERO CL33X24 VETRO", None),
    ("SCHWEPPES TONICA CL.18 CTX24", "SCHWEPPES CL18X24 TONICAZERO", None),
    ("AMARO MONTENEGRO CL.70", "AMARO MONTENEGRO CL100", None),
    ("ACQUA FERRARELLE CL.50 CTX24", "ACQUA FERRARELLE PREMIUM PET CL.50 CTX24", None),
    ("COCA COLA ZERO VETRO VAP CL.33 CTX24", "COCA COLA ZERO LATTINA CL.33 CTX24", None),
    ("MARG WIENER PLUNDERPLAT KG.2X5", "MARGARINA WIENER BACK KG.2,5X4", None),
    ("PASTA DE CECCO SPAGHETTI", "PASTA DE CECCO PENNE LISCE", None),
])
def test_stesso_articolo(a, b, esito):
    assert cf.confronta(cf.leggi(a), cf.leggi(b)) == esito


# ── prezzo per pezzo ────────────────────────────────────────────────────────


def _pezzo(descrizione, prezzo, unita, quantita):
    return cf.prezzo_per_pezzo(cf.leggi(descrizione), Decimal(prezzo), unita, Decimal(quantita))


def test_prezzo_per_pezzo_dalle_unita_di_fattura():
    # Siro: unita' C5 = cartone
    assert _pezzo("ACQUA FERRARELLE CL.50 CTX24", "4.056", "C5", "5") == (Decimal("0.1690"), True)
    # Sud Ingrosso scrive PZ ma fattura il cartone: quantita' minore della confezione
    assert _pezzo("RED BULL CL25X24PZ", "19.2623", "PZ", "2") == (Decimal("0.8026"), True)
    # Fiorentino: PZ con quantita' multipla della confezione = prezzo del pezzo
    assert _pezzo("PANNA VEG GRAN CUCINA ML.500X20", "1.25", "PZ", "20") == (Decimal("1.2500"), False)
    # a peso: prezzo al kg per il peso del sacco
    assert _pezzo("FARINA 00 CAPUTO RINFORZ.KG.25", "0.825", "KG", "125") == (Decimal("20.6250"), False)
    # bottiglia singola
    assert _pezzo("APEROL CL100", "9.6721", "BT", "3") == (Decimal("9.6721"), False)


# ── gruppi, migliore, decisioni ─────────────────────────────────────────────


def _fattura(fornitore, data, righe, tipo="TD01", fid=None):
    return {
        "id": fid or f"{fornitore}-{data}",
        "supplier_name": fornitore,
        "invoice_date": data,
        "invoice_number": "1",
        "tipo_documento": tipo,
        "linee": [
            {"descrizione": d, "prezzo_unitario": p, "unita_misura": u, "quantita": q, "aliquota_iva": "22.00"}
            for d, p, u, q in righe
        ],
    }


FATTURE = [
    _fattura("SIRO S.R.L. UNIPERSONALE", "2026-03-10", [
        ("CRODINO CL.10 CTX48", "24.12", "C5", "2"),
        ("APEROL BARBIERI CL.100", "9.426230", "B4", "6"),
        ("SCHWEPPES LIMONE CL.18 CTX24", "13.52459", "C5", "1"),
        ("SPESE DI TRASPORTO", "2.10", "", "1"),
    ]),
    _fattura("SIRO S.R.L. UNIPERSONALE", "2026-08-26", [
        ("CRODINO CL.10 CTX48", "25.00", "C5", "1"),       # ultimo prezzo Siro
    ]),
    _fattura("SUD INGROSSO DI VINCENZO SRL", "2026-05-27", [
        ("CRODINO CL.10X48", "21.7213", "CT", "1"),
        ("APEROL CL100", "9.6721", "BT", "3"),
        ("SCHWEPPES CL18X24 LIMONE", "13.1148", "PZ", "1"),   # PZ ma e' il cartone
        ("ACQUA PERRIER CL33X24 NATURALE VAP", "20.4918", "PZ", "2"),
    ]),
    _fattura("\"TOP DISTRBUZIONE SRL\"", "2026-06-01", [
        ("ACQUA PERRIER CL33X24 NATURALE VAP", "0.80", "PZ", "48"),   # prezzo al pezzo, 48 bottiglie
    ]),
    _fattura("SUD INGROSSO DI VINCENZO SRL", "2026-06-10", [
        ("CRODINO CL.10X48", "30.00", "CT", "1"),
    ], tipo="TD04"),                                             # nota di credito: fuori
]


def _articolo(articoli, parola):
    trovati = [a for a in articoli if parola in a["nome"]]
    assert len(trovati) == 1, [a["nome"] for a in articoli]
    return trovati[0]


def test_miglior_fornitore_sull_ultimo_prezzo_per_pezzo():
    gruppi, probabili = cf.raggruppa(cf.acquisti_da_fatture(FATTURE))
    articoli = [cf.riepilogo_gruppo(g) for g in gruppi.values()]
    assert not any("TRASPORTO" in a["nome"] for a in articoli)

    crodino = _articolo(articoli, "CRODINO")
    assert crodino["n_fornitori"] == 2 and crodino["formato"] == "10 cl × 48"
    assert crodino["migliore"] == "SUD INGROSSO DI VINCENZO SRL"
    siro = next(r for r in crodino["fornitori"] if r["fornitore"].startswith("SIRO"))
    assert siro["prezzo_fattura"] == "25.0000" and siro["data"] == "2026-08-26"   # l'ultimo, non il minimo
    assert siro["prezzo_min"] == "0.5025"
    assert crodino["risparmio_pezzo"] == "0.0683"
    # la nota di credito non entra
    assert all(r["prezzo_fattura"] != "30.0000" for r in crodino["fornitori"])

    schweppes = _articolo(articoli, "SCHWEPPES")
    assert schweppes["migliore"] == "SUD INGROSSO DI VINCENZO SRL"

    # Perrier: cartone a 20,49 contro 0,80 a bottiglia = 0,85 contro 0,80 per pezzo
    perrier = _articolo(articoli, "PERRIER")
    assert perrier["migliore"] == "TOP DISTRBUZIONE SRL" and perrier["confrontabile"]

    # Aperol: due articoli separati finche' nessuno conferma
    assert len([a for a in articoli if "APEROL" in a["nome"]]) == 2
    assert [(a.descrizione, b.descrizione) for a, b in probabili] == [("APEROL BARBIERI CL.100", "APEROL CL100")] \
        or [(b.descrizione, a.descrizione) for a, b in probabili] == [("APEROL BARBIERI CL.100", "APEROL CL100")]


def test_decisione_stesso_accorpa_e_diverso_non_ripropone():
    acquisti = cf.acquisti_da_fatture(FATTURE)
    a, b = cf.leggi("APEROL BARBIERI CL.100").chiave, cf.leggi("APEROL CL100").chiave

    stesso = cf.Decisioni.da_documenti([{"chiavi": [a, b], "esito": "stesso"}])
    gruppi, probabili = cf.raggruppa(acquisti, stesso)
    aperol = [cf.riepilogo_gruppo(g) for g in gruppi.values() if any("APEROL" in x.articolo.descrizione for x in g)]
    assert len(aperol) == 1 and aperol[0]["migliore"].startswith("SIRO")
    assert probabili == []

    diverso = cf.Decisioni.da_documenti([{"chiavi": [b, a], "esito": "diverso"}])
    gruppi, probabili = cf.raggruppa(acquisti, diverso)
    assert probabili == []
    assert len([g for g in gruppi.values() if any("APEROL" in x.articolo.descrizione for x in g)]) == 2


def test_prezzi_non_confrontabili_non_scelgono():
    fatture = [
        _fattura("A SRL", "2026-01-01", [("BIRRA PERONI CL.33 CTX24", "12.70", "PZ", "24")]),   # 12,70 a bottiglia?
        _fattura("B SRL", "2026-01-02", [("BIRRA PERONI CL.33 CTX24", "13.00", "CT", "1")]),
    ]
    gruppi, _ = cf.raggruppa(cf.acquisti_da_fatture(fatture))
    [art] = [cf.riepilogo_gruppo(g) for g in gruppi.values()]
    assert art["confrontabile"] is False and art["migliore"] is None
    assert "da verificare" in art["motivo"].lower()


# ── router ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def router(monkeypatch):
    import app.lotti.routers.confronto_fornitori as r

    database = AsyncMongoMockClient()["Lotti_Test_Confronto"]
    monkeypatch.setattr(r, "db", database)

    async def fatture():
        return FATTURE

    monkeypatch.setattr(r, "_fatture", fatture)
    cf.invalida_cache()
    yield r
    cf.invalida_cache()


def test_elenco_filtri(router):
    tutto = run(router.elenco_articoli(q="", solo_confronti=False, fornitore="", limit=200))
    assert tutto["totale_articoli"] == 5 and tutto["con_confronto"] == 3 and tutto["da_confermare"] == 1
    # prima gli articoli in cui scegliere conviene
    assert all(a["migliore"] for a in tutto["articoli"][:3])

    solo = run(router.elenco_articoli(q="crodino", solo_confronti=True, fornitore="", limit=200))
    assert [a["nome"] for a in solo["articoli"]] == ["CRODINO CL.10X48"]

    per_fornitore = run(router.elenco_articoli(q="", solo_confronti=False, fornitore="Top Distrbuzione srl", limit=200))
    assert [a["nome"].split()[1] for a in per_fornitore["articoli"]] == ["PERRIER"]


def test_decisione_registrata_con_chi_l_ha_presa(router, monkeypatch):
    import app.lotti.routers.confronto_fornitori as r

    monkeypatch.setattr(r, "request_actor", lambda _req: {"id": "hr-7", "nome": "Pocci Salvatore"})
    proposte = run(router.coppie_da_confermare(limit=100))
    assert proposte["totale"] == 1
    chiavi = proposte["proposte"][0]["chiavi"]

    esito = run(router.registra_decisione(router.Decisione(chiavi=chiavi, esito="stesso"), request=object()))
    assert esito["decisione"]["deciso_da"]["nome"] == "Pocci Salvatore"
    dopo = run(router.elenco_articoli(q="aperol", solo_confronti=False, fornitore="", limit=200))
    assert len(dopo["articoli"]) == 1 and dopo["articoli"][0]["n_fornitori"] == 2
    assert run(router.coppie_da_confermare(limit=100))["totale"] == 0


def test_decisione_rifiuta_formati_diversi(router):
    crodino = cf.leggi("CRODINO CL.10X48").chiave
    perrier = cf.leggi("ACQUA PERRIER CL33X24 NATURALE VAP").chiave
    with pytest.raises(HTTPException) as exc:
        run(router.registra_decisione(router.Decisione(chiavi=[crodino, perrier], esito="stesso"), request=None))
    assert exc.value.status_code == 409
    with pytest.raises(HTTPException) as exc:
        run(router.registra_decisione(router.Decisione(chiavi=["x|-|x?", perrier], esito="stesso"), request=None))
    assert exc.value.status_code == 404


def test_fornitore_e_la_sua_partita_iva():
    """Due nomi con la stessa P.IVA sono un fornitore; due P.IVA sono due fornitori."""
    fatture = [
        dict(_fattura("SUD INGROSSO DI VINCENZO SRL", "2026-05-01", [("CRODINO CL.10X48", "21.72", "CT", "1")]),
             supplier_vat="08719711213"),
        dict(_fattura("Sud Ingrosso di Vincenzo S.r.l.", "2026-05-20", [("CRODINO CL.10X48", "22.00", "CT", "1")]),
             supplier_vat="IT08719711213"),
        dict(_fattura("DI VINCENZO GROUP SRL", "2026-07-01", [("CRODINO CL.10X48", "22.13", "CT", "1")]),
             supplier_vat="18377021003"),
    ]
    gruppi, _ = cf.raggruppa(cf.acquisti_da_fatture(fatture))
    [art] = [cf.riepilogo_gruppo(g) for g in gruppi.values()]
    assert art["n_fornitori"] == 2
    sud = next(r for r in art["fornitori"] if r["fornitore_id"] == "piva:08719711213")
    assert sud["acquisti"] == 2 and sud["prezzo_fattura"] == "22.0000"


def test_pari_merito_vince_la_fattura_piu_recente():
    fatture = [
        dict(_fattura("SUD INGROSSO DI VINCENZO SRL", "2026-05-05", [("ABACA SCIROPPO CL75 ELDER FLOWERS", "6.5164", "BT", "1")]),
             supplier_vat="08719711213"),
        dict(_fattura("DI VINCENZO GROUP SRL", "2026-07-28", [("ABACA SCIROPPO CL75 ELDER FLOWERS", "6.5164", "BT", "2")]),
             supplier_vat="18377021003"),
        dict(_fattura("A PRIMA SRL", "2026-01-01", [("ABACA SCIROPPO CL75 ELDER FLOWERS", "6.5164", "BT", "1")]),
             supplier_vat="00000000001"),
    ]
    gruppi, _ = cf.raggruppa(cf.acquisti_da_fatture(fatture))
    [art] = [cf.riepilogo_gruppo(g) for g in gruppi.values()]
    assert art["migliore"] == "DI VINCENZO GROUP SRL"
    assert art["pari_merito"] is True and art["risparmio_pezzo"] == "0.0000"
