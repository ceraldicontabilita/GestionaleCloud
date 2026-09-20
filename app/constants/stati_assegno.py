"""Gli assegni che stanno nel portafoglio: usciti dal blocchetto, non incassati.

La chiusura d'esercizio li sommava cosi':

    {"stato": {"$in": ["emesso", "consegnato"]}, "incassato": {"$ne": True}}

Misurato in produzione il 20/09/2026 su 109 assegni: `consegnato` non e' uno
degli stati di `ASSEGNO_STATI` e nessuna riga lo porta; il campo booleano
`incassato` non esiste su nessuna riga, quindi quel filtro passava sempre;
e `assegnato` / `parzialmente_assegnato` — gli stati che scrive il collegamento
a fattura, cioe' un assegno consegnato al fornitore e non ancora incassato —
restavano **fuori** dal conto. Oggi tutti i 109 sono `incassato` e il totale
era corretto per caso.
"""
__all__ = ["ASSEGNI_STATI_IN_PORTAFOGLIO"]

#: `vuoto` e `compilato` non sono ancora usciti; `incassato` e' chiuso;
#: `annullato`, `stornato` e `scaduto` non valgono piu'.
ASSEGNI_STATI_IN_PORTAFOGLIO = (
    "emesso",
    "parzialmente_assegnato",
    "assegnato",
)
