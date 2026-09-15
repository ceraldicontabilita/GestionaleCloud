"""Fase 0 (PROMPT_CLAUDE_CODE_FASE_0.md punto 11): "Motore C" (riconciliazione
automatica fatture provvisorie durante l'import estratto conto) disattivato —
niente più scritture in prima_nota_banca né flag pagata sulle fatture durante
l'import.
"""
import inspect

from app.routers.bank import estratto_conto as mod


def test_fase0_disattivato_e_true():
    assert mod.FASE0_DISATTIVATO is True


def test_ciclo_motore_c_gated_da_fase0_disattivato():
    sorgente = inspect.getsource(mod)
    assert (
        "for f in provvisori if (not FASE0_DISATTIVATO and fonte_ufficiale "
        "and has_material_changes) else []:"
    ) in sorgente
