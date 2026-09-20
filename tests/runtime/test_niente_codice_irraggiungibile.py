"""Guardia: non rientra codice dopo un `return` o un `raise`.

Non e' una questione di ordine. In questo repository quel codice aveva sempre
la stessa storia: un fabbricatore di registrazioni HACCP — controlli dell'olio
«entro le soglie», esiti di disinfestazione tirati a sorte con
`random.random() < 0.98`, interventi attribuiti a una ditta reale «come da
contratto» — che qualcuno aveva disattivato mettendogli davanti un `return 0`
o un `raise HTTPException(410)`, lasciando il corpo dietro.

Disattivato cosi' non e' rimosso: bastava togliere una riga per rimetterlo in
funzione, e nel frattempo il modulo si leggeva come se quelle registrazioni
nascessero ancora da li'. Un caso diverso, ma con lo stesso sintomo, era il
turno delle 07:00 nello scheduler: dopo il `return` verso l'orchestratore
c'era una seconda copia del giro, con `marca_giorni_non_rilevati` dentro — chi
la leggeva credeva che quella marcatura partisse da li'.

Nell'ERP era lo stesso, ma sui soldi: il pagamento manuale confermato «senza
alcuna prova bancaria o di cassa verificata», l'auto-conferma dei provvisori
sul solo metodo dichiarato in anagrafica, l'abbinamento degli assegni alle
fatture per importo entro 10 euro e data entro 30 giorni. Tutti disattivati
con un `raise HTTPException(409)` davanti, tutti ancora scritti sotto.

Il codice che non gira si toglie. Se una funzione deve smettere di fare
qualcosa, si toglie il corpo e si lascia la ragione scritta.
"""
import ast
import pathlib

import pytest

RADICE = pathlib.Path(__file__).resolve().parents[2] / "app"


def _funzioni_con_codice_morto(sorgente: str):
    """(nome, riga della sentenza che chiude, righe morte) per ogni funzione."""
    trovate = []
    for nodo in ast.walk(ast.parse(sorgente)):
        if not isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        corpo = nodo.body
        for indice, sentenza in enumerate(corpo[:-1]):
            if isinstance(sentenza, (ast.Return, ast.Raise)):
                morte = corpo[indice + 1:]
                trovate.append(
                    (nodo.name, sentenza.lineno, morte[-1].end_lineno - morte[0].lineno + 1)
                )
                break
    return trovate


MODULI = sorted(RADICE.rglob("*.py"))
assert MODULI, "nessun modulo trovato: il percorso di app/ e' cambiato"


@pytest.mark.parametrize("modulo", MODULI, ids=lambda p: str(p.relative_to(RADICE)))
def test_nessuna_funzione_ha_codice_dopo_il_return(modulo):
    morte = _funzioni_con_codice_morto(modulo.read_text(encoding="utf-8"))

    assert not morte, "\n".join(
        f"{modulo}:{riga} {nome}() — {righe} righe che non girano mai. "
        "Se non devono girare, vanno tolte, non messe dietro un return."
        for nome, riga, righe in morte
    )


def test_la_guardia_riconosce_il_caso_che_deve_fermare():
    """Il controllo va provato, o una guardia rotta passa sempre."""
    fabbricatore = (
        "async def genera():\n"
        "    return 0\n"
        "    for frigo in FRIGGITRICI:\n"
        "        await db.olio.insert_one({'esito': 'conforme'})\n"
    )

    assert _funzioni_con_codice_morto(fabbricatore) == [("genera", 2, 2)]
    assert _funzioni_con_codice_morto("def pulita():\n    return 0\n") == []
