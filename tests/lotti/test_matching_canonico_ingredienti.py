"""
test_matching_canonico_ingredienti.py
──────────────────────────────────────
Regression test per il motore di matching nome-commerciale -> nome-canonico
(match_livello2, il livello deterministico keyword-based usato sia
dall'import fatture XML sia da POST /ricette/collega-ingredienti-canonico —
STESSO matcher, per non ripetere il bug "doppio sistema" già trovato e
corretto oggi in prodotti_master.py).

Le stringhe di fattura sono reali, verificate via GET /ingredienti/cerca il
01/07/2026 (AP Commerciale, F.lli Fiorentino, SAIMA). Gli "attesi" sono il
risultato del solo livello L2 (dizionario statico INGREDIENTI_CANONICI):
il sistema live puo' restituire un canonico piu' specifico (es. "Zucchero a
Velo" invece di "Zucchero") quando L1 (nome_mapping, appreso/confermato in
DB) precede L2 — qui testiamo solo il livello deterministico, senza DB.
"""
import pytest

from app.lotti.routers.ingredienti import match_livello2, _consolida_canonico


@pytest.mark.parametrize("nome_fattura,atteso", [
    ("MARG.GREEN VALLEY CROISSANT 12Kg", "Margarina"),
    ("MARGARINA WIENER BACK KG.2,5X4", "Margarina"),
    ("ZUCCHERO A VELO x 5kg", "Zucchero"),
    ("ZUCCHERO RAF.SEM.ERIDANIA KG.25", "Zucchero"),
    ("CAT.A UOVA FRESCHE L DA 180", "Uova"),
    ("FARINA 0/MAN. CAPUTO DA KG.25", "Farina"),
])
def test_match_livello2_su_descrizioni_fattura_reali(nome_fattura, atteso):
    assert match_livello2(nome_fattura) == atteso


def test_match_livello2_nessun_match_ritorna_none():
    # descrizione senza nessuna keyword del dizionario culinario
    assert match_livello2("SPID INFOCERT ID AZIENDALE - 1 ANNO") is None


def test_match_livello2_preferisce_keyword_piu_specifica():
    # "Farina Manitoba" (keyword "farina manitoba", 14 char) deve vincere su
    # "Farina" (keyword "farina", 6 char): il matcher ordina per specificita'.
    assert match_livello2("FARINA MANITOBA KG.25 MOLINO") == "Farina Manitoba"


def test_consolida_canonico_unifica_varianti_margarina():
    # Stesso ingrediente, varianti di etichetta diverse -> stesso canonico unico
    # (regressione del conflitto "Margarina Sfoglia" vs "Margarina" in STATO.md).
    assert _consolida_canonico("margarina") == "Margarina"
    assert _consolida_canonico("Margarina") == "Margarina"


def test_keyword_corte_solo_parola_intera():
    # Bug riprodotto live il 02/07/2026 durante la campagna ricerca web:
    # la keyword "te" per sottostringa era dentro "torte"/"paste"/"palette"
    # e "orata" dentro "decorate" — da qui i canonici assurdi storici
    # ("804 PALETTE" → "Tè", "vassoio stella trasp." → "Tè").
    assert match_livello2("804 PALETTE CM.9.5 RIUTILIZZABILI KG. 1") is None
    assert match_livello2("Paste lievitate per babà") is None
    assert match_livello2("Torte decorate") is None          # 'orata' in 'decorate'
    assert match_livello2("Cannoli medi cioccolattati pz 100") != "Cola"
    assert match_livello2("ACQUA LETE VAP - VETRO CL.33 CTX24") != "Tè"
    # ...ma le parole intere continuano a matchare
    assert match_livello2("tè verde in foglie") == "Tè"
    assert match_livello2("STAR TEA 25FF VERDE") == "Tè"
    assert match_livello2("OLIO EVO DE CECCO LT.1") == "Olio extravergine"


def test_confine_parola_tollera_cifre_attaccate():
    # Le fatture incollano i numeri alle parole ("24RIGATONI", "9SPAGHETTINI"):
    # la cifra vale da separatore, il match non si deve perdere.
    assert match_livello2("DE CECCO PAS.GR.500 24RIGATONI") == "Pasta"
    assert match_livello2("DIVELLA PASTA GR.500 9SPAGHETTINI") == "Pasta"


def test_ricerca_web_canonico_da_vocabolario_controllato():
    # Casi REALI dalla prima esecuzione live di /schede-tecniche/ricerca-web
    # (02/07/2026): il modello propone canonici liberi ("Burro biologico"),
    # ma il mapping salvato DEVE restare nel vocabolario controllato, altrimenti
    # L1 vincerebbe su L2 col nome libero e il FIFO ricette ("Burro") non
    # troverebbe piu' il lotto. Stessa composizione testo usata dall'endpoint:
    # "{nome_canonico llm} {prodotto_identificato}".
    assert match_livello2("Burro biologico Parmareggio Burro Bio 125 g") == "Burro"
    assert match_livello2(
        "Farina 0 Farina Tipo 0 di Grano Tenero - Mulino Caputo (sacchetto 25 kg)"
    ) == "Farina tipo 0"
