"""Il percorso Document AI dei cedolini deve esistere davvero.

Regressione: entrambi i `cedolini_manager` importavano `extract_document_data`,
una funzione mai definita in nessuno dei due moduli. L'ImportError finiva in un
`except Exception` che degradava al parser regex, quindi la "prima scelta"
annunciata dal codice non e' mai stata eseguita e nessuno se n'e' accorto.

Il ramo HR era inoltre un fork divergente del motore ERP: chiamava LlmChat e
UserMessage con nomi di parametro inesistenti e troncava il testo a 15.000
caratteri. Ora `app.hr.services.document_ai_extractor` re-esporta il motore
unico di `app.services`.
"""
import inspect

import pytest

from app.hr.services import document_ai_extractor as hr_extractor
from app.services import document_ai_extractor as erp_extractor


def test_hr_reesporta_il_motore_erp():
    """Un solo motore per funzione: HR non tiene una seconda implementazione."""
    assert hr_extractor.process_document is erp_extractor.process_document
    assert hr_extractor.extract_structured_data is erp_extractor.extract_structured_data


@pytest.mark.parametrize("modulo", [hr_extractor, erp_extractor])
def test_process_document_accetta_i_kwargs_dei_chiamanti(modulo):
    """I cedolini_manager chiamano con questi nomi esatti: devono combaciare."""
    parametri = inspect.signature(modulo.process_document).parameters
    for atteso in ("file_data", "filename", "document_type"):
        assert atteso in parametri, f"{atteso} mancante in process_document"


@pytest.mark.parametrize(
    "sorgente",
    ["app/hr/services/cedolini_manager.py", "app/services/cedolini_manager.py"],
)
def test_nessun_riferimento_alla_funzione_inesistente(sorgente):
    testo = open(sorgente, encoding="utf-8").read()
    assert "extract_document_data" not in testo


def test_lo_stub_con_modello_ritirato_non_torna():
    """emergent_stub cablava un modello ritirato e duplicava anthropic_llm_client."""
    with pytest.raises(ImportError):
        __import__("app.hr.services.emergent_stub")


def test_il_testo_non_viene_troncato_a_15k():
    """Il limite 15k tagliava PDF multipagina ed estratti conto (bug segnalato)."""
    sorgente = inspect.getsource(erp_extractor.extract_structured_data)
    assert "text[:15000]" not in sorgente
    assert "text[:150000]" in sorgente
