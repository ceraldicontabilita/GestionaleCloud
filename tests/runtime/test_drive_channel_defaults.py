"""Le variabili ENABLE_DRIVE_*_SYNC sono state tolte da Render il 27/09/2026:
i default di config.py sono la configurazione di produzione e non devono
riaccendere per sbaglio i canali Drive per sezione smontati."""
from app.config import Settings


def test_canali_drive_per_sezione_spenti_di_default(monkeypatch):
    spenti = (
        "FATTURE", "CEDOLINI", "CORRISPETTIVI", "QUIETANZE", "ESTRATTI_CONTO",
        "BONIFICI", "DICHIARAZIONI_IVA", "CARTELLE_ESATTORIALI",
        "AVVISI_BONARI", "VERBALI",
    )
    for nome in (*spenti, "DICHIARAZIONI_FISCALI"):
        monkeypatch.delenv(f"ENABLE_DRIVE_{nome}_SYNC", raising=False)
    fields = Settings.model_fields
    for nome in spenti:
        assert fields[f"ENABLE_DRIVE_{nome}_SYNC"].default is False, nome
    assert fields["ENABLE_DRIVE_DICHIARAZIONI_FISCALI_SYNC"].default is True
