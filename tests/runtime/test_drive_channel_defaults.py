"""I canali Drive per sezione sono smontati (DRV-16): i documenti entrano
solo dalla cartella unica. Nessuna variabile per sezione deve tornare in
config.py, o un canale si riaccenderebbe su una cartella che non c'e' piu'."""
import re

from app.config import Settings

_PER_SEZIONE = re.compile(
    r"^(ENABLE_DRIVE_.+_SYNC|DRIVE_.+_BATCH_SIZE|GOOGLE_SERVICE_ACCOUNT_JSON_.+"
    r"|GOOGLE_DRIVE_(FATTURE|CEDOLINI|CORRISPETTIVI|QUIETANZE|ESTRATTI|BONIFICI"
    r"|DICHIARAZIONI_IVA|DICHIARAZIONI_FISCALI|CARTELLE_ESATTORIALI|AVVISI_BONARI)_FOLDER_IDS?"
    r"|DRIVE_(CARTE|F24|PAYPAL|NOLEGGIO|VERBALI|PRESENZE)_FOLDER_ID"
    r"|DRIVE_FOLDER_REGISTRY_JSON|DRIVE_FISCAL_ROOT_FOLDER_ID|DRIVE_ESTRATTI_ANNO_MINIMO)$"
)


def test_nessuna_variabile_dei_canali_per_sezione():
    rimaste = sorted(nome for nome in Settings.model_fields if _PER_SEZIONE.match(nome))
    assert not rimaste, rimaste
