"""
Arricchimento IVA delle fatture (app/engines/iva_fatture.py): dai dati grezzi
di una fattura ricava periodo IVA attribuito, regola e stato di detrazione.
"""
from app.engines import iva_fatture as ivf


def test_fattura_immediata_stesso_mese():
    inv = {"invoice_date": "2026-03-10", "created_at": "2026-03-12T00:00:00", "iva": 220}
    c = ivf.campi_iva_da_fattura(inv)
    assert c["periodo_iva_attribuito"] == "2026-03"
    assert c["regola_iva_applicata"] == "STESSO_MESE"
    assert c["iva_documento"] == 220
    assert c["iva_utilizzata"] is False
    assert c["stato_detrazione_iva"] == "DA_VERIFICARE"
    assert "iva_detraibile" not in c, (
        "Su una fattura mai classificata la detraibilita' non e' «zero»: non "
        "e' stata decisa. Scrivere 0.00 la fa sembrare decisa e disarma "
        "l'unica guardia del libro giornale, che rifiuta la registrazione "
        "finche' `iva_detraibile is None`."
    )


def test_una_fattura_mai_classificata_resta_fuori_dal_libro_giornale():
    """La prova che conta: la guardia del giornale regge dopo il ricalcolo IVA."""
    from app.services.registrazione_contabile import registra_fattura
    import asyncio

    inv = {"id": "f-1", "invoice_date": "2026-03-10", "iva": 220, "total_amount": 1220}
    inv.update(ivf.campi_iva_da_fattura(inv))

    loop = asyncio.new_event_loop()
    try:
        # `force=True` salta il controllo di idempotenza, che e' l'unico
        # punto che toccherebbe il database: la guardia si valuta prima di
        # qualunque scrittura.
        esito = loop.run_until_complete(registra_fattura(None, inv, force=True))
    finally:
        loop.close()

    assert esito["stato"] == "da_verificare"
    assert esito["motivo"] == "IVA detraibile non classificata"


def test_fattura_classificata_preserva_iva_detraibile():
    inv = {
        "invoice_date": "2026-03-10", "iva": 220,
        "iva_detraibile": 88, "classificato_da": "learning_machine",
        "stato_classificazione": "classificata",
    }
    c = ivf.campi_iva_da_fattura(inv)
    assert c["iva_documento"] == 220
    assert c["iva_detraibile"] == 88
    assert c["stato_detrazione_iva"] == "DA_INSERIRE"


def test_classificazione_incerta_non_diventa_credito_disponibile():
    inv = {
        "invoice_date": "2026-03-10", "iva": 220,
        "iva_detraibile": 88, "classificato_da": "learning_machine",
        "stato_classificazione": "da_verificare",
    }
    c = ivf.campi_iva_da_fattura(inv)
    assert c["iva_detraibile"] == 88
    assert c["stato_detrazione_iva"] == "DA_VERIFICARE"


def test_ricevuta_entro_il_15_attribuita_mese_precedente():
    # operazione 31/01 (data documento), ricevuta/registrata l'8-10/02 → gennaio
    inv = {"invoice_date": "2026-01-31", "data_ricezione": "2026-02-08",
           "data_registrazione": "2026-02-10", "iva": 100}
    c = ivf.campi_iva_da_fattura(inv)
    assert c["periodo_iva_attribuito"] == "2026-01"
    assert c["regola_iva_applicata"] == "ENTRO_15_MESE_SUCCESSIVO"


def test_periodo_da_righe_operazione():
    # fattura periodica: l'operazione è la fine periodo indicata nella riga
    inv = {"invoice_date": "2026-03-05",
           "linee": [{"data_inizio_periodo": "2026-02-01", "data_fine_periodo": "2026-02-28"}],
           "data_ricezione": "2026-03-05", "iva": 50}
    c = ivf.campi_iva_da_fattura(inv)
    assert c["data_operazione"] == "2026-02-28"
    # operazione febbraio, ricezione 5/3 (entro il 15) → attribuita a febbraio
    assert c["periodo_iva_attribuito"] == "2026-02"


def test_cambio_anno_non_retroattribuisce():
    inv = {"invoice_date": "2025-12-31", "data_ricezione": "2026-01-08",
           "data_registrazione": "2026-01-08", "iva": 300}
    c = ivf.campi_iva_da_fattura(inv)
    assert c["periodo_iva_attribuito"] == "2026-01"
    assert c["regola_iva_applicata"] == "OPERAZIONE_ANNO_PRECEDENTE"


def test_iva_gia_utilizzata_non_viene_toccata():
    inv = {"invoice_date": "2026-01-31", "data_ricezione": "2026-02-08",
           "iva": 100, "iva_utilizzata": True,
           "stato_detrazione_iva": "INSERITA_IN_LIQUIDAZIONE",
           "periodo_iva_utilizzato": "2026-01"}
    c = ivf.campi_iva_da_fattura(inv)
    assert c["iva_utilizzata"] is True
    assert c["stato_detrazione_iva"] == "INSERITA_IN_LIQUIDAZIONE"
    assert c["periodo_iva_utilizzato"] == "2026-01"


def test_fallback_data_ricezione_su_data_documento():
    # P2-a (fix 13/07/2026): senza data_ricezione esplicita si usa la data del
    # DOCUMENTO, NON la data di importazione (created_at), che per le fatture
    # storiche importate in blocco mis-attribuirebbe il pregresso.
    inv = {"invoice_date": "2026-05-31", "created_at": "2026-06-10T09:00:00", "iva": 10}
    c = ivf.campi_iva_da_fattura(inv)
    assert c["data_ricezione"] == "2026-05-31"
    assert c["periodo_iva_attribuito"] == "2026-05"


def test_da_verificare_del_motore_si_sblocca_quando_la_detraibilita_arriva():
    """Il motore gira all'import prima della classificazione: il suo
    DA_VERIFICARE non deve restare appiccicato quando `iva_detraibile` arriva."""
    inv = {"invoice_date": "2026-03-10", "created_at": "2026-03-12T00:00:00", "iva": 220}
    inv.update(ivf.campi_iva_da_fattura(inv))
    assert inv["stato_detrazione_iva"] == "DA_VERIFICARE"
    inv["iva_detraibile"] = 220
    assert ivf.campi_iva_da_fattura(inv)["stato_detrazione_iva"] == "DA_INSERIRE"


def test_non_valutata_e_da_decidere_come_nel_riepilogo():
    from app.engines.liquidazione_iva_engine import detraibilita_da_decidere
    assert detraibilita_da_decidere(
        {"iva": 22, "iva_detraibile": 22, "stato_detrazione_iva": "NON_VALUTATA"})


# ── dubbio analitico ≠ dubbio fiscale (07/10/2026: 201 fatture su 265 escluse) ──

def _fattura_da_verificare(**extra):
    inv = {"invoice_date": "2026-06-10", "iva": 220, "iva_detraibile": 220,
           "classificato_da": "learning_machine", "stato_classificazione": "da_verificare",
           "classificazione_confidence": 0.3}
    inv.update(extra)
    return inv


def test_materie_prime_con_righe_incerte_entrano_in_liquidazione():
    """Il classificatore non sa in quale sottoconto va il costo: dubbio del
    bilancio, non dell'IVA. La fattura di materie prime resta al 100%."""
    inv = _fattura_da_verificare(
        centro_costo_id="1.3_MATERIE_PRIME_PASTICCERIA",
        classificazioni_righe=[
            {"numero_linea": "1", "centro_costo_id": "99_ALTRI_COSTI", "richiede_verifica": True},
            {"numero_linea": "2", "centro_costo_id": "1.3_MATERIE_PRIME_PASTICCERIA",
             "richiede_verifica": False},
        ])
    c = ivf.campi_iva_da_fattura(inv)
    assert c["stato_detrazione_iva"] == "DA_INSERIRE"
    assert c["motivo_detraibilita_da_verificare"] is None


def test_centro_di_costo_indeterminato_resta_da_verificare_con_il_motivo():
    c = ivf.campi_iva_da_fattura(_fattura_da_verificare(centro_costo_id="99_ALTRI_COSTI"))
    assert c["stato_detrazione_iva"] == "DA_VERIFICARE"
    assert "non determinato" in c["motivo_detraibilita_da_verificare"]


def test_detraibilita_ridotta_incerta_resta_da_verificare():
    """Telefonia al 50% con confidenza bassa: se il centro e' sbagliato
    cambia l'IVA, quindi decide una persona."""
    inv = _fattura_da_verificare(centro_costo_id="10.1_TELEFONIA", iva_detraibile=110)
    c = ivf.campi_iva_da_fattura(inv)
    assert c["stato_detrazione_iva"] == "DA_VERIFICARE"
    assert "50%" in c["motivo_detraibilita_da_verificare"]
    # con confidenza alta la stessa classificazione e' una decisione
    inv["classificazione_confidence"] = 0.9
    assert ivf.campi_iva_da_fattura(inv)["stato_detrazione_iva"] == "DA_INSERIRE"


def test_riga_con_detraibilita_diversa_dalla_testata_resta_da_verificare():
    inv = _fattura_da_verificare(
        centro_costo_id="1.3_MATERIE_PRIME_PASTICCERIA",
        classificazioni_righe=[
            {"numero_linea": "3", "centro_costo_id": "10.1_TELEFONIA", "richiede_verifica": False},
        ])
    c = ivf.campi_iva_da_fattura(inv)
    assert c["stato_detrazione_iva"] == "DA_VERIFICARE"
    assert "riga 3" in c["motivo_detraibilita_da_verificare"]


def test_classificata_non_ha_motivo_e_la_liquidazione_mostra_il_motivo_quando_c_e():
    from app.engines.liquidazione_iva_engine import seleziona_fatture_per_liquidazione
    ok = ivf.campi_iva_da_fattura(_fattura_da_verificare(stato_classificazione="classificata"))
    assert ok["motivo_detraibilita_da_verificare"] is None
    f = {"id": "f-99", "supplier_name": "X", "iva": 22, "iva_detraibile": 22,
         "periodo_iva_attribuito": "2026-06", "stato_detrazione_iva": "DA_VERIFICARE",
         "motivo_detraibilita_da_verificare": "centro di costo non determinato: decidere la detraibilita'"}
    incluse, escluse = seleziona_fatture_per_liquidazione([f], "2026-06")
    assert not incluse
    assert escluse[0]["motivo_esclusione"].endswith("centro di costo non determinato: decidere la detraibilita'")
