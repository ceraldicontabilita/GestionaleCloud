"""Un solo motore Salari V2, e il netto nullo resta nullo sul ramo vivo.

Fino al 19/09/2026 `services/salari_unificati_v2.py` esisteva in due copie. La
copia `app/hr` era una fotografia piu' vecchia; la copia ERP e' quella sul
percorso di ingest vivo (email_monitor / post_download_pipeline ->
`services/cedolini_manager` -> `processa_cedolino_v2`).

La Fase 3 aveva applicato la regola «cella vuota → valore nullo, MAI zero»
(CLAUDE.md, «Personale») alla sola copia HR: sul ramo che gira davvero il netto
illeggibile continuava a essere schiacciato a `0.0` da `float(... or 0)` e a
finire nello stesso errore «netto=0» di uno zero vero, indistinguibili a valle.
Questi test coprono la correzione sul ramo vivo.
"""
import asyncio

from app.constants.stati_netto import NETTO_NON_PRESENTE_O_NON_LEGGIBILE
from app.services import salari_unificati_v2 as motore


def _run(coroutine):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coroutine)
    finally:
        loop.close()


class _DbEsplosivo:
    """Qualunque accesso al database e' un errore: questi casi si fermano prima."""

    def __getitem__(self, nome):
        raise AssertionError(
            f"Il cedolino non doveva arrivare al database (collection '{nome}'): "
            "una busta senza netto leggibile non alimenta Salari."
        )


def test_netto_illeggibile_non_diventa_zero():
    res = _run(motore.processa_cedolino_v2(
        _DbEsplosivo(),
        {"codice_fiscale": "RSSMRA80A01F839X", "nome_dipendente": "ROSSI MARIO",
         "mese": 3, "anno": 2026, "netto_mese": None},
    ))

    assert res["stato_netto"] == NETTO_NON_PRESENTE_O_NON_LEGGIBILE
    assert NETTO_NON_PRESENTE_O_NON_LEGGIBILE in res["errore"]
    assert res["prima_nota_id"] is None


def test_netto_zero_vero_ha_un_errore_diverso_dal_netto_assente():
    """Zero e' un valore, l'assenza no: i due casi non vanno confusi."""
    res = _run(motore.processa_cedolino_v2(
        _DbEsplosivo(),
        {"codice_fiscale": "RSSMRA80A01F839X", "nome_dipendente": "ROSSI MARIO",
         "mese": 3, "anno": 2026, "netto_mese": 0},
    ))

    assert res["errore"] == "Netto pari a zero sul cedolino"
    assert NETTO_NON_PRESENTE_O_NON_LEGGIBILE not in res["errore"]


def test_anagrafica_incompleta_non_parla_di_netto():
    res = _run(motore.processa_cedolino_v2(
        _DbEsplosivo(),
        {"codice_fiscale": "", "nome_dipendente": "", "mese": 3, "anno": 2026,
         "netto_mese": 1500.0},
    ))

    assert res["errore"] == "Dati mancanti (CF, mese o anno)"


def test_la_copia_hr_e_un_re_export_del_modulo_unico():
    from app.hr.services import salari_unificati_v2 as copia_hr

    for nome in (
        "processa_cedolino_v2",
        "registra_pagamento_salario",
        "get_saldo_completo_dipendente",
        "get_riepilogo_salari_tutti",
    ):
        assert getattr(copia_hr, nome) is getattr(motore, nome), (
            f"{nome} sul lato HR non e' la funzione del modulo unico: il fork "
            "e' tornato, e con lui il rischio di una correzione applicata a "
            "una copia sola."
        )


def test_il_riepilogo_non_rilegge_i_cedolini_per_ogni_dipendente():
    """Niente find dentro il ciclo: l'adattatore Supabase non ha indici."""
    import inspect

    corpo = inspect.getsource(motore.get_riepilogo_salari_tutti)
    ciclo = corpo[corpo.index("for dip in dipendenti:"):]
    assert 'db["cedolini"].find' not in ciclo, (
        "Lettura dei cedolini dentro il ciclo sui dipendenti: fino a 200 find "
        "su una tabella senza indici."
    )
    assert "cedolini_per_cf" in corpo
