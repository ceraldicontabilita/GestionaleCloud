"""
test_proponi_ingredienti.py
────────────────────────────
Collaudo del bottone «✨ Proponi» (richiesta Enzo 23/07/2026: "il bottone
proponi non funziona"): la base curata deve coprire i prodotti REALI di una
pasticceria/rosticceria napoletana anche quando l'AI non risponde. Test puri
su _kb_lookup (nessuna rete/DB): nomi presi dal catalogo vero dell'app.
"""
import pytest
from app.lotti.routers.food_cost import _kb_lookup, _radici_kb, _arricchisci_da_nome


# (nome come lo scrive Enzo, ingrediente che DEVE comparire nella proposta)
CASI_CATALOGO = [
    ("Babà Crema Ed Amarena", "Rum"),
    ("Babà Mignon", "Farina"),
    ("Babà al limoncello", "Rum"),
    ("Sfogliatella Riccia", "Ricotta"),
    ("Sfogliatelle frolle", "Ricotta"),
    ("Zeppola di San Giuseppe", "Crema pasticcera"),
    ("Zeppole fritte", "Crema pasticcera"),
    ("Coda di aragosta", "Strutto"),
    ("Code di aragosta al cioccolato", "Crema pasticcera"),
    ("Strudel di Mele", "Mele"),
    ("Torta di mele della casa", "Mele"),
    ("Torta Caprese", "Mandorle"),
    ("Cassata siciliana", "Ricotta"),
    ("Cannoli siciliani", "Ricotta"),
    ("Pastiera napoletana", "Grano cotto"),
    ("Tiramisù", "Mascarpone"),
    ("Graffe zuccherate", "Patate"),
    ("Struffoli", "Miele"),
    ("Roccocò", "Mandorle"),
    ("Mostaccioli", "Cacao amaro"),
    ("Migliaccio napoletano", "Semolino"),
    ("Chiacchiere di carnevale", "Farina"),
    ("Fiocchi di neve", "Ricotta"),
    ("Pasticciotto leccese", "Crema pasticcera"),
    ("Diplomatico", "Pasta sfoglia"),
    ("Millefoglie alla crema", "Pasta sfoglia"),
    ("Profiteroles", "Cioccolato fondente"),
    ("Bignè alla crema", "Crema pasticcera"),
    ("Crostata di confettura", "Confettura"),
    ("Cheesecake ai frutti", "Formaggio spalmabile"),
    ("Torta Sacher", "Confettura di albicocche"),
    ("Torta della nonna", "Pinoli"),
    ("Pan di Spagna", "Uova"),
    ("Crema pasticcera", "Latte"),
    ("Mousse al cioccolato", "Cioccolato fondente"),
    ("Plumcake allo yogurt", "Farina"),
    ("Muffin al cioccolato", "Gocce di cioccolato"),
    ("Ciambellone", "Olio di semi"),
    ("Cornetti integrali", "Burro"),
    ("Croissant", "Burro"),
    ("Veneziana alla crema", "Crema pasticcera"),
    ("Tronchetto di Natale", "Pan di Spagna"),
    # Rosticceria
    ("Arancini di riso", "Riso"),
    ("Arancino ai funghi", "Riso"),
    ("Crocchè di patate", "Patate"),
    ("Frittatine di pasta", "Besciamella"),
    ("Rustico napoletano", "Pasta sfoglia"),
    ("Pizzette rosse", "Pomodoro"),
    ("Panzerotti fritti", "Fiordilatte"),
    ("Casatiello napoletano", "Strutto"),
    ("Tortano", "Salame"),
    ("Danubio salato", "Prosciutto cotto"),
    ("Parigina", "Prosciutto cotto"),
    ("Panino napoletano", "Salame"),
    # Bar
    ("Caffè freddo", "Caffe espresso"),
    ("Crema di caffè", "Panna"),
    ("Granita di limone", "Limoni"),
    ("Cioccolata calda", "Cacao amaro"),
]


@pytest.mark.parametrize("nome,ingrediente_atteso", CASI_CATALOGO)
def test_catalogo_reale_trova_proposta(nome, ingrediente_atteso):
    """Ogni prodotto tipico del catalogo DEVE avere una proposta dalla KB."""
    r = _kb_lookup(nome)
    assert r, f"nessuna proposta per {nome!r}"
    nomi = [i["nome"] for i in r]
    assert any(ingrediente_atteso.lower() in x.lower() for x in nomi), \
        f"{nome!r}: atteso {ingrediente_atteso!r} tra {nomi}"


def test_formato_output():
    r = _kb_lookup("Sfogliatella")
    assert all(set(i) == {"nome", "quantita", "unita"} for i in r)
    assert all(i["unita"] in ("g", "ml", "pz") for i in r)


def test_singolare_plurale_stessa_ricetta():
    """'Zeppola' e 'Zeppole' devono dare la stessa proposta (radici)."""
    assert _kb_lookup("Zeppole") == _kb_lookup("Zeppola")
    assert _kb_lookup("Graffe") == _kb_lookup("Graffa")
    assert _kb_lookup("Arancini") == _kb_lookup("Arancino")


def test_specificita_vince():
    """'Torta di mele' NON deve pescare un'altra torta generica: la chiave
    con più parole significative combacianti vince."""
    r = _kb_lookup("Torta di mele")
    assert any("mele" in i["nome"].lower() for i in r)
    # e lo strudel resta strudel anche se contiene 'mele' nel nome
    r2 = _kb_lookup("Strudel di mele")
    assert any("uvetta" in i["nome"].lower() for i in r2)


def test_sconosciuto_ritorna_none():
    """Un nome che non c'entra nulla NON deve agganciare per sbaglio."""
    assert _kb_lookup("Insalata di polpo") is None
    assert _kb_lookup("Spaghetti alle vongole") is None


def test_radici_ignorano_stopword_e_accenti():
    assert _radici_kb("Babà al Rum") == _radici_kb("baba rum")
    assert "di" not in _radici_kb("torta di mele")


# ── Gusti letti dal NOME (Enzo 23/07/2026: "babà panna e pistacchio →
#    dovevi inserire la panna e il pistacchio") ──────────────────────────────
def _proposta_completa(nome):
    """Simula il percorso dell'endpoint senza AI: base curata + gusti dal nome."""
    return _arricchisci_da_nome(nome, _kb_lookup(nome) or [])


@pytest.mark.parametrize("nome,attesi", [
    ("Babà panna e pistacchio", ["Panna", "Pistacchio"]),   # il caso esatto di Enzo
    ("Babà al pistacchio", ["Pistacchio"]),
    ("Babà crema ed amarena", ["Crema pasticcera", "Amarene"]),
    ("Cornetto alla nutella", ["Crema di nocciole"]),
    ("Cornetto al pistacchio", ["Pistacchio"]),
    ("Muffin ai frutti di bosco", ["Frutti di bosco"]),
    ("Crostata di albicocche", ["Confettura"]),
    ("Arancino ai funghi", ["Funghi"]),
    ("Pizzetta con wurstel", ["Wurstel"]),
    ("Rustico salsiccia e friarielli", ["Salsiccia", "Friarielli"]),
    ("Brioche al cioccolato bianco", ["Cioccolato bianco"]),
])
def test_gusti_dal_nome(nome, attesi):
    nomi = [i["nome"] for i in _proposta_completa(nome)]
    for atteso in attesi:
        assert any(atteso.lower() in x.lower() for x in nomi), \
            f"{nome!r}: manca {atteso!r} in {nomi}"


def test_gusti_non_duplicano_la_base():
    """'Babà al rum' NON deve avere due volte il rum; la coda di aragosta
    alla panna NON deve avere due volte la panna."""
    nomi = [i["nome"].lower() for i in _proposta_completa("Babà al rum")]
    assert sum(1 for x in nomi if "rum" in x) == 1
    nomi2 = [i["nome"].lower() for i in _proposta_completa("Coda di aragosta alla panna")]
    assert sum(1 for x in nomi2 if "panna" in x) == 1


def test_gusti_su_lista_vuota_non_inventano():
    assert _arricchisci_da_nome("Babà al pistacchio", []) == []
