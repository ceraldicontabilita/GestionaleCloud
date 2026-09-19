"""
Test dei fix su quantità e unità di misura (audit AUDIT_QUANTITA_UNITA §3 e §4,
tranche 25/07/2026). Test PURI: nessun database, nessuna rete.

Cosa proteggono:
 - `cl` e `dl` non finiscono più nel ramo default (una bottiglia "75 CL"
   valeva 75 kg / un errore ×10 sul food cost);
 - le unità a confezione (cartone, cassa, bottiglia…) NON vengono convertite
   in kg inventando un peso: tornano 0 e chi chiama deve segnalarlo;
 - la regola del titolare "bevande e alcolici a bottiglia/cartone, MAI a kg"
   viene riconosciuta anche dal food cost delle ricette.
"""
import os

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "Gestionale_Test")

from app.lotti.routers.food_cost import (  # noqa: E402
    UNITA_A_CONFEZIONE,
    _e_bevanda_a_unita,
    converti_in_kg,
)


# ── Conversioni di volume ────────────────────────────────────────────────────
def test_cl_vale_un_centesimo_di_litro():
    # 75 cl = 0,75 l. Prima cadeva nel default (÷1000) → 0,075: errore ×10.
    assert converti_in_kg(75, "cl") == 0.75
    assert converti_in_kg(100, "cl") == 1.0


def test_dl_vale_un_decimo_di_litro():
    assert converti_in_kg(5, "dl") == 0.5


def test_conversioni_base_invariate():
    assert converti_in_kg(2, "kg") == 2
    assert converti_in_kg(1, "l") == 1
    assert converti_in_kg(500, "g") == 0.5
    assert converti_in_kg(250, "ml") == 0.25


def test_uova_usano_il_peso_reale():
    # regola storica di Enzo: uovo 60 g, tuorlo 19 g, albume 33 g
    assert converti_in_kg(10, "pz", "uova fresche") == 0.6
    assert round(converti_in_kg(10, "pz", "tuorlo d'uovo"), 3) == 0.19
    assert round(converti_in_kg(10, "pz", "albume"), 3) == 0.33


# ── Unità a confezione: mai conversioni inventate ────────────────────────────
def test_cartone_e_cassa_non_diventano_chili():
    for unita in ("ct", "cartone", "cassa", "bottiglia", "cf", "collo"):
        assert unita in UNITA_A_CONFEZIONE
        # 0 = "non convertibile", NON "1 cartone = 1 grammo" (vecchio default)
        assert converti_in_kg(3, unita) == 0, unita


def test_unita_sconosciuta_resta_al_vecchio_default_grammi():
    # comportamento invariato per le unità davvero di massa non elencate
    assert converti_in_kg(500, "grammi") == 0.5


# ── Regola bevande a unità ───────────────────────────────────────────────────
def test_bevande_riconosciute_dal_nome():
    for nome in ("Amaro del Capo", "Birra Moretti 66", "Acqua naturale 1,5 L",
                 "Prosecco DOC", "Rum bianco", "Vino rosso della casa"):
        assert _e_bevanda_a_unita(nome) is True, nome


def test_ingredienti_di_pasticceria_non_sono_bevande():
    for nome in ("Farina 00", "Zucchero semolato", "Burro di panna",
                 "Sciroppo di glucosio"):  # glucosio = zuccheri, non bibite
        assert _e_bevanda_a_unita(nome) is False, nome


def test_categoria_del_dizionario_ha_la_precedenza_sul_nome():
    # se il dizionario dice già la categoria, non si ri-deduce dal nome
    assert _e_bevanda_a_unita("prodotto senza nome parlante", {"categoria": "liquori"}) is True
    assert _e_bevanda_a_unita("Amaro del Capo", {"categoria": "ALTRO"}) is False


# ── Dosi da laboratorio: l'ingrediente base sale a 1 kg ──────────────────────
from app.lotti.routers.food_cost import normalizza_a_un_kg, _scegli_ingrediente_base  # noqa: E402


def test_farina_150g_diventa_un_chilo_e_il_resto_si_riscala():
    # esempio testuale del titolare: 150 g di farina → 1 kg
    ric = [
        {"nome": "Farina 00", "quantita": 150, "unita": "g"},
        {"nome": "Zucchero", "quantita": 30, "unita": "g"},
        {"nome": "Uova", "quantita": 2, "unita": "pz"},
    ]
    out = normalizza_a_un_kg(ric)
    assert out["base"] == "Farina 00"
    assert round(out["fattore"], 2) == 6.67
    per_nome = {i["nome"]: i["quantita"] for i in out["ingredienti"]}
    assert per_nome["Farina 00"] == 1000
    assert per_nome["Zucchero"] == 200
    assert per_nome["Uova"] == 13  # 2 × 6,67 arrotondato


def test_arancini_500g_di_riso_diventano_un_chilo():
    ric = [
        {"nome": "Riso Carnaroli", "quantita": 500, "unita": "g"},
        {"nome": "Ragù", "quantita": 250, "unita": "g"},
        {"nome": "Piselli", "quantita": 100, "unita": "g"},
    ]
    out = normalizza_a_un_kg(ric)
    assert out["base"] == "Riso Carnaroli" and out["fattore"] == 2.0
    per_nome = {i["nome"]: i["quantita"] for i in out["ingredienti"]}
    assert per_nome == {"Riso Carnaroli": 1000, "Ragù": 500, "Piselli": 200}


def test_il_riso_vince_sulla_farina_quando_ci_sono_entrambi():
    # negli arancini c'è anche farina per la panatura: la base resta il riso
    ric = [
        {"nome": "Farina", "quantita": 100, "unita": "g"},
        {"nome": "Riso", "quantita": 500, "unita": "g"},
    ]
    assert _scegli_ingrediente_base(ric)["nome"] == "Riso"


def test_besciamella_parte_dal_latte():
    ric = [
        {"nome": "Latte intero", "quantita": 500, "unita": "ml"},
        {"nome": "Burro", "quantita": 50, "unita": "g"},
        {"nome": "Farina", "quantita": 50, "unita": "g"},
    ]
    out = normalizza_a_un_kg(ric)
    assert out["base"] == "Latte intero" and out["fattore"] == 2.0
    per_nome = {i["nome"]: i["quantita"] for i in out["ingredienti"]}
    assert per_nome["Latte intero"] == 1000 and per_nome["Burro"] == 100


def test_dosi_gia_da_un_chilo_restano_intatte():
    ric = [{"nome": "Farina", "quantita": 1, "unita": "kg"},
           {"nome": "Sale", "quantita": 20, "unita": "g"}]
    out = normalizza_a_un_kg(ric)
    assert out["fattore"] == 1.0
    assert out["ingredienti"] == ric


def test_senza_ingredienti_pesabili_non_si_inventa_nulla():
    ric = [{"nome": "Cornetti", "quantita": 10, "unita": "pz"}]
    out = normalizza_a_un_kg(ric)
    assert out["base"] is None and out["fattore"] == 1.0
    assert out["ingredienti"] == ric
