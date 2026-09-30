"""Lievito che cambia con ore e temperatura: ricette, produzione, calcolatore."""

import asyncio
import json

import pytest
from fastapi import HTTPException

from app.lotti.servizi import lievitazione as lv
from tests.lotti.test_e2e_flussi import dbmock  # noqa: F401  (fixture condivisa)


def run(coro):
    return asyncio.run(coro)


RIF = {"ore_ambiente": 8, "temperatura_c": 24}


# ── modello ─────────────────────────────────────────────────────────────────

def test_riconosce_solo_il_lievito_di_birra():
    si = ["Lievito di birra fresco", "LIEVITO x 2.5kg", "Lievito compresso", "Lievito", "lievito secco"]
    no = ["Lievito chimico", "Lievito per dolci", "lievito in polvere per dolci", "Lievito madre",
          "Miglioratore", "Farina"]
    assert all(lv.e_lievito_di_birra(n) for n in si)
    assert not any(lv.e_lievito_di_birra(n) for n in no)


def test_stesse_condizioni_stesso_lievito():
    assert lv.fattore_lievito(lv.condizioni(RIF), lv.condizioni(RIF)) == pytest.approx(1)


def test_piu_ore_e_piu_caldo_meno_lievito():
    rif = lv.condizioni(RIF)
    # Japi 2: il lievito va con 1/H^1,2 → doppio del tempo = 2^-1,2 ≈ 0,435
    assert lv.fattore_lievito(rif, lv.condizioni({"ore_ambiente": 16, "temperatura_c": 24})) == \
        pytest.approx(2 ** -1.2)
    # e con 1/T^2,5
    assert lv.fattore_lievito(rif, lv.condizioni({"ore_ambiente": 8, "temperatura_c": 28})) == \
        pytest.approx((24 / 28) ** 2.5)


def test_ore_in_frigo_contano_con_la_regola_di_hamelman():
    c = lv.condizioni({"ore_ambiente": 4, "temperatura_c": 22, "ore_frigo": 24, "temperatura_frigo_c": 4})
    assert lv.ore_equivalenti(c) == pytest.approx(4 + 24 * 3 ** ((4 - 22) / 9))  # 18 °C in meno = ÷9


def test_frigo_senza_temperatura_non_si_inventa():
    with pytest.raises(lv.DatoNonValido, match="temperatura del frigo"):
        lv.condizioni({"ore_ambiente": 2, "temperatura_c": 22, "ore_frigo": 24})


def test_formula_japi2_su_un_caso_noto():
    # 1 kg farina, 65%, 24 °C, 8 ore, 50 g/l sale → circa 1,28 g di fresco
    g = lv.lievito_japi2(1000, 65, 24, 8, 50, 0)
    atteso = 1000 * 2250 * 1.25 / ((-80 + 4.2 * 65 - 0.0305 * 65 ** 2) * 24 ** 2.5 * 8 ** 1.2)
    assert g == pytest.approx(atteso) and 1.2 < g < 1.4


def test_ricetta_senza_riferimento_non_inventa():
    esito = lv.adegua_lievito([{"nome": "Lievito", "quantita": 15, "unita_misura": "g"}], None,
                              {"ore_ambiente": 12, "temperatura_c": 20})
    assert esito["stato"] == "manca_riferimento"
    assert esito["righe"][0]["oggi"] is None and esito["righe"][0]["ricetta"] == 15


def test_ricetta_con_riferimento_ricalcola_solo_il_lievito():
    ingredienti = [{"nome": "Farina", "quantita": 1000, "unita_misura": "g"},
                   {"nome": "Lievito di birra", "quantita": 20, "unita_misura": "g"},
                   {"nome": "Lievito chimico", "quantita": 5, "unita_misura": "g"}]
    oggi = {"ore_ambiente": 16, "temperatura_c": 24}
    esito = lv.adegua_lievito(ingredienti, RIF, oggi)
    assert esito["stato"] == "ricalcolato"
    assert [r["nome"] for r in esito["righe"]] == ["Lievito di birra"]
    assert esito["righe"][0]["oggi"] == pytest.approx(20 * 2 ** -1.2, abs=0.05)
    nuovi = lv.applica_a_ingredienti(ingredienti, esito)
    assert nuovi[0] == ingredienti[0] and nuovi[2] == ingredienti[2]
    assert nuovi[1]["quantita"] == pytest.approx(8.7, abs=0.05) and nuovi[1]["lievito_ricalcolato"]


def test_calcolatore_impasto_torna_col_peso_totale():
    esito = lv.calcola_impasto({"panetti": 10, "peso_panetto_g": 250, "idratazione_pct": 65,
                                "sale_g_litro": 50, "ore_ambiente": 8, "temperatura_c": 24})
    somma = esito["farina_g"] + esito["acqua_g"] + esito["sale_g"]
    assert abs(somma - 2500) <= 2
    assert esito["lievito"]["grammi"] == pytest.approx(
        lv.lievito_japi2(esito["farina_g"], 65, 24, 8, 50), rel=0.02)


def test_calcolatore_con_biga_divide_farina_e_acqua():
    esito = lv.calcola_impasto({"panetti": 10, "peso_panetto_g": 250, "idratazione_pct": 70,
                                "sale_g_litro": 50, "ore_ambiente": 8, "temperatura_c": 22,
                                "prefermento": {"tipo": "biga", "quota_farina_pct": 50,
                                                "idratazione_pct": 44, "lievito_pct": 1}})
    p, c = esito["prefermento"], esito["chiusura"]
    assert abs(p["farina_g"] + c["farina_g"] - esito["farina_g"]) <= 1
    assert abs(p["acqua_g"] + c["acqua_g"] - esito["acqua_g"]) <= 1
    assert p["lievito_g"] == pytest.approx(p["farina_g"] / 100, abs=0.2)


def test_mix_farine_e_temperatura_acqua():
    m = lv.mix_farine(380, 220, 300, 1000)
    assert m == {"farina_a_g": 500, "farina_b_g": 500, "quota_a_pct": 50.0}
    with pytest.raises(lv.DatoNonValido):
        lv.mix_farine(380, 220, 400, 1000)
    assert lv.temperatura_acqua(24, 22, 20, 8)["acqua_c"] == 22.0
    assert lv.attrito_da_impasto(25, 22, 20, 25)["attrito_c"] == 8.0


# ── agganci agli endpoint ───────────────────────────────────────────────────

def _ricetta_pizza(dbmock, riferimento=RIF):
    run(dbmock.ricette.insert_one({
        "id": "R-pizza", "nome": "Pizza bianca", "porzioni": 10,
        "lievitazione_riferimento": riferimento,
        "ingredienti_dettaglio": [
            {"nome": "Farina 0", "quantita": 1000, "unita_misura": "g"},
            {"nome": "Acqua", "quantita": 650, "unita_misura": "ml"},
            {"nome": "Lievito di birra", "quantita": 20, "unita_misura": "g"},
            {"nome": "Sale", "quantita": 30, "unita_misura": "g"},
        ]}))


def test_dose_produzione_ricalcola_il_lievito(dbmock):
    import app.lotti.routers.food_cost as fc
    _ricetta_pizza(dbmock)
    out = run(fc.dose_produzione("R-pizza", fc.DoseProduzioneReq(
        moltiplicatore=2, normalizza_1kg=True, lievitazione={"ore_ambiente": 16, "temperatura_c": 24})))
    per_nome = {i["nome"]: i["quantita"] for i in out["ingredienti"]}
    assert per_nome["Sale"] == 60  # il resto scala normalmente
    assert per_nome["Lievito di birra"] == pytest.approx(40 * 2 ** -1.2, abs=0.1)
    assert out["lievito"]["stato"] == "ricalcolato"


def test_dose_produzione_senza_condizioni_resta_come_prima(dbmock):
    import app.lotti.routers.food_cost as fc
    _ricetta_pizza(dbmock)
    out = run(fc.dose_produzione("R-pizza", fc.DoseProduzioneReq(moltiplicatore=1, normalizza_1kg=True)))
    assert {i["nome"]: i["quantita"] for i in out["ingredienti"]}["Lievito di birra"] == 20
    assert out["lievito"]["stato"] == "manca_condizioni"


def test_lievito_per_pezzi_usa_il_moltiplicatore_della_produzione(dbmock):
    import app.lotti.routers.food_cost as fc
    _ricetta_pizza(dbmock)
    out = run(fc.lievito_per_produzione("R-pizza", {"pezzi": 25, "lievitazione": RIF}))
    assert out["moltiplicatore"] == 2.5
    assert out["righe"][0]["oggi"] == 50 and out["righe"][0]["ricetta"] == 50


def test_senza_riferimento_la_dose_in_ricetta_segue_i_pezzi(dbmock):
    import app.lotti.routers.food_cost as fc
    _ricetta_pizza(dbmock, riferimento=None)
    out = run(fc.lievito_per_produzione("R-pizza", {"pezzi": 20}))
    assert out["stato"] == "manca_riferimento" and out["righe"][0]["ricetta"] == 40


def test_dato_sbagliato_e_un_400_leggibile(dbmock):
    import app.lotti.routers.food_cost as fc
    _ricetta_pizza(dbmock)
    with pytest.raises(HTTPException) as err:
        run(fc.lievito_per_produzione("R-pizza", {"lievitazione": {"ore_ambiente": 8, "temperatura_c": 90}}))
    assert err.value.status_code == 400 and "temperatura ambiente" in err.value.detail


def test_patch_ricetta_salva_il_riferimento_validato(dbmock, monkeypatch):
    import app.lotti.routers.ricette as rr

    async def _ok(*a, **k):
        return None
    monkeypatch.setattr(rr, "verifica_reparto_ricetta", _ok)
    monkeypatch.setattr(rr, "_sincronizza_menu", _ok)
    _ricetta_pizza(dbmock, riferimento=None)
    run(rr.aggiorna_campo_ricetta("R-pizza", {"lievitazione_riferimento": {"ore_ambiente": "10",
                                                                          "temperatura_c": "22"}}, None))
    doc = run(dbmock.ricette.find_one({"id": "R-pizza"}))
    assert doc["lievitazione_riferimento"]["ore_ambiente"] == 10.0
    with pytest.raises(HTTPException):
        run(rr.aggiorna_campo_ricetta("R-pizza", {"lievitazione_riferimento": {"ore_ambiente": 10}}, None))


def _registra(lp, **extra):
    return run(lp.registra_produzione_e_crea_lotto(
        ricetta_id="R-pizza", pezzi=20, pezzi_base=20, costo_totale=None,
        data_produzione="2026-09-27", frigo_numero="Frigo 2", lotti_componenti_json=None,
        operatore_id="op1", operatore_nome="Mario", data_scadenza=None, memorizza_durata=False,
        operation_id=extra.pop("operation_id", "prod-lievito"), destinazione="frigo", **extra))


def test_registrazione_scarica_il_lievito_di_oggi_e_lo_scrive_sul_lotto(dbmock, monkeypatch):
    import app.lotti.routers.lotti_produzione as lp
    _ricetta_pizza(dbmock)
    run(dbmock.attrezzature_config.insert_one({"tipo": "frigo", "numero": 2, "nome": "Frigo 2", "attivo": True}))
    visto = {}
    originale = lp.scala_lotti_fornitori_per_ricetta

    async def _spia(ricetta, moltiplicatore, numero):
        visto["ingredienti"] = ricetta["ingredienti_dettaglio"]
        visto["moltiplicatore"] = moltiplicatore
        return await originale(ricetta, moltiplicatore, numero)
    monkeypatch.setattr(lp, "scala_lotti_fornitori_per_ricetta", _spia)

    oggi = {"ore_ambiente": 16, "temperatura_c": 24}
    lotto = _registra(lp, lievitazione_json=json.dumps(oggi))
    lievito = {i["nome"]: i["quantita"] for i in visto["ingredienti"]}["Lievito di birra"]
    assert lievito == pytest.approx(20 * 2 ** -1.2, abs=0.05)
    assert visto["moltiplicatore"] == 2
    assert lotto["lievitazione"]["righe"][0]["oggi"] == pytest.approx(40 * 2 ** -1.2, abs=0.1)
    prod = run(dbmock.produzioni.find_one({}))
    assert prod["lievitazione"]["condizioni"]["ore_ambiente"] == 16
    # la ricetta ufficiale non cambia
    assert run(dbmock.ricette.find_one({"id": "R-pizza"}))["ingredienti_dettaglio"][2]["quantita"] == 20


def test_registrazione_con_condizioni_sbagliate_non_lascia_nulla(dbmock):
    import app.lotti.routers.lotti_produzione as lp
    _ricetta_pizza(dbmock)
    run(dbmock.attrezzature_config.insert_one({"tipo": "frigo", "numero": 2, "nome": "Frigo 2", "attivo": True}))
    with pytest.raises(HTTPException) as err:
        _registra(lp, lievitazione_json='{"ore_ambiente": 8}', operation_id="prod-rotta")
    assert err.value.status_code == 400
    assert run(dbmock.lotti.count_documents({})) == 0
    assert run(dbmock.produzioni.count_documents({})) == 0
    assert run(dbmock.operazioni_idempotenti.count_documents({})) == 0
