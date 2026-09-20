"""L'archivio `legacy_staging` non alimenta piu' i registri vivi.

Uno scheduler ogni 6 ore ripescava dallo schema `legacy_staging` (56 tabelle,
197 MB su 2.111 di database, con il compute Supabase gia' al limite) e ne
riversava il contenuto nei registri vivi. La sua descrizione diceva
«fatture/chiusure 2024-25»: **falso**, il codice riversava soltanto versamenti,
presenze/acconti HR e ordini Lotti. Nessuna fattura, da nessuna parte.

I versamenti ora li riconosce `services/versamenti_contanti.py` direttamente
dall'estratto conto, che e' la fonte vera: il ponte legacy non serve piu'.

Quello che il legacy ha gia' portato **resta** dov'e': 786 fatture, 180
fornitori su 188, 1.857 movimenti bancari su 2.017 e 27.383 transazioni POS
portano un marcatore `legacy_*`. Quel marcatore e' la **provenienza** del dato,
non un doppione: cancellarlo cancellerebbe la contabilita' 2026.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_il_modulo_di_integrazione_non_esiste_piu():
    assert not (ROOT / "app/services/integrazione_legacy.py").exists()


def test_nessun_codice_legge_piu_lo_schema_legacy():
    colpevoli = []
    for sorgente in (ROOT / "app").rglob("*.py"):
        testo = sorgente.read_text(encoding="utf-8")
        if "legacy_staging" in testo or "integra_legacy" in testo:
            colpevoli.append(str(sorgente.relative_to(ROOT)))
    assert colpevoli == [], colpevoli


def test_lo_scheduler_non_ha_piu_il_giro_legacy():
    sorgente = (ROOT / "app/scheduler.py").read_text(encoding="utf-8")
    assert "integrazione_legacy" not in sorgente
    assert "_integrazione_legacy_job" not in sorgente


def test_i_marcatori_di_provenienza_restano_sui_dati():
    """Nessuna cancellazione di massa per marcatore: e' la provenienza.

    Se un giorno qualcuno scrivesse una cancellazione filtrata su
    `legacy_row_hash` o `legacy_source_table`, toglierebbe 180 fornitori su
    188 e 786 fatture su 1.457. Questa guardia lo impedisce.
    """
    sospette = []
    for sorgente in (ROOT / "app").rglob("*.py"):
        for riga in sorgente.read_text(encoding="utf-8").splitlines():
            if re.search(r"delete_(one|many)\(.*legacy_(row_hash|source)", riga):
                sospette.append(f"{sorgente.relative_to(ROOT)}: {riga.strip()}")
    assert sospette == [], sospette
