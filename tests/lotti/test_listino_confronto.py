"""Listini dei fornitori nel confronto prezzi, e lettura AI delle descrizioni.

Le righe sono quelle vere del catalogo riservato Barone (28/09/2026) e delle
fatture 2026 di Fiorentino, Big Food, Di Vincenzo e Siro.
"""
import asyncio
import json
import os
from decimal import Decimal

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.lotti.servizi import confronto_fornitori as cf
from app.lotti.servizi import lettura_articoli_ai as lai
from app.lotti.servizi import listino_fornitore as lf


def run(coro):
    return asyncio.run(coro)


INTESTAZIONE = ["Codice", "Descrizione", "EAN", "IVA %", "Unità di misura", "Prezzo €", "Conf. ordine",
                "Categoria", "Sottocategoria", "Link scheda"]
RIGHE_BARONE = [
    ["285SAL01", "SALE FINO KG. 1 X12 ITALKALI", "8007620005523", 22, "12 PZ", 3.6, "12 PZ", "SCATOLAMI", "SPEZIE", ""],
    ["255POM17", "POMODORI PELATI KG.3 LA TORRENTE", "8000282000530", 4, "6 PZ", 17.52, "6 PZ", "SCATOLAMI", "POMODORI", ""],
    ["290TON21", "TONNO OLIO GIR.GR.80x6 MAREVIVO", "8000614004519", 10, "PZ", 3.06, "1 PZ", "SCATOLAMI", "CARNE E PESCE", ""],
    ["351EDA01", "EDAMER BLOCCHI BAYERNLAND", "27779290", 4, "KG", 4.59, "1 KG", "FORMAGGI", "", ""],
    ["400NUT01", "NUTELLA KG.3 FERRERO", "80176800", 10, "PZ", 19.9, "1 PZ", "DOLCIARI", "", ""],
    ["460COC01", "COCA COLA LATTINA CL.33 X24", "", 22, "24 PZ", 12.0, "24 PZ", "BEVANDE", "", ""],
]
FONTE_BARONE = {"fornitore_key": "barone", "nome": "Barone Achille & figli srl", "partita_iva": "01527580615",
                "tipo": "listino"}


def _fattura(fornitore, piva, data, righe):
    return {
        "supplier_name": fornitore, "supplier_vat": piva, "invoice_date": data,
        "linee": [{"descrizione": d, "prezzo_unitario": p, "unita_misura": u, "quantita": q} for d, p, u, q in righe],
    }


FATTURE = [
    _fattura("F.lli Fiorentino Srl", "01234567890", "2026-09-14", [
        ("POMODORI PELATI KG.3 TORRENTE\n\n", "19.500000", "CT", "5.000000"),
        ("SALE FINO ITALKALI DA KG.1X12\n\n", "0.360000", "KG", "24.000000"),
    ]),
    _fattura("G.I.A.L. GENERALE INGROSSO ALIMENTARE S.R.L.", "05555555555", "2026-08-31", [
        ("F.NUTELLA K.3", "22.00000", "PZ", "1.000"),
    ]),
    _fattura("DI VINCENZO GROUP SRL", "18377021003", "2026-09-16", [
        ("COCA COLA CL33X24 LATTINA\n0\n", "11.475400", "CF", "1.000000"),
    ]),
    _fattura("SIRO S.R.L. UNIPERSONALE", "07777777777", "2026-09-11", [
        ("COCA COLA VETRO VAP CL.33 CTX24", "15.983610", "C5", "3.000000"),
        ("COCA COLA CL.33 CTX24", "13.000000", "C5", "1.000000"),
    ]),
]


def _listino():
    esito = lf.leggi_righe([INTESTAZIONE] + RIGHE_BARONE)
    return [lf.documento_prodotto(r, fornitore_key="barone", fornitore_nome=FONTE_BARONE["nome"],
                                  data_listino="2026-09-28", file_sha256="x", adesso="2026-09-28T10:00:00+00:00")
            for r in esito.righe]


# ── lettura del file ────────────────────────────────────────────────────────


@pytest.mark.parametrize("testo, atteso", [
    ("12 PZ", (12, "PZ")), ("PZ", (1, "PZ")), ("KG", (1, "KG")), ("6 CF", (6, "CF")), ("", (1, "")),
])
def test_unita_di_vendita(testo, atteso):
    assert lf.leggi_unita(testo) == atteso


def test_colonne_per_intestazione_non_per_posizione():
    tabella = [
        ["Listino settembre"],
        ["Prezzo", "Descrizione articolo", "Cod. articolo", "UM"],
        ["1,25", "ACQUA LETE CL.50", "A1", "PZ"],
        ["", "RIGA SENZA PREZZO", "A2", "PZ"],
        ["2,00", "DOPPIONE", "A1", "PZ"],
    ]
    esito = lf.leggi_righe(tabella)
    assert [(r.codice, r.prezzo) for r in esito.righe] == [("A1", Decimal("1.25"))]
    assert sorted(s["motivo"] for s in esito.scartate) == ["codice ripetuto", "prezzo mancante o zero"]
    with pytest.raises(ValueError):
        lf.leggi_righe([["Nome", "Colore"], ["x", "y"]])


def test_file_barone_nel_repo_si_legge_tutto():
    path = os.path.join("app", "lotti", "data", "listino_barone_2026-09-28.json")
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    esito = lf.leggi_righe(payload["tabella"])
    assert len(esito.righe) == 4209 and len(esito.scartate) == 2
    # le righe «Offerta Volantino» del sito: unita' dalla confezione, EAN solo cifre
    birra = next(r for r in esito.righe if r.codice == "465BIR01")
    assert (birra.unita, birra.ean, birra.offerta_fino) == ("15 PZ", "8001435500013", "2023-06-14")
    assert all(r.sigla_unita.isalpha() for r in esito.righe)


def test_import_idempotente_e_articoli_usciti():
    db = AsyncMongoMockClient()["Lotti_Test_Listino"]
    esito = lf.leggi_righe([INTESTAZIONE] + RIGHE_BARONE)
    primo = run(lf.importa(db, esito, fornitore_nome="Barone Achille & figli srl", piva="IT01527580615",
                           data_listino="2026-09-28", file_sha256="a"))
    assert (primo["nuovi"], primo["aggiornati"], primo["fornitore_key"]) == (6, 0, "baroneachillefiglisrl")
    secondo = run(lf.importa(db, esito, fornitore_nome="Barone Achille & figli srl", data_listino="2026-09-28",
                             file_sha256="a"))
    assert (secondo["nuovi"], secondo["aggiornati"], secondo["invariati"]) == (0, 0, 6)

    righe = [list(r) for r in RIGHE_BARONE[1:]]
    righe[0][5] = 18.00                               # pelati rincarati
    terzo = run(lf.importa(db, lf.leggi_righe([INTESTAZIONE] + righe), fornitore_nome="Barone Achille & figli srl",
                           data_listino="2026-10-05", file_sha256="b"))
    assert (terzo["nuovi"], terzo["aggiornati"], terzo["usciti_dal_listino"]) == (0, 1, 1)
    sale = run(db.catalogo_forno_prodotti.find_one({"codice_articolo": "285SAL01"}))
    pelati = run(db.catalogo_forno_prodotti.find_one({"codice_articolo": "255POM17"}))
    assert sale["nel_listino"] is False and sale["uscito_dal_listino_il"] == "2026-10-05"
    assert (pelati["prezzo_listino"], pelati["prezzo_listino_precedente"]) == ("18.0", "17.52")
    fonte = run(db.fonti_catalogo_esterne.find_one({"tipo": "listino"}))
    assert (fonte["partita_iva"], fonte["prodotti_trovati"], fonte["listino_data"]) == ("01527580615", 5, "2026-10-05")
    assert run(db.catalogo_forno_prodotti.count_documents({})) == 6


# ── listino nel confronto ───────────────────────────────────────────────────


def test_prezzo_di_listino_al_pezzo():
    per = {a.codice_articolo: a for a in cf.acquisti_da_listini(_listino(), [FONTE_BARONE])}
    assert per["285SAL01"].prezzo_pezzo == Decimal("0.3000")     # 12 pezzi a 3,60
    assert per["255POM17"].prezzo_pezzo == Decimal("2.9200")     # 6 latte da 3 kg a 17,52
    assert per["290TON21"].prezzo_pezzo == Decimal("3.0600")     # la confezione da 6, come in fattura a «PZ»
    assert per["351EDA01"].prezzo_pezzo == Decimal("4.5900")     # al chilo
    assert per["460COC01"].prezzo_pezzo == Decimal("0.5000")
    assert all(a.fornitore_id == "piva:01527580615" and a.origine == "listino" for a in per.values())


def _gruppo_con(acquisti, testo):
    gruppi, _ = cf.raggruppa(acquisti)
    return next(cf.riepilogo_gruppo(g) for g in gruppi.values() if any(testo in a.articolo.descrizione for a in g))


def test_listino_e_fatture_nello_stesso_confronto():
    acquisti = cf.acquisti_da_fatture(FATTURE) + cf.acquisti_da_listini(_listino(), [FONTE_BARONE])
    sale = _gruppo_con(acquisti, "SALE FINO")
    assert sale["migliore"] == "Barone Achille & figli srl" and sale["con_listino"]
    assert [(r["origine"], r["prezzo_pezzo"]) for r in sale["fornitori"]] == [("listino", "0.3000"), ("fattura", "0.3600")]

    # cartone fatturato senza i pezzi scritti: il numero viene dal listino, e si dichiara
    pelati = _gruppo_con(acquisti, "POMODORI PELATI")
    fiorentino = next(r for r in pelati["fornitori"] if r["origine"] == "fattura")
    assert fiorentino["prezzo_pezzo"] == "3.2500" and "listino" in fiorentino["nota_pezzi"]
    assert pelati["confrontabile"] and pelati["migliore"] == "Barone Achille & figli srl"


def test_vetro_e_lattina_non_si_uniscono_neanche_passando_per_una_descrizione_senza_contenitore():
    acquisti = cf.acquisti_da_fatture(FATTURE) + cf.acquisti_da_listini(_listino(), [FONTE_BARONE])
    gruppi, _ = cf.raggruppa(acquisti)
    for g in gruppi.values():
        contenitori = {a.articolo.contenitore for a in g if a.articolo.contenitore}
        assert len(contenitori) <= 1


# ── lettura AI ──────────────────────────────────────────────────────────────


def test_la_lettura_non_inventa_numeri():
    l1 = lai.valida({"nome": "Nutella Ferrero 3 kg", "marca": "Ferrero", "prodotto": "Crema spalmabile nocciole",
                     "misura": 3000, "unita": "g", "pezzi": 1}, "F.NUTELLA K.3")
    assert (l1["misura"], l1["unita"], l1["pezzi"], l1["prodotto"]) == ("3000", "g", None, "crema spalmabile nocciole")
    l2 = lai.valida({"nome": "Nutella", "prodotto": "crema", "misura": 750, "unita": "g", "pezzi": 6}, "NUTELLA FERRERO")
    assert (l2["misura"], l2["pezzi"]) == (None, None)
    l3 = lai.valida({"prodotto": "coca cola", "misura": 330, "unita": "ml", "pezzi": 24}, "COCA COLA CL33X24")
    assert (l3["misura"], l3["pezzi"]) == ("330", 24)


def _letture():
    nutella = {"marca": "Ferrero", "prodotto": "crema spalmabile nocciole", "variante": "", "misura": "3000",
               "unita": "g", "pezzi": None, "servizio": False, "versione": lai.VERSIONE}
    return {
        cf.impronta_descrizione("F.NUTELLA K.3"): {**nutella, "nome": "Nutella Ferrero 3 kg"},
        cf.impronta_descrizione("NUTELLA KG.3 FERRERO"): {**nutella, "nome": "Nutella Ferrero 3 kg"},
    }


def test_lettura_ai_completa_il_formato_e_unisce_le_descrizioni():
    grezzi = cf.acquisti_da_fatture(FATTURE) + cf.acquisti_da_listini(_listino(), [FONTE_BARONE])
    senza = _gruppo_con(grezzi, "NUTELLA")
    assert senza["n_fornitori"] == 1

    acquisti = cf.applica_letture(grezzi, _letture())
    gial = next(a for a in acquisti if a.fornitore.startswith("G.I.A.L."))
    assert (gial.articolo.misura, gial.articolo.unita) == (Decimal("3000"), "g")
    nutella = _gruppo_con(acquisti, "NUTELLA")
    assert nutella["n_fornitori"] == 2 and nutella["abbinato_ai"] is False  # riepilogo senza flag esterno
    gruppi, _ = cf.raggruppa(acquisti)
    radice = next(k for k, g in gruppi.items() if any("NUTELLA" in a.articolo.descrizione for a in g))
    assert radice in gruppi.via_ai
    art = cf.riepilogo_gruppo(gruppi[radice], abbinato_ai=True)
    assert art["nome_standard"] == "Nutella Ferrero 3 kg" and art["migliore"] == "Barone Achille & figli srl"

    # una persona dice «diverso»: l'AI non li riunisce
    chiavi = cf._coppia(*[a.articolo.chiave for a in gruppi[radice]][:2])
    decisioni = cf.Decisioni.da_documenti([{"chiavi": list(chiavi), "esito": "diverso"}])
    gruppi2, _ = cf.raggruppa(acquisti, decisioni)
    assert not any(len({a.fornitore_id for a in g}) > 1 and any("NUTELLA" in a.articolo.descrizione for a in g)
                   for g in gruppi2.values())


class _ClientFinto:
    """Un ``LlmChat`` finto: legge le descrizioni numerate del prompt e risponde con l'array."""

    def __init__(self):
        self.chiamate = 0

    async def crea_messaggio(self, messages, **kw):
        self.chiamate += 1
        testo = messages[0]["content"]
        righe = [r.split(". ", 1)[1] for r in testo.splitlines()[1:]]
        risposta = [{"i": i + 1, "nome": r.title(), "marca": "", "prodotto": r.split()[0].lower(),
                     "variante": "", "misura": None, "unita": None, "pezzi": None, "servizio": False}
                    for i, r in enumerate(righe)]
        corpo = __import__("json").dumps(risposta)
        return {"content": [{"type": "text", "text": corpo}], "stop_reason": "end_turn", "testo": corpo,
                "fonti_web": [], "usage": {"input_tokens": 1, "output_tokens": 1}, "modello": "finto", "tentativi": 1}


def test_giro_di_lettura_idempotente(monkeypatch):
    db = AsyncMongoMockClient()["Lotti_Test_Lettura"]
    client = _ClientFinto()
    monkeypatch.setattr(lai, "_client", lambda *a, **k: client)   # il solo client, finto
    monkeypatch.setenv("ANTHROPIC_API_KEY", "prova")
    descrizioni = ["SALE FINO KG. 1 X12 ITALKALI", "SALE FINO KG. 1 X12 ITALKALI\n0\n", "POMODORI PELATI KG.3"]
    esito = run(lai.leggi_mancanti(db, descrizioni))
    assert (esito["letti"], esito["restano"]) == (2, 0) and client.chiamate == 1
    assert run(db.articoli_letti_ai.count_documents({})) == 2
    di_nuovo = run(lai.leggi_mancanti(db, descrizioni))
    assert di_nuovo["letti"] == 0 and client.chiamate == 1
    stato = run(db.sync_status.find_one({"_id": lai.STATO_ID}))
    assert stato["stato"] == "completato"


def test_senza_chiave_non_legge_e_lo_dice(monkeypatch):
    db = AsyncMongoMockClient()["Lotti_Test_Lettura2"]
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    esito = run(lai.leggi_mancanti(db, ["SALE FINO"]))
    assert esito["ok"] is False and esito["da_leggere"] == 1
    assert run(db.sync_status.find_one({"_id": lai.STATO_ID}))["stato"] == "senza_chiave"


# ── router: dal catalogo al carrello ────────────────────────────────────────


@pytest.fixture()
def router(monkeypatch):
    import app.lotti.routers.confronto_fornitori as r

    database = AsyncMongoMockClient()["Lotti_Test_Confronto_Listino"]
    monkeypatch.setattr(r, "db", database)

    async def fatture():
        return FATTURE

    monkeypatch.setattr(r, "_fatture", fatture)
    run(database.fonti_catalogo_esterne.insert_one(dict(FONTE_BARONE)))
    run(database.catalogo_forno_prodotti.insert_many([dict(p) for p in _listino()]))
    run(database.articoli_letti_ai.insert_many([{"id": k, **v} for k, v in _letture().items()]))
    cf.invalida_cache()
    yield r
    cf.invalida_cache()


def test_migliore_dal_catalogo_di_un_altro_fornitore(router):
    # si ordina il sale dal catalogo Fiorentino: costa meno da Barone
    esito = run(router.miglior_fornitore_per(descrizione="SALE FINO ITALKALI DA KG.1X12",
                                             fornitore="F.lli Fiorentino Srl", codice="", prodotto_master_id=""))
    consiglio = esito["consiglio"]
    assert consiglio["cambia"] and consiglio["migliore"]["fornitore"] == "Barone Achille & figli srl"
    assert consiglio["risparmio_pezzo"] == "0.0600"
    # dal catalogo Barone per codice: e' gia' il migliore
    esito = run(router.miglior_fornitore_per(descrizione="", fornitore="barone", codice="285SAL01", prodotto_master_id=""))
    assert esito["trovato"] and esito["consiglio"]["cambia"] is False
    # articolo che nessun altro vende: nessun consiglio inventato
    esito = run(router.miglior_fornitore_per(descrizione="", fornitore="barone", codice="351EDA01", prodotto_master_id=""))
    assert esito["trovato"] and esito["consiglio"]["cambia"] is False and esito["articolo"]["n_fornitori"] == 1
    assert run(router.miglior_fornitore_per(descrizione="ARTICOLO CHE NON ESISTE", fornitore="", codice="", prodotto_master_id=""))["trovato"] is False


def test_per_catalogo_a_colpo_d_occhio(router):
    out = run(router.confronto_per_catalogo(fornitore="barone"))["articoli"]
    assert out["285SAL01"]["questo_migliore"] is True
    assert out["400NUT01"]["abbinato_ai"] is True and out["400NUT01"]["n_fornitori"] == 2
    assert "351EDA01" not in out           # venduto solo da Barone
    elenco = run(router.elenco_articoli(q="nutella", solo_confronti=True, fornitore="", limit=50))
    assert elenco["articoli"][0]["nome_standard"] == "Nutella Ferrero 3 kg"
