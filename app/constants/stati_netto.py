"""I quattro stati del netto di un cedolino — punto unico.

CLAUDE.md, «Personale»: il netto si legge **solo** dalla cella graficamente
associata a `TOTALE NETTO` / `NETTO DEL MESE` / `NETTO IN BUSTA`, mai da
`ARR. PREC.`, competenze, trattenute, TFR, arrotondamenti o dal nome del file.
**Cella vuota → valore nullo, mai zero.** E soltanto
`NETTO_VERIFICATO_DA_CEDOLINO` alimenta Salari e bonifici.

Prima del 19/09/2026 nel codice esisteva un solo stato, e le sue uniche due
occorrenze stavano dentro una guardia che trattava lo stato **assente** come
verificato. Il parser non scriveva mai gli altri tre: un netto illeggibile
tornava `0.0`, cioe' indistinguibile da uno zero vero, e da li' passava.
"""
from __future__ import annotations

#: Il netto e' stato letto dalla cella giusta del cedolino. **L'unico** che
#: alimenta Prima Nota Salari e i bonifici.
NETTO_VERIFICATO_DA_CEDOLINO = "NETTO_VERIFICATO_DA_CEDOLINO"

#: La cella del netto non c'e' o non e' leggibile. L'importo resta **nullo**,
#: non zero: zero e' un valore, l'assenza no.
NETTO_NON_PRESENTE_O_NON_LEGGIBILE = "NETTO_NON_PRESENTE_O_NON_LEGGIBILE"

#: Piu' candidati plausibili e discordanti per il netto: serve un occhio umano,
#: non si sceglie il primo o il piu' grande.
MULTIPLE_NETS_DA_VERIFICARE = "MULTIPLE_NETS_DA_VERIFICARE"

#: Il parser si e' rotto su quel documento. Diverso da «non l'ho trovato»:
#: qui non sappiamo nemmeno se il dato ci fosse.
ERRORE_PARSER = "ERRORE_PARSER"

STATI_NETTO = (
    NETTO_VERIFICATO_DA_CEDOLINO,
    NETTO_NON_PRESENTE_O_NON_LEGGIBILE,
    MULTIPLE_NETS_DA_VERIFICARE,
    ERRORE_PARSER,
)

#: Gli stati che **non** possono alimentare Salari e bonifici.
STATI_NON_UTILIZZABILI = tuple(
    s for s in STATI_NETTO if s != NETTO_VERIFICATO_DA_CEDOLINO
)


def alimenta_salari(stato: object) -> bool:
    """True solo per il netto verificato.

    Fallisce **chiuso**: uno stato assente, vuoto o sconosciuto non passa. Il
    contrario — trattare l'assenza come verificato — e' esattamente il difetto
    corretto il 19/09/2026 in `prima_nota_salari.import_salari_verificati`.
    """
    return str(stato or "").strip().upper() == NETTO_VERIFICATO_DA_CEDOLINO
