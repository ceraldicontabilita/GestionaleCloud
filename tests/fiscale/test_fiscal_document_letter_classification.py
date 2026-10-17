"""Synthetic regressions: letters retain their nature, never legal effects."""
import pytest

from app.services.fiscal_domain import PAYMENT_EVIDENCE_TYPES, classify_document


@pytest.mark.parametrize(("text", "expected"), [
    ("Istanza di sgravio presentata per cartella di pagamento", "ISTANZA_SGRAVIO"),
    ("Rigetto della richiesta di sgravio per cartella di pagamento", "RIGETTO_SGRAVIO"),
    ("Preavviso di rigetto della richiesta di sgravio", "PREAVVISO_RIGETTO"),
    ("Richiesta di sospensione legale della riscossione presentata", "ISTANZA_SOSPENSIONE"),
    ("Dichiarazione SL1. Sospensione legale della riscossione", "ISTANZA_SOSPENSIONE"),
    ("Diniego della sospensione per la cartella di pagamento", "RIGETTO_SOSPENSIONE"),
    ("Domanda di rateizzazione cartella di pagamento", "ISTANZA_RATEIZZAZIONE"),
    ("Rigetto della domanda di rateizzazione", "RIGETTO_RATEIZZAZIONE"),
    ("Provvedimento di sgravio parziale della cartella di pagamento", "SGRAVIO"),
    ("Provvedimento di sospensione della cartella di pagamento", "SOSPENSIONE"),
    ("Relata di notifica della cartella di pagamento", "RELATA_NOTIFICA"),
    ("Sollecito di pagamento relativo alla cartella di pagamento", "SOLLECITO_PAGAMENTO"),
    ("INPS Nota di rettifica DMRA per periodo contributivo", "NOTA_RETTIFICA_INPS"),
    ("Documento unico di regolarità contributiva DURC", "DURC"),
    ("CIVIS esito della richiesta di assistenza", "COMUNICAZIONE_CIVIS"),
])
def test_lettere_non_diventano_cartelle_o_provvedimenti(text, expected):
    result = classify_document("documento.pdf", "Agenzia Entrate Riscossione. " + text)
    assert result["document_type"] == expected
    assert result["requires_review"] is True
    assert result["document_type"] not in PAYMENT_EVIDENCE_TYPES


@pytest.mark.parametrize(("text", "expected"), [
    ("Piano di ammortamento accolto relativo alla cartella di pagamento", "PIANO_RATEIZZAZIONE"),
    ("Attestazione di pagamento eseguito della cartella di pagamento", "RICEVUTA_PAGOPA"),
    ("Attestazione di pagamento non eseguito per cartella di pagamento", "ESITO_NEGATIVO_PAGOPA"),
    ("Cartella di pagamento. Importi originariamente indicati nel modello F24", "CARTELLA_ADE_R"),
])
def test_emittente_e_atto_citato_non_prevalgono_sulla_natura(text, expected):
    assert classify_document("documento.pdf", "Agenzia Entrate Riscossione. " + text)["document_type"] == expected


def test_emittente_da_solo_non_identifica_una_cartella():
    result = classify_document("documento.pdf", "Agenzia Entrate Riscossione. Richiesta di informazioni")
    assert result["document_type"] == "CORRISPONDENZA_ADE_R"
    assert result["requires_review"] is True


@pytest.mark.parametrize("filename", ["sgravio.pdf", "provvedimento di sgravio.pdf", "sospensione.pdf"])
def test_nome_file_non_prova_provvedimento(filename):
    result = classify_document(filename)
    assert result["document_type"] == "ALTRO_FISCALE"
    assert result["requires_review"] is True


def test_nome_sgravio_non_prevale_sul_contenuto_bancario():
    result = classify_document("sgravio.pdf", "Ricevuta bonifico eseguito. Causale differenza verbale")
    assert result["document_type"] == "MOVIMENTO_BANCARIO_DOCUMENTO"
    assert result["document_type"] not in PAYMENT_EVIDENCE_TYPES


def test_richiesta_con_provvedimento_ancora_atteso_resta_richiesta():
    result = classify_document("lettera.pdf", "Istanza di sgravio. Si attende il provvedimento di sgravio")
    assert result["document_type"] == "ISTANZA_SGRAVIO"
    assert result["requires_review"] is True


def test_testo_prevale_sul_nome_file_contraddittorio():
    result = classify_document("cartella di pagamento.pdf", "Modello F24 da presentare")
    assert result["document_type"] == "F24"


def test_modello_non_diventa_quietanza_dal_nome_file():
    result = classify_document("quietanza F24.pdf", "Modello F24 da presentare")
    assert result["document_type"] == "F24"


@pytest.mark.parametrize(("text", "expected"), [
    ("Ricevuta trasmissione UniEmens. Protocollo telematico 1234", "RICEVUTA_TRASMISSIONE"),
    ("Esito delega F24. Scartata. Versamento non eseguito. Protocollo telematico 1234", "ESITO_NEGATIVO_F24"),
    ("Si richiede di produrre il provvedimento di sgravio per la cartella di pagamento", "CORRISPONDENZA_ADE_R"),
    ("Il provvedimento di sgravio non è stato emesso. L'istanza resta in istruttoria", "CORRISPONDENZA_ADE_R"),
    ("Accoglimento della domanda di rateizzazione. In caso di decadenza si procederà a revoca del piano di rateizzazione", "PIANO_RATEIZZAZIONE"),
    ("Con riferimento alla domanda di rateizzazione, il piano di ammortamento è accolto", "PIANO_RATEIZZAZIONE"),
])
def test_esiti_e_citazioni_non_creano_prove_positive(text, expected):
    result = classify_document("lettera.pdf", text)
    assert result["document_type"] == expected
    assert result["requires_review"] is True
    assert result["document_type"] not in PAYMENT_EVIDENCE_TYPES


def test_protocollo_telematico_generico_non_prova_un_f24():
    result = classify_document("ricevuta.pdf", "Ricevuta invio dichiarazione. Protocollo telematico 1234")
    assert result["document_type"] not in PAYMENT_EVIDENCE_TYPES


def test_avviso_cita_ricevuta_futura():
    result = classify_document("avviso.pdf", "Avviso di pagamento. Conservare attestazione di pagamento dopo versamento")
    assert result["document_type"] == "AVVISO_PAGOPA"


@pytest.mark.parametrize(("text", "expected"), [
    ("Ricevuta di avvenuta consegna. Il messaggio con oggetto quietanza F24 è stato consegnato", "RICEVUTA_PEC"),
    ("Ricevuta di accettazione. Oggetto: provvedimento di sgravio", "RICEVUTA_PEC"),
    ("Dettaglio avviso. I dati corrispondono a quelli dei sistemi informatici di Agenzia Entrate Riscossione. Legenda: con provvedimento di sgravio", "PROSPETTO_ADE_R"),
    ("Carico affidato. Residuo carico 0,00. Legenda: sgravio con provvedimento di sgravio", "PROSPETTO_ADE_R"),
    ("Modello F24. Istruzioni quietanza F24 da esibire a richiesta", "F24"),
    ("Mod. SL1 SOSPENSIONE LEGALE DELLA RISCOSSIONE. Provvedimento di sgravio da allegare", "ISTANZA_SOSPENSIONE"),
    ("Oggetto: Modulo di pagamento per le rate dell'istanza di rateizzazione già approvata", "MODULO_PAGAMENTO"),
    ("Cartella di pagamento N. 012 2026 12345678 pagina 1 di 11. Istruzioni: richiedere provvedimento di sgravio", "CARTELLA_ADE_R"),
    ("Comunicazione di sgravio. L'ufficio ha disposto lo sgravio parziale. Residuo dovuto", "SGRAVIO"),
    ("Esito delega F24. Stato: in attesa", "RICEVUTA_TRASMISSIONE"),
    ("Tipo documento F24A0. Ricevuta del controllo formale. Protocollo telematico", "RICEVUTA_TRASMISSIONE"),
    ("Esito delega F24. Accolta dal controllo formale. Protocollo telematico", "RICEVUTA_TRASMISSIONE"),
    ("Accoglimento della richiesta di rateazione. Piano approvato", "PIANO_RATEIZZAZIONE"),
    ("CHIEDE che venga inserito il provvedimento di sospensione della cartella", "CORRISPONDENZA_ADE_R"),
])
def test_documenti_citazioni_e_legende_non_diventano_allegati_o_provvedimenti(text, expected):
    result = classify_document("documento.pdf", text)
    assert result["document_type"] == expected
    assert result["requires_review"] is True
    assert result["document_type"] not in PAYMENT_EVIDENCE_TYPES


def test_quietanza_positiva_non_esige_presenza_di_documento_bancario():
    result = classify_document("documento.pdf", "Quietanza F24. Tipo documento I24A0. Esito addebito positivo")
    assert result["document_type"] == "QUIETANZA_F24"
    assert result["document_type"] in PAYMENT_EVIDENCE_TYPES
    assert result["requires_review"] is False


def test_causale_dmra_sul_modello_non_lo_trasforma_in_nota_rettifica():
    assert classify_document("documento.pdf", "Modello F24. Sezione INPS, causale DMRA")["document_type"] == "F24"


def test_richiesta_di_acquisire_quietanza_non_e_una_quietanza():
    result = classify_document("lettera.pdf", "Oggetto: Richiesta di acquisizione quietanza F24. Il modello non risulta ancora pagato.")
    assert result["document_type"] == "ALTRO_FISCALE"
    assert result["requires_review"] is True
    assert result["document_type"] not in PAYMENT_EVIDENCE_TYPES
