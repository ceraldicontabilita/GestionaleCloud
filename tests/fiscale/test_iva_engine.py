"""
Motore IVA — attribuzione periodo per competenza (SPECIFICA_IVA.md §9, §24).
"""
from app.engines import iva_engine as iva


def test_regola_A_stesso_mese():
    # operazione e ricezione stesso mese → periodo = quel mese
    p, r = iva.attribuisci_periodo_iva("2026-01-31", "2026-01-31", "2026-01-31")
    assert p == "2026-01" and r == iva.STESSO_MESE


def test_regola_B_entro_il_15():
    # SPECIFICA §24 Test 1: operazione gennaio, ricezione 8/2, registrazione 10/2
    # → attribuita a GENNAIO
    p, r = iva.attribuisci_periodo_iva("2026-01-31", "2026-02-08", "2026-02-10")
    assert p == "2026-01" and r == iva.ENTRO_15_MESE_SUCCESSIVO


def test_regola_B_serve_anche_registrazione_entro_15():
    # ricezione entro il 15 ma registrazione il 20 → NON deroga, va a febbraio
    p, r = iva.attribuisci_periodo_iva("2026-01-31", "2026-02-08", "2026-02-20")
    assert p == "2026-02" and r == iva.RICEVUTA_DOPO_IL_15


def test_regola_C_dopo_il_15():
    # SPECIFICA §24 Test 2: operazione gennaio, ricezione 18/2 → FEBBRAIO
    p, r = iva.attribuisci_periodo_iva("2026-01-31", "2026-02-18", "2026-02-18")
    assert p == "2026-02" and r == iva.RICEVUTA_DOPO_IL_15


def test_regola_D_cambio_anno_no_retroattribuzione():
    # SPECIFICA §24 Test 3 / §6: operazione dicembre 2025, ricezione gennaio 2026
    # → attribuita a GENNAIO 2026, MAI a dicembre 2025
    p, r = iva.attribuisci_periodo_iva("2025-12-31", "2026-01-08", "2026-01-08")
    assert p == "2026-01" and r == iva.OPERAZIONE_ANNO_PRECEDENTE


def test_regola_D_anche_se_entro_il_15():
    # cambio anno vince sulla regola del 15: dicembre→gennaio resta gennaio
    p, r = iva.attribuisci_periodo_iva("2025-12-20", "2026-01-10", "2026-01-10")
    assert p == "2026-01" and r == iva.OPERAZIONE_ANNO_PRECEDENTE


def test_date_mancanti():
    p, r = iva.attribuisci_periodo_iva(None, "2026-02-08")
    assert p is None and r == "DA_VERIFICARE"


def test_mesi_distanti_va_a_ricezione():
    # operazione gennaio, ricezione aprile → aprile (non deroga)
    p, r = iva.attribuisci_periodo_iva("2026-01-15", "2026-04-03", "2026-04-03")
    assert p == "2026-04" and r == iva.RICEVUTA_DOPO_IL_15


def test_controllo_12_giorni():
    # emessa/trasmessa 20 giorni dopo l'operazione → anomalia
    res = iva.controllo_emissione_12_giorni("2026-01-01", "2026-01-21")
    assert res["giorni"] == 20 and res["anomalia"] is True
    # entro i 12 giorni → nessuna anomalia
    ok = iva.controllo_emissione_12_giorni("2026-01-01", "2026-01-10")
    assert ok["giorni"] == 9 and ok["anomalia"] is False


def test_controllo_12_giorni_non_tocca_periodo():
    # il controllo 12 giorni NON influenza l'attribuzione (competenza a parte)
    p, _ = iva.attribuisci_periodo_iva("2026-01-31", "2026-02-08", "2026-02-10")
    assert p == "2026-01"  # resta la regola del 15, indipendente dai 12 giorni
