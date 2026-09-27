"""Il riferimento Banco BPM a segmenti identifica il bonifico, non la giornata.

Ricevute del 02/04/2026: «RIF. OPERAZIONE BAPPIT222026-04-0290553560». Il
lettore si fermava al primo trattino e tutti i bonifici del giorno avevano lo
stesso «CRO»: sette stipendi da 1.000 EUR sarebbero diventati uno solo.
"""
from app.routers.bonifici_module.pdf_parser import extract_transfers_from_text


def _ricevuta(rif_operazione: str, beneficiario: str) -> str:
    return (
        "BONIFICO\nRICEVUTA PER ORDINANTE\nDATA\n02/04/2026\nRIF. INTERNO\nMB0B39331321\n"
        f"RIF. OPERAZIONE\n{rif_operazione}\nCERALDI GROUP S.R.L.\n"
        f"REGISTRIAMO A VOSTRO DEBITO A FAVORE DI:\n{beneficiario}\n"
        "IBAN BENEFICIARIO\nIT62Q0306903487100000006597\nIMPORTO\nEUR 1.000,00\n"
    )


def test_il_riferimento_bpm_a_segmenti_resta_intero():
    a = extract_transfers_from_text(_ricevuta("BAPPIT222026-04-0290553560", "GUARINO GIULIANO"))[0]
    b = extract_transfers_from_text(_ricevuta("BAPPIT222026-04-0290553624", "MOSCATO EMANUELE"))[0]
    assert a["cro_trn"] == "BAPPIT222026-04-0290553560"
    assert b["cro_trn"] == "BAPPIT222026-04-0290553624"
    assert a["cro_trn"] != b["cro_trn"]


def test_gli_altri_riferimenti_non_cambiano():
    """Un CRO numerico gia' archiviato deve restare identico, o la copia nuova
    dello stesso bonifico non verrebbe riconosciuta come doppione."""
    testo = _ricevuta("260120100283216-480340403400IT05387", "CERALDI GROUP S.R.L.")
    assert extract_transfers_from_text(testo)[0]["cro_trn"] == "260120100283216"


def test_il_rif_interno_si_legge_accanto_al_cro():
    """Ricevuta BPM del 05/12/2024: il CRO resta il TRN (chiave dei doppioni
    gia' archiviati), il RIF. INTERNO e' quello che l'estratto conto ripete."""
    testo = (
        "BONIFICO RICEVUTA PER ORDINANTE\nDATA 05/12/2024\nRIF. INTERNO MB0B96218506\n"
        "RIF. OPERAZIONE 5034905662434340480340003400IT\n"
        "REGISTRIAMO A VOSTRO DEBITO A FAVORE DI: ROSSI MARIO\n"
        "IBAN BENEFICIARIO IT32T0100503400000000004198\nIMPORTO EUR 800,00\n"
        "CAUSALE Rossi Mario acc stip 2024\n"
        "VS.DISP. RIF. MB0B96218506/90566244 NS RIF. MB0B96218506 SPESE E CO\n"
    )
    bonifico = extract_transfers_from_text(testo)[0]
    assert bonifico["cro_trn"] == "5034905662434340480340003400IT"
    assert bonifico["rif_interno"] == "MB0B96218506"


def test_rif_interno_con_le_etichette_in_fila():
    """Ricevuta del 05/05/2023: le due etichette stampate una sotto l'altra e
    i valori dopo. Vale il «NS RIF.» della riga contabile, che e' lo stesso."""
    testo = (
        "05/05/2023 DATA\n\nRIF. INTERNO\n\nRIF. OPERAZIONE\n\nMB0B92220730\n\n"
        "5034904893533125480340003400IT\n\nREGISTRIAMO A VOSTRO DEBITO A FAVORE DI:\n"
        "IMPORTO\nEUR 132,58 05/05/2023\n"
        "VS.DISP. RIF. MB0B92220730/90489354 -05/05/2023 NS RIF. MB0B92220730 SPESE E CO -\n"
    )
    assert extract_transfers_from_text(testo)[0]["rif_interno"] == "MB0B92220730"


def test_ricevuta_senza_rif_interno_resta_vuota():
    testo = _ricevuta("260120100283216-480340403400IT05387", "CERALDI GROUP S.R.L.").replace(
        "RIF. INTERNO\nMB0B39331321\n", "")
    assert extract_transfers_from_text(testo)[0]["rif_interno"] is None
