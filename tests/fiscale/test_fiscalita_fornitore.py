"""Identità fiscale e IVA: memoria canonica, prove del documento e replay."""
import asyncio
from copy import deepcopy

import pytest

from app.database import Collections
from app.handlers.learning import handler_classifica_cdc
from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services import fiscalita_fornitore as fiscale
from app.services.learning_machine_cdc import CENTRI_COSTO


PIVA = "04219660158"
MERCI = "1.6_PRODOTTI_CONFEZIONATI"
VALIDITA = {"dal": "2026-01-01", "al": "2026-12-31"}


def run(coro):
    return asyncio.run(coro)


def profilo(regola="merci_attivita", **extra):
    return {"partita_iva": PIVA, "nome": "Perfetti Van Melle S.p.A.",
            "attivita": "Prodotti confezionati", "stato": "verificato", "identita_verificata": True,
            "ateco": {"codice": None, "versione": "2025", "stato": "non_verificato"},
            "regola_iva": regola, "centri_costo_ammessi": [MERCI],
            "validita_fiscale": VALIDITA,
            "fonti": [{"url": "https://example.test/identita", "titolo": "Identità ufficiale",
                       "verificata_il": "2026-10-12", "evidenza": "P.IVA 04219660158 e attività",
                       "tipo": "primaria"}], **extra}


def invoice(**extra):
    return {"id": "f-1", "supplier_id": "s-1", "supplier_vat": PIVA,
            "supplier_name": "Perfetti Van Melle S.p.A.", "invoice_date": "2026-09-30",
            "imponibile": 82.77, "iva": 18.21,
            "linee": [{"descrizione": "FRISK EXTREME BLACK X12", "prezzo_totale": 82.77,
                       "aliquota_iva": 22}], **extra}


def db_profilo(p=None, inv=None):
    db = ClientArchivioMemoria()["fiscalita-test"]
    run(db[Collections.SUPPLIERS].insert_one({"id": "s-1", "partita_iva": PIVA,
                                           "nome": "Perfetti Van Melle S.p.A.",
                                           "profilo_fiscale": p if p is not None else profilo()}))
    if inv is not None:
        run(db[Collections.INVOICES].insert_one(inv))
    return db


def valutazione(p=None, inv=None, cdc=MERCI, righe=None):
    fattura = inv or invoice()
    risolta = {"stato": "risolto", "partita_iva": PIVA, "supplier_id": "s-1",
               "profilo": p or profilo()}
    return fiscale.valuta_iva_fattura(
        fattura, risolta, cdc, CENTRI_COSTO[cdc],
        righe if righe is not None else [{"centro_costo_id": cdc, "richiede_verifica": False}],
    )


def contesto(**extra):
    return {"confermato_da": "admin", "fonte_documento": "documento-uso",
            "validita_fiscale": VALIDITA, "inerente": True, **extra}


def test_cespite_senza_profilo_richiede_inerenza_documentata():
    cdc = "15.1_ACQUISTO_BENI_STRUMENTALI"
    inv = invoice(linee=[{"descrizione": "Condizionatore split Daikin", "prezzo_totale": 1500}])
    risolta = {"stato": "assente", "profilo": None}
    righe = [{"centro_costo_id": cdc, "richiede_verifica": False}]
    assert fiscale.valuta_iva_fattura(inv, risolta, cdc, CENTRI_COSTO[cdc], righe)["iva_detraibile"] is None
    inv["contesto_fiscale_iva"] = contesto()
    assert fiscale.valuta_iva_fattura(inv, risolta, cdc, CENTRI_COSTO[cdc], righe)["iva_detraibile"] == 18.21


def test_cespite_in_fattura_mista_merci_richiede_comunque_inerenza():
    inv = invoice(linee=[{"descrizione": "FRISK EXTREME", "prezzo_totale": 100},
                         {"descrizione": "Condizionatore split Daikin", "prezzo_totale": 1500}])
    righe = [{"centro_costo_id": MERCI, "richiede_verifica": False},
             {"centro_costo_id": "15.1_ACQUISTO_BENI_STRUMENTALI", "richiede_verifica": False}]
    assert valutazione(profilo(), inv, MERCI, righe)["iva_detraibile"] is None
    inv["contesto_fiscale_iva"] = contesto()
    assert valutazione(profilo(), inv, MERCI, righe)["iva_detraibile"] == 18.21


def test_grossista_alimentare_puo_vendere_detergenza_documentata():
    cdc = "12.1_PULIZIA_LOCALE"
    p = profilo(centri_costo_ammessi=[MERCI, cdc])
    inv = invoice(linee=[{"descrizione": "Detersivo lavastoviglie"}],
                  contesto_fiscale_iva=contesto())
    assert valutazione(p, inv, cdc)["percentuale_detraibilita_iva"] == 1.0
    assert valutazione(p, invoice(linee=inv["linee"]), cdc)["iva_detraibile"] is None


def test_gamma_web_superata_da_prova_non_elimina_vincoli_telefonia():
    inv = invoice(linee=[{"descrizione": "Canone telefonia"}],
                  contesto_fiscale_iva=contesto(percentuale_utilizzo_aziendale=0.8))
    esito = valutazione(profilo(), inv, "10.1_TELEFONIA")
    assert esito["percentuale_detraibilita_iva"] == 0.8
    assert esito["valutazione_fiscale_iva"]["gamma_fornitore_superata_da_documento"] is True
    assert valutazione(profilo(), invoice(linee=inv["linee"]), "10.1_TELEFONIA")["iva_detraibile"] is None


def test_importa_solo_master_exact_anteprima_idempotenza_e_profilo_manual_protetto(monkeypatch):
    db = db_profilo()
    run(db[Collections.SUPPLIERS].update_one({"id": "s-1"}, {"$unset": {"profilo_fiscale": ""}}))
    monkeypatch.setattr(fiscale, "carica_memoria", lambda: {"versione": 1, "profili": [profilo()]})
    prima = run(db[Collections.SUPPLIERS].find_one({"id": "s-1"}))
    anteprima = run(fiscale.importa_memoria(db))
    assert anteprima["da_aggiornare"] == 1 and anteprima["aggiornate"] == 0
    assert run(db[Collections.SUPPLIERS].find_one({"id": "s-1"})) == prima
    assert run(fiscale.importa_memoria(db, False))["aggiornate"] == 1
    assert run(fiscale.importa_memoria(db, False))["invariate"] == 1
    run(db[Collections.SUPPLIERS].update_one({"id": "s-1"}, {"$set": {
        "profilo_fiscale": profilo(confermato_da="commercialista", regola_iva="da_verificare")}}))
    assert run(fiscale.importa_memoria(db, False))["protette"] == 1
    assert run(db[Collections.SUPPLIERS].find_one({"id": "s-1"}))["profilo_fiscale"]["regola_iva"] == "da_verificare"
    assert run(db[Collections.INVOICES].count_documents({})) == 0


def test_import_non_crea_fornitore_dal_nome_o_da_piva_sbagliata(monkeypatch):
    db = ClientArchivioMemoria()["fiscalita-test"]
    run(db[Collections.SUPPLIERS].insert_one({"id": "s-2", "nome": "Perfetti Van Melle S.p.A.",
                                           "partita_iva": "12345678901"}))
    monkeypatch.setattr(fiscale, "carica_memoria", lambda: {"versione": 1, "profili": [profilo()]})
    report = run(fiscale.importa_memoria(db, False))
    assert report["non_trovate"] == 1 and report["aggiornate"] == 0
    assert run(db[Collections.SUPPLIERS].count_documents({})) == 1


def test_piva_duplicate_ambigue_non_importate_ne_usate(monkeypatch):
    db = db_profilo()
    run(db[Collections.SUPPLIERS].insert_one({"id": "s-2", "partita_iva": "IT" + PIVA}))
    monkeypatch.setattr(fiscale, "carica_memoria", lambda: {"versione": 1, "profili": [profilo()]})
    assert run(fiscale.importa_memoria(db, False))["conflitti"] == 1
    assert run(fiscale.risolvi_profilo(db, invoice()))["stato"] == "da_verificare"


def test_risoluzione_normalizza_it_senza_fuzzy_nome_e_senza_zeri_eliminati():
    db = db_profilo()
    assert run(fiscale.risolvi_profilo(db, invoice(supplier_vat="IT" + PIVA,
                                                supplier_name="Nome cambiato")))["stato"] == "risolto"
    assert run(fiscale.risolvi_profilo(db, invoice(supplier_vat=PIVA.lstrip("0"))))["profilo"] is None
    assert run(fiscale.risolvi_profilo(db, invoice(supplier_id="s-altra")))["stato"] == "da_verificare"


def test_gruppo_iva_richiede_cf_e_denominazione_documentati():
    p = profilo(gruppo_iva=True, codice_fiscale="CF-ESATTO")
    db = db_profilo(p)
    assert run(fiscale.risolvi_profilo(db, invoice()))["stato"] == "da_verificare"
    assert run(fiscale.risolvi_profilo(db, invoice(fornitore_cf="CF-ESATTO")))["stato"] == "risolto"
    assert run(fiscale.risolvi_profilo(db, invoice(fornitore_cf="CF-ESATTO",
                                                supplier_name="Perfetti")))["stato"] == "da_verificare"


def test_perfetti_iva_intera_e_percentuale_canonica_non_rapporto_arrotondato():
    esito = valutazione()
    assert esito["percentuale_detraibilita_iva"] == 1
    assert esito["iva_detraibile"] == 18.21 and esito["iva_indetraibile"] == 0
    assert esito["valutazione_fiscale_iva"]["fonti"][0]["url"]


@pytest.mark.parametrize("variante", [
    {"invoice_date": "2003-09-30"},
    {"linee": [{"descrizione": "Omaggio di rappresentanza"}]},
    {"pro_rata": 0.7},
])
def test_merci_non_eliminano_condizioni_storiche_particolari_o_pro_rata(variante):
    esito = valutazione(inv=invoice(**variante))
    assert esito["iva_detraibile"] is None and esito["percentuale_detraibilita_iva"] is None


def test_profile_ateco_non_verificato_non_inventa_numero_ma_attivita_verificata_puo_supportare_merci():
    assert valutazione()["iva_detraibile"] == 18.21
    assert valutazione(p=profilo(stato="da_verificare"))["iva_detraibile"] is None
    assert valutazione(p=profilo(fonti=[]))["iva_detraibile"] is None


def test_riga_ignota_o_trattamento_diverso_impedisce_100_testata():
    for cdc in ["99_ALTRI_COSTI", "6.1_NOLEGGIO_AUTO", "10.1_TELEFONIA"]:
        esito = valutazione(righe=[{"centro_costo_id": MERCI}, {"centro_costo_id": cdc}])
        assert esito["iva_detraibile"] is None


def test_telefonia_iva_utilizzo_documentato_e_non_ires80_o_iva50():
    cdc = "10.1_TELEFONIA"
    p = profilo("telefonia", centri_costo_ammessi=[cdc])
    assert valutazione(p, cdc=cdc)["iva_detraibile"] is None
    esito = valutazione(p, invoice(contesto_fiscale_iva=contesto(percentuale_utilizzo_aziendale=1)), cdc)
    assert esito["percentuale_detraibilita_iva"] == 1 and esito["iva_detraibile"] == 18.21
    assert CENTRI_COSTO[cdc]["deducibilita_ires"] == 0.8


@pytest.mark.parametrize("uso,pct", [("promiscuo", 0.4), ("esclusivo", 1)])
def test_auto_uso_documentato_separato_da_ires70(uso, pct):
    cdc = "6.1_NOLEGGIO_AUTO"
    p = profilo("noleggio_veicoli", centri_costo_ammessi=[cdc])
    assert valutazione(p, cdc=cdc)["iva_detraibile"] is None
    f = invoice(auto_assegnata=True, contesto_fiscale_iva=contesto(tipo_veicolo="autovettura", uso_veicolo=uso))
    esito = valutazione(p, f, cdc)
    assert esito["percentuale_detraibilita_iva"] == pct
    assert esito["iva_detraibile"] == (7.28 if pct == 0.4 else 18.21)


def test_pro_rata_documentato_applica_percentuale_esplicita():
    esito = valutazione(inv=invoice(contesto_fiscale_iva=contesto(pro_rata_applicabile=True, pro_rata=0.5)))
    assert esito["iva_detraibile"] == 9.11 and esito["percentuale_detraibilita_iva"] == 0.5


def test_beni_misti_o_cespiti_non_derivano_inerenza_da_attivita_fornitore():
    cdc = "5.3_PICCOLE_ATTREZZATURE"
    p = profilo("cespiti", centri_costo_ammessi=[cdc])
    f = invoice(linee=[{"descrizione": "Stampante da ufficio"}])
    assert valutazione(p, f, cdc)["iva_detraibile"] is None
    f["contesto_fiscale_iva"] = contesto()
    assert valutazione(p, f, cdc, [{"centro_costo_id": cdc, "richiede_verifica": True}])["iva_detraibile"] == 18.21


def test_handler_legge_master_prima_calcolo_salva_audit_e_replay_idempotente():
    f = invoice(iva_detraibile=9.11, iva_indetraibile=9.10,
                centro_costo_id="10.1_TELEFONIA", stato_detrazione_iva="DA_VERIFICARE")
    db = db_profilo(inv=f)
    assert run(handler_classifica_cdc({"fattura_id": f["id"]}, db))["iva_da_verificare"] is False
    dopo = run(db[Collections.INVOICES].find_one({"id": f["id"]}))
    assert dopo["centro_costo_id"] == MERCI and dopo["iva_detraibile"] == 18.21
    assert dopo["percentuale_detraibilita_iva"] == 1
    assert dopo["valutazione_fiscale_iva"]["supplier_id"] == "s-1"
    run(handler_classifica_cdc({"fattura_id": f["id"]}, db))
    assert run(db[Collections.INVOICES].find_one({"id": f["id"]})) == dopo


@pytest.mark.parametrize("protezione", [
    {"iva_utilizzata": True}, {"classificazione_manuale": True},
    {"classificato_da": "manuale"}, {"stato_detrazione_iva": "INSERITA_IN_LIQUIDAZIONE"},
])
def test_handler_non_modifica_decisioni_manual_o_iva_utilizzata(protezione):
    f = invoice(iva_detraibile=9.11, **protezione)
    db = db_profilo(inv=f)
    prima = run(db[Collections.INVOICES].find_one({"id": f["id"]}))
    assert run(handler_classifica_cdc({"fattura_id": f["id"]}, db))["skipped"] is True
    assert run(db[Collections.INVOICES].find_one({"id": f["id"]})) == prima


def test_handler_non_modifica_periodo_liquidazione_chiuso():
    f = invoice(periodo_iva_attribuito="2026-09")
    db = db_profilo(inv=f)
    run(db["liquidazioni_iva"].insert_one({"id": "l-1", "periodo": "2026-09", "versione": 1, "stato": "CONFERMATA"}))
    prima = run(db[Collections.INVOICES].find_one({"id": f["id"]}))
    assert run(handler_classifica_cdc({"fattura_id": f["id"]}, db))["skipped"] is True
    assert run(db[Collections.INVOICES].find_one({"id": f["id"]})) == prima


def test_master_fallback_non_forza_righe_evidenti_fuori_gamma():
    risolta = {"stato": "risolto", "profilo": profilo()}
    originale = ("10.1_TELEFONIA", CENTRI_COSTO["10.1_TELEFONIA"], 0.9, "contenuto_fattura")
    assert fiscale.adatta_classificazione_al_profilo(
        invoice(), risolta, "", [{"descrizione": "Canone telefonia e internet"}], originale) == originale
    fallback = fiscale.adatta_classificazione_al_profilo(
        invoice(), risolta, "", [{"descrizione": "FRISK EXTREME BLACK X12"}], originale)
    assert fallback[0] == MERCI and fallback[3] == "profilo_fiscale_fornitore"


def test_master_multicategoria_non_conserva_fallback_fuori_gamma():
    p = profilo(centri_costo_ammessi=["1.3_MATERIE_PRIME_PASTICCERIA", "1.8_MATERIE_PRIME_CUCINA"])
    esito = fiscale.adatta_classificazione_al_profilo(
        invoice(), {"stato": "risolto", "profilo": p}, "", [{"descrizione": "ARTICOLO 123"}],
        (MERCI, CENTRI_COSTO[MERCI], 0.65, "tabella_statica"))
    assert esito[0] == "99_ALTRI_COSTI" and esito[2] == 0


def test_profilo_non_verificato_non_blocca_prova_merceologica_esplicita_del_documento():
    cdc = "1.1_CAFFE_BEVANDE_CALDE"
    f = invoice(linee=[{"descrizione": "Caffè in grani", "prezzo_totale": 82.77, "aliquota_iva": 22}])
    esito = valutazione(profilo(stato="da_verificare"), f, cdc)
    assert esito["iva_detraibile"] == 18.21
    assert esito["valutazione_fiscale_iva"]["fonte"] == "classificazione_documento"
    assert esito["valutazione_fiscale_iva"]["profilo_applicato"] is False


def test_iva_storica_da_documento_non_dichiara_valido_un_profilo_del_2026():
    cdc = "1.1_CAFFE_BEVANDE_CALDE"
    f = invoice(invoice_date="2003-09-30", linee=[{"descrizione": "Caffè in grani"}])
    esito = valutazione(profilo(), f, cdc)
    assert esito["iva_detraibile"] == 18.21
    assert esito["valutazione_fiscale_iva"]["profilo_applicato"] is False
    assert "data" in esito["valutazione_fiscale_iva"]["motivo_profilo_non_applicato"]


def test_campo_vat_master_usato_exact_con_prefisso_it():
    db = ClientArchivioMemoria()["fiscalita-test"]
    run(db[Collections.SUPPLIERS].insert_one({"id": "s-1", "vat": "IT" + PIVA,
                                           "profilo_fiscale": profilo()}))
    assert run(fiscale.risolvi_profilo(db, invoice()))["stato"] == "risolto"


def test_identita_collegata_usa_piva_normalizzata_senza_nome():
    db = ClientArchivioMemoria()["fiscalita-test"]
    run(db[Collections.SUPPLIERS].insert_one({"id": "s-1", "vat": "IT 04219660158",
                                           "profilo_fiscale": profilo()}))
    assert run(fiscale.risolvi_profilo(db, invoice()))["stato"] == "risolto"


@pytest.mark.parametrize("ctx", [contesto(), contesto(pro_rata_applicabile=True, pro_rata=0.7)])
def test_pro_rata_fattura_non_ignorato_per_presenza_di_altro_contesto_documentato(ctx):
    esito = valutazione(inv=invoice(pro_rata=0.5, contesto_fiscale_iva=ctx))
    assert esito["iva_detraibile"] is None


def test_profilo_dichiarato_verificato_ma_identita_falsa_non_applicato():
    p = profilo(identita_verificata=False)
    assert valutazione(p)["iva_detraibile"] is None
    db = db_profilo(p)
    assert run(fiscale.risolvi_profilo(db, invoice()))["stato"] == "da_verificare"


def test_secondaria_o_piva_non_documentata_non_autorizza_master():
    for fonti in [[{"url": "https://example.test", "tipo": "secondaria", "verificata_il": "2026-10-12",
                   "evidenza": "PIVA 04219660158"}],
                 [{"url": "https://example.test", "tipo": "primaria", "verificata_il": "2026-10-12",
                   "evidenza": "Attività di caramelle senza identità fiscale"}]]:
        assert valutazione(profilo(fonti=fonti))["iva_detraibile"] is None


def test_codici_bilancio_equivalenti_al_centro_interno_non_creano_seconda_regola():
    f = invoice()
    risolta = {"stato": "risolto", "profilo": profilo(), "partita_iva": PIVA, "supplier_id": "s-1"}
    esito = fiscale.valuta_iva_fattura(
        f, risolta, "B6.1.6", CENTRI_COSTO[MERCI], [{"centro_costo_id": "B6.1.6"}])
    assert esito["iva_detraibile"] == 18.21 and esito["percentuale_detraibilita_iva"] == 1


def test_manualita_non_maschera_liquidazione_chiusa():
    f = invoice(classificazione_manuale=True, periodo_iva_attribuito="2026-09")
    db = db_profilo(inv=f)
    run(db["liquidazioni_iva"].insert_one({"id": "l-1", "periodo": "2026-09", "versione": 1, "stato": "CHIUSA"}))
    assert "Liquidazione" in run(fiscale.motivo_fattura_protetta(db, f))


@pytest.mark.parametrize("anno", [2003, 2027])
def test_regola_condizionale_non_estesa_a_periodi_non_verificati(anno):
    cdc = "6.1_NOLEGGIO_AUTO"
    f = invoice(invoice_date=f"{anno}-09-30", contesto_fiscale_iva={
        **contesto(tipo_veicolo="autovettura", uso_veicolo="promiscuo"),
        "validita_fiscale": {"dal": f"{anno}-01-01", "al": f"{anno}-12-31"}})
    esito = fiscale.valuta_iva_fattura(f, {"stato": "assente", "profilo": None}, cdc,
                                    CENTRI_COSTO[cdc], [{"centro_costo_id": cdc}])
    assert esito["iva_detraibile"] is None
    assert "fuori periodo" in esito["valutazione_fiscale_iva"]["motivo"]
