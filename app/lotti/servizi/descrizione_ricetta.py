"""Descrizione breve derivata esclusivamente dagli ingredienti della ricetta.

Non legge note o procedimento: quei campi sono interni e non devono finire
nel Menu pubblico. Nessuna caratteristica del prodotto viene inferita dal nome.
"""

from app.lotti.allergeni import estrai_nomi_ingredienti


def descrizione_da_ingredienti(ricetta: dict, limite: int = 140) -> str | None:
    nomi = estrai_nomi_ingredienti(ricetta)
    if not nomi:
        return None

    selezionati: list[str] = []
    for nome in nomi:
        candidato = ", ".join([*selezionati, nome])
        if len(f"Preparato con {candidato}.") > limite:
            break
        selezionati.append(nome)
    if not selezionati:
        return None
    return f"Preparato con {', '.join(selezionati)}."
