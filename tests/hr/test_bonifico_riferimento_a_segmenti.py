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
