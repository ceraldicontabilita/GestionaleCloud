"""Fase 0 (PROMPT_CLAUDE_CODE_FASE_0.md punto 9): il ramo F24 per solo
importo (±0,05€ senza data) e il ramo POS-cassa legacy a tolleranza (±1€) del
motore A devono essere disattivati; il ramo NUMIA (riconcilia_accredito_pos_ec)
resta attivo, non va toccato.

`riconcilia_movimenti_banca` e' una funzione monolitica con molte query DB
concatenate (fatture, fornitori, assegni, evento bus...): riprodurne
l'ambiente con un fake minimale sarebbe fragile e rischierebbe di far
sembrare "provato" un comportamento in realta' non esercitato. La prova qui
e' sulla condizione effettiva eseguita dal Python: importa il sorgente e
verifica che il flag di disattivazione sia cablato esattamente sui due rami
citati dall'audit, e non sul ramo NUMIA.
"""
import inspect

from app.services import riconciliazione_bancaria as mod


def test_fase0_disattivato_e_true():
    assert mod.FASE0_DISATTIVATO is True


def test_ramo_f24_per_solo_importo_e_disattivato():
    sorgente = inspect.getsource(mod)
    assert (
        'if not FASE0_DISATTIVATO and tipo == "uscita" and not match_found '
        'and "F24" in descrizione.upper():'
    ) in sorgente


def test_ramo_pos_legacy_a_tolleranza_e_disattivato():
    sorgente = inspect.getsource(mod)
    assert (
        "if not FASE0_DISATTIVATO and any(kw in desc_upper for kw in "
        "['POS', 'NEXI', 'SUMUP', 'CARTE', 'BANCOMAT']):"
    ) in sorgente


def test_ramo_numia_pos_ec_resta_attivo_senza_guardia_fase0():
    sorgente = inspect.getsource(mod)
    idx = sorgente.index("_e_accredito_pos_numia_con_giorno(descrizione)")
    # La riga che invoca il controllo NUMIA non deve contenere la guardia
    # FASE0_DISATTIVATO: e' l'unico ramo POS che deve restare operativo.
    inizio_riga = sorgente.rfind("\n", 0, idx) + 1
    fine_riga = sorgente.index("\n", idx)
    riga = sorgente[inizio_riga:fine_riga]
    assert "FASE0_DISATTIVATO" not in riga
