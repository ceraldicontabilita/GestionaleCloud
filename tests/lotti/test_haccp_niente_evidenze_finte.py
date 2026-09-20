"""Guardia: nessuna registrazione HACCP nasce da sola.

Dentro `haccp_auto.py` c'erano due motori in contraddizione, e vinceva quello
sbagliato.

Il primo inventava la rilevazione del giorno:

    temp = round(max(t_min, min(t_max, base + random.uniform(-0.8, 0.8))), 1)
    ...
    "operatore": random.choice(OPERATORI),   # sei dipendenti veri, nome e cognome
    "allarme": False,

Il commento diceva «le rilevazioni automatiche sono SEMPRE CONFORMI», e infatti
il valore veniva schiacciato dentro le soglie della scheda. Lo stesso
succedeva alle sanificazioni, segnate «X» su tutte le attrezzature.

Il secondo, `marca_giorni_non_rilevati`, fa la cosa onesta: scrive
`temp: None` con il motivo, e non inventa niente.

Qualcuno aveva gia' messo un `return`/`raise` in testa agli endpoint, ma le
201 + 134 + 70 righe del generatore erano rimaste li' sotto, irraggiungibili e
pronte a tornare in funzione togliendo una riga. In archivio restano **384**
rilevazioni del 2026 nate cosi' (192 frigoriferi + 192 congelatori), ognuna
firmata col nome di una persona che non l'ha fatta.

Un registro HACCP e' un obbligo di legge: attestare controlli mai eseguiti,
con il nome di chi non li ha eseguiti, davanti a un'ispezione vale meno di un
registro vuoto. Questa guardia non guarda il testo del sorgente: guarda cosa
il codice fa e cosa espone.
"""
import ast
import inspect
from pathlib import Path

import pytest

RADICE = Path(__file__).resolve().parents[2]

# I moduli che registrano evidenze HACCP: nessuno di loro deve saper fabbricare
# una misura o una firma.
MODULI_HACCP = [
    "app/lotti/routers/haccp_auto.py",
    "app/lotti/routers/temperature_positive.py",
    "app/lotti/routers/temperature_negative.py",
    "app/lotti/routers/sanificazione.py",
    "app/lotti/routers/anomalie.py",
]


@pytest.mark.parametrize("percorso", MODULI_HACCP)
def test_niente_valori_casuali_nei_registri_haccp(percorso):
    sorgente = (RADICE / percorso).read_text(encoding="utf-8")
    albero = ast.parse(sorgente)

    casuali = [
        n for n in ast.walk(albero)
        if isinstance(n, ast.Attribute)
        and isinstance(n.value, ast.Name) and n.value.id == "random"
        and n.attr in {"uniform", "choice", "randint", "random", "gauss", "sample"}
    ]
    assert not casuali, (
        f"{percorso} usa random.{casuali[0].attr} alla riga {casuali[0].lineno}: "
        "una misura o una firma HACCP non si sorteggiano."
    )


@pytest.mark.parametrize("percorso", MODULI_HACCP)
def test_nessun_codice_irraggiungibile(percorso):
    """Il generatore era morto ma intatto: bastava togliere una riga.

    Il codice irraggiungibile non e' una svista di stile — e' una funzione
    intera che nessuno rivede piu' perche' «tanto non gira», e che il primo
    che tocca quel `raise` rimette in produzione.
    """
    albero = ast.parse((RADICE / percorso).read_text(encoding="utf-8"))
    morti = []
    for n in ast.walk(albero):
        if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef)):
            for i, istruzione in enumerate(n.body):
                if isinstance(istruzione, (ast.Return, ast.Raise)):
                    dopo = n.body[i + 1:]
                    if dopo:
                        morti.append(
                            f"{n.name}: righe {dopo[0].lineno}-{dopo[-1].end_lineno}"
                        )
                    break
    assert not morti, f"{percorso} ha codice irraggiungibile: {'; '.join(morti)}"


def test_gli_endpoint_che_popolavano_sono_chiusi():
    """Non basta che il corpo sia sparito: devono rispondere 410."""
    from fastapi import HTTPException

    import app.lotti.routers.haccp_auto as haccp

    for nome in ("popola_temperature_storiche", "popola_sanificazione_storica",
                 "popola_tutti_dati_haccp", "genera_dati_oggi"):
        funzione = getattr(haccp, nome)
        sorgente = inspect.getsource(funzione)
        assert "HTTPException" in sorgente and "410" in sorgente, (
            f"{nome} non e' piu' bloccato: puo' tornare a scrivere evidenze finte."
        )
    assert HTTPException  # l'import serve a provare che il tipo esiste davvero


def test_verifica_oggi_non_scrive_niente():
    """L'unico automatismo chiamato dallo scheduler ogni mattina alle 07:00."""
    import asyncio

    import app.lotti.routers.haccp_auto as haccp

    class _ArchivioCheEsplode:
        def __getattr__(self, nome):
            raise AssertionError(
                f"verifica_e_popola_oggi ha toccato `{nome}`: "
                "il job delle 07:00 non deve scrivere nessuna evidenza."
            )

    originale = haccp.db
    haccp.db = _ArchivioCheEsplode()
    try:
        esito = asyncio.run(haccp.verifica_e_popola_oggi())
    finally:
        haccp.db = originale

    assert esito["generato"] is False
    assert esito["elementi"] == []


def test_il_marcatore_dei_giorni_scoperti_non_inventa_la_temperatura():
    """La forma onesta, quella che resta: il buco si dichiara, non si riempie."""
    import app.lotti.routers.haccp_auto as haccp

    sorgente = inspect.getsource(haccp.marca_giorni_non_rilevati)
    assert '"temp": None' in sorgente, (
        "Il marcatore deve lasciare la temperatura VUOTA: e' tutto il suo senso."
    )
    assert "MOTIVO_NON_RILEVATO" in sorgente, "Il buco deve portare il suo motivo."
    assert "operatore" not in sorgente, (
        "Un giorno non rilevato non ha un operatore: non l'ha fatto nessuno."
    )
