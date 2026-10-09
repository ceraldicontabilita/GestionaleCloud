"""Ricevute di pagamento pagoPA che il lettore generico non capiva.

* Mooney («Ricevuta per l'utente», pagato con PayPal): il livello testo porta solo
  gli importi, il resto e' un'immagine letta con l'OCR e rimessa in righe per
  posizione. Nessun dato vero nei test: importi, IUV e ID sono inventati.
* Attestazione dell'Agente della Riscossione: testo vero, una cartella o piu'
  documenti con lo stesso IUV, voci letta per voce.
"""
import asyncio
import os

import fitz
import pytest

from app.routers.documenti import detect_document_type
from app.services import pagopa_receipts as modulo
from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.pagopa_receipts import (
    _parse_ader_attestazione,
    _parse_mooney_payment,
    collega_ricevuta_a_paypal,
    import_receipt,
    parse_receipt_pdf,
    ricollega_ricevute_paypal,
)

IUV_A = "80070000000000001"
IUV_B = "80070000000000002"
PAYPAL_ID = "1AB23456CD789012E"

# Righe come le restituisce l'OCR per posizione: spazi persi, «0» al posto di «o».
MOONEY_RIGHE = """\
mooney
RICEVUTAPERL'UTENTE
Servizio erogato da Mooney S.p.A Abo IMEL ex art.114-
Sigla operatore:11111.111
Datae0ra:01/09/202610:15
CodiceCarrello:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
ID PSP: MOONTMMXXX
Beneficiario:ENTETEST
Ente Creditore:12345678901
IUV:{iuv}
ID Operazione:9999999
IdentificativoRisc0ssione:abcdef0123456789abcdef0123456789
Causale:Pagamentoafavoredellamministrazione
Lapresentericevutacostituisceattestazionedipagamentoedeliberatoria
ID Ricevuta:TESTRIC01
Pagamento
Importo: {importo}
Diritti: {diritti}
Totale: {totale}
PAGAMENTO:
PayPal ID: {paypal}
Payment ID: 1234567890123456789
Importo:5.88
Pagamentoimmediatamenteassolto
"""


def _mooney(importo="5,88", diritti="1,50", totale="7,38", iuv=IUV_A, paypal=PAYPAL_ID):
    return MOONEY_RIGHE.format(iuv=iuv, importo=importo, diritti=diritti, totale=totale, paypal=paypal)


def test_mooney_legge_tutti_i_campi_e_le_cifre_tornano():
    r = _parse_mooney_payment(_mooney())

    assert r["is_payment_receipt"] is True and r["importi_quadrano"] is True
    assert (r["operation_amount"], r["fee_amount"], r["bank_debit_total"]) == (5.88, 1.5, 7.38)
    assert r["identificativo_bolletta"] == IUV_A
    assert (r["data_pagamento"], r["ora_pagamento"]) == ("2026-09-01", "10:15")
    assert r["beneficiario"] == "ENTETEST" and r["ente_creditore"] == "12345678901"
    assert r["paypal_transaction_id"] == PAYPAL_ID and r["metodo_pagamento"] == "PayPal"
    assert r["id_ricevuta"] == "TESTRIC01" and r["id_operazione"] == "9999999"
    assert r["identificativo_riscossione"] == "abcdef0123456789abcdef0123456789"


def test_mooney_con_importi_che_non_tornano_non_e_un_pagamento():
    """Una lettura dell'immagine con una cifra sbagliata non diventa un pagamento."""
    r = _parse_mooney_payment(_mooney(totale="7,83"))

    assert r["importi_quadrano"] is False
    assert r["is_payment_receipt"] is False


def test_un_testo_qualunque_non_e_una_ricevuta_mooney():
    assert _parse_mooney_payment("Ricevuta per l'utente di un altro servizio") == {}


def _attestazione(*, righe_documenti, totale_riga, documenti_dettaglio=""):
    return (
        " \nRicevuta di pagamento\nIntestata a: AZIENDA TEST SRL\nCodice fiscale: 00000000000\n"
        "Data/ora: 15/03/2025 09:30:00\nAgente della Riscossione: Agenzia delle Entrate-Riscossione\n"
        "Cod. Fisc. Agente Risc.: 13756881002\nIdentificativo PSP: TESTITMM - Banca Prova\n"
        f"Dettaglio transazione\nIUV¹: {IUV_B}\n{righe_documenti}{totale_riga}\n"
        "Transazione eseguita\nIl pagamento è stato registrato correttamente.\n"
        f"{documenti_dettaglio}"
    )


TESTO_SINGOLA = _attestazione(
    righe_documenti=(
        "Cartella/Avviso n.: 00000000000000000001\nEnte creditore: ENTE UNO\n"
        "Importo tributi: €\t\t\t100.00\nInteressi di mora: €\t\t\t2.50\nDiritti di notifica: €\t\t\t5.88\n"
    ),
    totale_riga="Totale Cartella/Avviso: €\t\t\t108.38",
)

TESTO_DIRITTI = _attestazione(
    righe_documenti=(
        "Documento: 00000000000000000002 €\t\t\t5.88\nDocumento: 00000000000000000003 €\t\t\t0.05\n"
    ),
    totale_riga="Totale pagamento: €\t\t\t5.93",
    documenti_dettaglio=(
        "Dettaglio documento n.\nIUV¹: " + IUV_B + "\nCartella/Avviso n.: 00000000000000000002\n"
        "Ente creditore: ENTE DUE\nDiritti di notifica: €\t\t\t5.88\nTotale pagato: €\t\t\t5.88\n"
        "Dettaglio documento n.\nIUV¹: " + IUV_B + "\nCartella/Avviso n.: 00000000000000000003\n"
        "Ente creditore: ENTE TRE\nDiritti di notifica: €\t\t\t0.05\nTotale pagato: €\t\t\t0.05\n"
    ),
)


def test_attestazione_di_una_cartella_legge_ogni_voce_e_quadra():
    r = _parse_ader_attestazione(TESTO_SINGOLA)

    assert r["is_payment_receipt"] is True and r["importi_quadrano"] is True
    assert r["identificativo_bolletta"] == IUV_B and r["data_pagamento"] == "2025-03-15"
    assert r["operation_amount"] == 108.38
    assert (r["importo_tributi"], r["interessi_mora"], r["diritti_notifica"]) == (100.0, 2.5, 5.88)
    assert r["cartella_number"] == "00000000000000000001"
    assert (r["psp_bic"], r["psp_nome"]) == ("TESTITMM", "Banca Prova")
    # Tributi e diritti insieme: la natura non si decide, resta da dire.
    assert r["natura"] is None


def test_attestazione_di_soli_diritti_di_notifica_dice_da_sola_la_natura():
    r = _parse_ader_attestazione(TESTO_DIRITTI)

    assert r["is_payment_receipt"] is True
    assert len(r["documenti"]) == 2 and r["operation_amount"] == 5.93
    assert (r["natura"], r["natura_fonte"]) == ("onere_pratica", "documento")


def test_una_voce_nuova_che_non_torna_col_totale_lascia_il_pagamento_da_verificare():
    testo = TESTO_SINGOLA.replace("Diritti di notifica: €\t\t\t5.88\n",
                                  "Diritti di notifica: €\t\t\t5.88\nSpese esecutive: €\t\t\t9.99\n")

    r = _parse_ader_attestazione(testo)

    assert r["importi_quadrano"] is False and r["is_payment_receipt"] is False


def test_importo_originario_della_cartella_non_e_una_voce_di_pagamento():
    testo = _attestazione(
        righe_documenti="Documento: 00000000000000000004 €\t\t\t46.94\n",
        totale_riga="Totale pagamento: €\t\t\t46.94",
        documenti_dettaglio=(
            "Dettaglio documento n.\nIUV¹: " + IUV_B + "\nCodice documento: " + IUV_B + "\n"
            "Importo originario: €\t\t\t46.94\nCartella/Avviso n.: 00000000000000000004\n"
            "Ente creditore: ENTE QUATTRO\nImporto tributi: €\t\t\t41.06\n"
            "Diritti di notifica: €\t\t\t5.88\nTotale Cartella/Avviso: €\t\t\t46.94\n"
        ),
    )

    r = _parse_ader_attestazione(testo)

    assert r["is_payment_receipt"] is True and r["importi_quadrano"] is True
    assert (r["importo_tributi"], r["diritti_notifica"]) == (41.06, 5.88)


def _pdf(*righe: str) -> bytes:
    doc = fitz.open()
    pagina = doc.new_page()
    y = 40
    for riga in righe:
        # I font PDF di base non includono il simbolo euro: ``EUR`` mantiene
        # il significato della fixture ed evita font esterni dipendenti dal SO.
        pagina.insert_text((30, y), riga.replace("€", "EUR"), fontsize=9, fontname="helv")
        y += 14
    contenuto = doc.tobytes()
    doc.close()
    return contenuto


def test_documenti_import_riconosce_attestazione_e_mooney():
    attestazione = _pdf(*[r for r in TESTO_SINGOLA.replace("\t", " ").splitlines() if r.strip()])
    mooney = _pdf("RICEVUTA PER L'UTENTE", "Servizio erogato da Mooney S.p.A. Albo IMEL",
                  "Importo: 5,88", "Totale: 7,38")

    assert detect_document_type("attestazione_pagamento.pdf", attestazione) == "ricevuta_pagopa"
    assert detect_document_type("ricevuta.pdf", mooney) == "ricevuta_pagopa"


def test_import_attestazione_salva_i_campi_e_il_secondo_file_dello_stesso_pagamento_non_duplica():
    db = ClientArchivioMemoria()["ader-import"]
    righe = [r for r in TESTO_DIRITTI.replace("\t", " ").splitlines() if r.strip()]

    primo = asyncio.run(import_receipt(db, content=_pdf(*righe), filename="a.pdf", company_id="c"))
    # Altro file (byte diversi) dello stesso pagamento: stesso IUV, importo e giorno.
    secondo = asyncio.run(import_receipt(db, content=_pdf(*righe, "copia"), filename="b.pdf", company_id="c"))

    assert primo["success"] is True and primo["duplicate"] is False
    ricevuta = primo["receipt"]
    assert ricevuta["identificativo_bolletta"] == IUV_B and ricevuta["importo"] == 5.93
    assert ricevuta["natura"] == "onere_pratica" and ricevuta["natura_label"] == "Diritti o oneri di una pratica"
    assert ricevuta["beneficiario"] == "ADER" and ricevuta["psp_nome"] == "Banca Prova"
    assert secondo["duplicate"] is True and secondo["duplicate_motivo"] == "stesso_iuv_importo_data"
    assert asyncio.run(db["ricevute_pagopa"].count_documents({})) == 1


@pytest.fixture
def mooney_letto(monkeypatch):
    """Il PDF Mooney ha solo il riquadro degli importi come testo: le righe vere
    le dara' l'OCR, qui sostituito con quelle inventate."""
    monkeypatch.setattr(modulo, "_righe_ocr_per_posizione", lambda _contenuto: _mooney())
    return _pdf("RICEVUTA PER L'UTENTE", "Servizio erogato da Mooney S.p.A. Albo IMEL",
                "Importo: 5,88", "Diritti: 1,50", "Totale: 7,38", "ID Ricevuta: TESTRIC01")


def test_ricevuta_mooney_attende_il_pagamento_paypal_e_lo_trova_quando_arriva(mooney_letto):
    db = ClientArchivioMemoria()["mooney-paypal"]

    esito = asyncio.run(import_receipt(db, content=mooney_letto, filename="m.pdf", company_id="c"))
    ricevuta = esito["receipt"]

    assert esito["success"] is True
    assert ricevuta["paypal_transaction_id"] == PAYPAL_ID and ricevuta["intermediario"] == "Mooney"
    assert ricevuta.get("paypal_collegato") is not True

    # Il PayPal non e' ancora in archivio: si attende, senza inventare.
    assert asyncio.run(ricollega_ricevute_paypal(db)) == {"in_attesa": 1, "collegate": 0}

    asyncio.run(db["paypal_transactions"].insert_one({
        "transaction_id": PAYPAL_ID, "importo": -7.38, "lordo": -7.38, "data": "2026-09-01",
        "movimento_banca_id": "EC-1",
    }))
    asyncio.run(db["estratto_conto_movimenti"].insert_one({
        "id": "EC-1", "importo": 7.38, "data": "2026-09-03", "evidenza_bancaria_ufficiale": True,
    }))
    assert asyncio.run(ricollega_ricevute_paypal(db)) == {"in_attesa": 1, "collegate": 1}

    salvata = asyncio.run(db["ricevute_pagopa"].find_one({"id": ricevuta["id"]}, {"_id": 0}))
    assert salvata["paypal_collegato"] is True and salvata["movimento_id"] == "EC-1"
    assert salvata["banca_verificata"] is True
    transazione = asyncio.run(db["paypal_transactions"].find_one({"transaction_id": PAYPAL_ID}, {"_id": 0}))
    # Non e' il pagamento di una fattura: fuori dall'abbinamento per importo.
    assert transazione["is_pagopa"] is True and transazione["ricevuta_pagopa_id"] == ricevuta["id"]
    assert asyncio.run(ricollega_ricevute_paypal(db)) == {"in_attesa": 0, "collegate": 0}


def test_paypal_con_importo_diverso_o_movimento_non_ufficiale_non_si_aggancia(mooney_letto):
    db = ClientArchivioMemoria()["mooney-paypal-no"]
    ricevuta = asyncio.run(import_receipt(db, content=mooney_letto, filename="m.pdf", company_id="c"))["receipt"]

    asyncio.run(db["paypal_transactions"].insert_one({
        "transaction_id": PAYPAL_ID, "importo": -7.39, "lordo": -7.39, "data": "2026-09-01"}))
    assert asyncio.run(collega_ricevuta_a_paypal(db, ricevuta)) == {
        "collegata": False, "motivo": "importo_paypal_diverso"}

    asyncio.run(db["paypal_transactions"].update_one(
        {"transaction_id": PAYPAL_ID},
        {"$set": {"importo": -7.38, "lordo": -7.38, "movimento_banca_id": "EC-2"}}))
    asyncio.run(db["estratto_conto_movimenti"].insert_one({
        "id": "EC-2", "importo": 7.38, "data": "2026-09-03", "evidenza_bancaria_ufficiale": False}))
    esito = asyncio.run(collega_ricevuta_a_paypal(db, ricevuta))

    assert esito["collegata"] is True and esito["banca"] is False
