"""Identita' documentale del cedolino: il PDF, non soltanto dipendente e mese.

Lo scrittore unico e' `salari_unificati_v2.processa_cedolino_v2`; il vecchio
`cedolini_manager.processa_cedolino_completo`, usato solo come ripiego, e'
stato tolto insieme agli altri motori paralleli.
"""
import base64


def _data(netto, tipo="mensile"):
    return {
        "codice_fiscale": "RSSMRA80A01H501U",
        "nome_dipendente": "Rossi Mario",
        # Usa un mese gia' maturato nel periodo contabile operativo. Dicembre
        # 2026 e' futuro rispetto alla data del collaudo e deve correttamente
        # restare fuori dalla Prima Nota Salari.
        "mese": 6,
        "anno": 2026,
        "netto_mese": netto,
        "lordo": netto + 500,
        "tipo_cedolino": tipo,
    }


def test_v2_usa_hash_pdf_e_fallback_legacy_esatto():
    from app.services.salari_unificati_v2 import (
        _cedolino_document_key,
        _cedolino_identity_filter,
    )

    data = _data(1500)
    pdf_a = base64.b64encode(b"%PDF-1.4 A").decode()
    pdf_b = base64.b64encode(b"%PDF-1.4 B").decode()
    key_a = _cedolino_document_key(data, pdf_a)
    key_b = _cedolino_document_key(data, pdf_b)
    assert key_a != key_b

    filtro = _cedolino_identity_filter(
        data["codice_fiscale"], 12, 2026, "mensile",
        key_a, "mensile.pdf", 1500, 2000,
    )
    assert filtro["$or"][0] == {"cedolino_dedup_key": key_a}
    legacy = filtro["$or"][1]
    assert legacy["cedolino_dedup_key"] == {"$exists": False}
    assert legacy["filename"] == "mensile.pdf"
    assert legacy["netto"] == 1500
