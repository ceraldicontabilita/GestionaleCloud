"""
Motori tributi e fiscale — test sulla Specifica definitiva
(memoria/SPECIFICA_F24_CEDOLINI_IRES_IRAP_CHAT.md).

Copre: classificazione §6-11, scadenze/ravvedimenti §20, associazione §15
(esempio corretto e vietato), il caso reale F24 €50,61 (§16),
DM10↔RC01 §21, doppio pagamento §23, costo personale §12, IRES §13, IRAP §14.
"""
from app.engines import tributi_engine as te
from app.engines import fiscale_engine as fe


# ── F24 del caso §16 (saldo €50,61) ────────────────────────────────────────
F24_50_61 = {
    "dati_generali": {"codice_fiscale": "04523831214", "data_pagamento": "2023-01-16",
                      "saldo_delega": 50.61},
    "sezione_erario": [
        {"codice_tributo": "1001", "periodo_riferimento": "11/2022", "importo_debito": 1382.12},
        {"codice_tributo": "8906", "periodo_riferimento": "11/2022", "importo_debito": 36.56},
        {"codice_tributo": "6869", "periodo_riferimento": "11/2022", "importo_credito": 5024.76},
    ],
    "sezione_inps": [
        {"causale": "RC01", "periodo_riferimento": "11/2022", "importo_debito": 2840.00},
    ],
    "sezione_regioni": [
        {"codice_tributo": "3802", "periodo_riferimento": "11/2022", "importo_debito": 410.71},
    ],
    "sezione_tributi_locali": [
        {"codice_tributo": "3847", "periodo_riferimento": "11/2022", "importo_debito": 200.00},
        {"codice_tributo": "3848", "periodo_riferimento": "11/2022", "importo_debito": 205.98},
    ],
    "status": "pagato",
}

F24_ORDINARIO_11_2022 = {
    "dati_generali": {"codice_fiscale": "04523831214"},
    "sezione_erario": [
        {"codice_tributo": "1001", "periodo_riferimento": "11/2022", "importo_debito": 1382.12},
    ],
    "sezione_inps": [
        {"causale": "DM10", "periodo_riferimento": "11/2022", "importo_debito": 2840.00},
    ],
    "status": "pagato",
}


# ── §6-11 Classificazione ─────────────────────────────────────────────────

def test_classificazione_codici_erario():
    assert te.classifica_riga("erario", "1001")["natura"] == "ritenuta"
    assert te.classifica_riga("erario", "1001")["deducibilita"] == "no"
    assert te.classifica_riga("erario", "8906")["natura"] == "sanzione"
    assert te.classifica_riga("erario", "6869")["natura"] == "credito"
    assert te.classifica_riga("erario", "1701")["natura"] == "credito"


def test_classificazione_addizionali_regione_comune():
    r = te.classifica_riga("sezione_regioni", "3802")
    assert r["ente"] == "Regione" and r["natura"] == "ritenuta" and r["deducibilita"] == "no"
    c = te.classifica_riga("sezione_tributi_locali", "3848")
    assert c["ente"] == "Comune" and c["natura"] == "ritenuta"


def test_classificazione_inps_e_inail():
    dm10 = te.classifica_riga("inps", "DM10")
    assert dm10["natura"] == "costo" and dm10["deducibilita"] == "parziale"
    rc01 = te.classifica_riga("inps", "RC01")
    assert rc01["natura"] == "regolarizzazione"
    inail = te.classifica_riga("inail", "P")
    assert inail["natura"] == "costo" and inail["deducibilita"] == "si"


def test_codice_ignoto_mai_indovinato():
    x = te.classifica_riga("erario", "9999")
    assert x["deducibilita"] == "da_verificare"


# ── §20 Scadenza naturale e ritardo ───────────────────────────────────────

def test_scadenza_naturale_novembre_2022():
    assert te.scadenza_naturale(11, 2022).isoformat() == "2022-12-16"
    assert te.scadenza_naturale(12, 2022).isoformat() == "2023-01-16"


def test_pagamento_in_ritardo_31_giorni():
    esito = te.valuta_pagamento(11, 2022, "2023-01-16")
    assert esito["scadenza_naturale"] == "2022-12-16"
    assert esito["giorni_ritardo"] == 31
    assert esito["stato"] == "pagato_in_ritardo"


def test_pagamento_nei_termini():
    esito = te.valuta_pagamento(5, 2026, "2026-06-16")
    assert esito["stato"] == "pagato_nei_termini"
    assert esito["giorni_ritardo"] == 0


# ── §16 Caso reale €50,61 ─────────────────────────────────────────────────

def test_caso_50_61_classificazione_completa():
    analisi = te.classifica_f24(F24_50_61)
    assert analisi["periodo_prevalente"] == "11/2022"
    assert analisi["tipo_versamento"] == "regolarizzazione"
    assert analisi["stato"] == "pagato_in_ritardo"
    assert analisi["giorni_ritardo"] == 31
    assert analisi["saldo_finale"] == 50.61
    tot = analisi["totali_per_natura"]
    assert tot["ritenuta"] == round(1382.12 + 410.71 + 200.00 + 205.98, 2)
    assert tot["sanzione"] == 36.56
    assert tot["credito"] == 5024.76
    assert tot["regolarizzazione"] == 2840.00
    # Il saldo non è mai un costo: la nota deve dirlo
    assert "NON coincide" in analisi["nota_saldo"]


# ── §15 Associazione F24 ↔ cedolini ───────────────────────────────────────

def test_associazione_vietata_cedolini_maggio_2026():
    esito = te.valuta_associazione_cedolini(F24_50_61, 5, 2026)
    assert esito["associabile"] is False
    assert any("RC01" in m for m in esito["motivi"])
    assert any("11/2022" in m for m in esito["motivi"])
    assert "NON consentita" in esito["spiegazione"]


def test_associazione_consentita_maggio_2026():
    f24_maggio = {
        "dati_generali": {"codice_fiscale": "04523831214", "data_pagamento": "2026-06-16"},
        "sezione_erario": [
            {"codice_tributo": "1001", "periodo_riferimento": "05/2026", "importo_debito": 1000.0},
        ],
        "sezione_inps": [
            {"causale": "DM10", "periodo_riferimento": "05/2026", "importo_debito": 2000.0},
        ],
    }
    esito = te.valuta_associazione_cedolini(f24_maggio, 5, 2026,
                                            codice_fiscale_azienda="04523831214")
    assert esito["associabile"] is True
    assert "consentita" in esito["spiegazione"]


# ── §21 + §23 DM10 ↔ RC01 e doppio pagamento ──────────────────────────────

def test_collegamento_dm10_rc01():
    legame = te.confronta_dm10_rc01(F24_ORDINARIO_11_2022, F24_50_61)
    assert legame["collegati"] is True
    assert "1001" in legame["tributi_comuni"]


def test_stesso_mese_da_solo_non_basta():
    altro = {
        "dati_generali": {"codice_fiscale": "99999999999"},  # soggetto diverso
        "sezione_erario": [
            {"codice_tributo": "1001", "periodo_riferimento": "11/2022", "importo_debito": 10.0}],
        "sezione_inps": [{"causale": "RC01", "periodo_riferimento": "11/2022"}],
    }
    assert te.confronta_dm10_rc01(F24_ORDINARIO_11_2022, altro)["collegati"] is False


def test_possibile_doppio_pagamento():
    esito = te.rileva_doppio_pagamento(F24_ORDINARIO_11_2022, F24_50_61)
    assert esito["possibile_doppio_pagamento"] is True
    assert esito["stato"] == "da_verificare"
    assert esito["quota_potenzialmente_duplicata"] == 1382.12  # capitale 1001 ripetuto
    assert esito["quota_sanzioni_interessi"] == 36.56
    assert "POSSIBILE DOPPIO PAGAMENTO" in esito["messaggio"]


def test_solo_accessori_non_e_duplicato():
    solo_sanzioni = {
        "dati_generali": {"codice_fiscale": "04523831214", "data_pagamento": "2023-01-16"},
        "sezione_erario": [
            {"codice_tributo": "1001", "periodo_riferimento": "11/2022", "importo_debito": 0},
            {"codice_tributo": "8906", "periodo_riferimento": "11/2022", "importo_debito": 36.56}],
        "sezione_inps": [{"causale": "RC01", "periodo_riferimento": "11/2022", "importo_debito": 0}],
        "status": "pagato",
    }
    esito = te.rileva_doppio_pagamento(F24_ORDINARIO_11_2022, solo_sanzioni)
    assert esito["possibile_doppio_pagamento"] is False


# ── §12 Costo del personale ───────────────────────────────────────────────

def test_costo_personale_non_risomma_trattenute():
    out = fe.calcola_costo_personale({
        "retribuzioni_lorde": 10000, "inps_datoriale": 2800, "premio_inail": 150,
        "tfr_maturato": 700, "tredicesima": 800, "sgravi_recuperi": 300,
        # queste NON devono entrare nel totale:
        "irpef": 1382.12, "addizionale_regionale": 410.71, "netto_pagato": 7500,
    })
    assert out["costo_personale"] == 10000 + 2800 + 150 + 700 + 800 - 300
    assert set(out["voci_ignorate"]) == {"irpef", "addizionale_regionale", "netto_pagato"}


# ── §13 IRES / §14 IRAP ───────────────────────────────────────────────────

def test_ires_aliquota_versionata():
    out = fe.calcola_ires(2026, ricavi_imponibili=200000, costi_deducibili=150000,
                          variazioni_in_aumento=5000, variazioni_in_diminuzione=1000)
    assert out["imponibile_ires"] == 54000
    assert out["aliquota"] == 0.24
    assert out["imposta_ires"] == round(54000 * 0.24, 2)


def test_irap_separata_e_mai_intero_f24():
    out = fe.calcola_irap(
        2026, valore_produzione=180000,
        costo_personale_per_tipo={"indeterminato": 60000, "determinato": 20000},
        deduzioni_personale_per_tipo={"indeterminato": 60000, "determinato": 0},
        maggiorazione_regionale=0.0,
    )
    assert out["totale_deduzioni_personale"] == 60000
    assert out["imponibile_irap"] == 120000
    assert out["aliquota"] == 0.039
    assert "Mai sottratto l'intero F24" in out["nota"]


def test_irap_deduzione_non_supera_il_costo():
    out = fe.calcola_irap(2026, 100000,
                          costo_personale_per_tipo={"indeterminato": 30000},
                          deduzioni_personale_per_tipo={"indeterminato": 99999})
    assert out["deduzioni_personale"]["indeterminato"] == 30000
