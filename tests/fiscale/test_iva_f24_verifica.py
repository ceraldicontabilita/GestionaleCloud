from datetime import date

from app.services.iva_f24_verifica import (
    scadenza_iva_mensile,
    verifica_versamento_iva_da_documenti,
)


def _doc(**extra):
    return {
        "id": "f24-iva-giugno",
        "file_name": "F24 IVA giugno.pdf",
        "sezione_erario": [
            {
                "codice_tributo": "6006",
                "anno_riferimento": "2026",
                "importo_debito": 1000.0,
            }
        ],
        "totali": {"saldo_netto": 1000.0},
        **extra,
    }


def test_iva_f24_quietanza_senza_banca_prova_versamento_documentale():
    esito = verifica_versamento_iva_da_documenti(
        anno=2026,
        mese=6,
        f24_docs=[_doc(quietanza_id="q1", data_pagamento_quietanza="2026-07-16")],
        debito_liquidazione=1000.0,
        oggi=date(2026, 7, 20),
    )
    assert esito["pagato_banca"] is False
    assert esito["versato_documentalmente"] is True
    assert esito["data_versamento_documentale"] == "2026-07-16"
    assert esito["stato"] == "QUIETANZA_PRESENTE_DA_VERIFICARE_BANCA"
    assert esito["ravvedimento"]["necessario"] is False
    assert esito["ravvedimento"]["codice_sanzione"] == "8904"
    assert esito["ravvedimento"]["codice_interessi"] == "1991"


def test_iva_f24_con_movimento_banca_e_pagato():
    esito = verifica_versamento_iva_da_documenti(
        anno=2026,
        mese=6,
        f24_docs=[_doc(
            movimento_bancario_id="mov-1",
            data_pagamento_effettivo="2026-07-16",
        )],
        debito_liquidazione=1000.0,
        oggi=date(2026, 7, 20),
    )
    assert esito["pagato_banca"] is True
    assert esito["stato"] == "PAGATO_BANCA"
    assert esito["ravvedimento"]["necessario"] is False
    assert esito["scostamento_f24_liquidazione"] == 0


def test_iva_quietanza_tardiva_calcola_ravvedimento_sulla_data_documentale():
    esito = verifica_versamento_iva_da_documenti(
        anno=2026,
        mese=6,
        f24_docs=[_doc(quietanza_id="q-late", data_pagamento_quietanza="2026-07-21")],
        oggi=date(2026, 7, 22),
    )
    assert esito["versato_documentalmente"] is True
    assert esito["pagato_banca"] is False
    assert esito["scaduto"] is False
    assert esito["ravvedimento"]["necessario"] is True


def test_iva_f24_anno_diverso_non_viene_collegato():
    esito = verifica_versamento_iva_da_documenti(
        anno=2026,
        mese=6,
        f24_docs=[_doc(sezione_erario=[{
            "codice_tributo": "6006",
            "anno_riferimento": "2025",
            "importo_debito": 1000.0,
        }])],
        oggi=date(2026, 7, 20),
    )
    assert esito["stato"] == "F24_NON_TROVATO"


def test_iva_luglio_scade_il_20_agosto():
    assert scadenza_iva_mensile(2026, 7).isoformat() == "2026-08-20"


def test_codice_ravvedimento_non_iva_non_etichetta_iva():
    doc = _doc()
    doc["sezione_erario"].append({
        "codice_tributo": "8906",
        "anno_riferimento": "2026",
        "importo_debito": 12.0,
    })
    esito = verifica_versamento_iva_da_documenti(
        anno=2026, mese=6, f24_docs=[doc], oggi=date(2026, 7, 1),
    )
    assert esito["f24"]["ravvedimento"] is False
