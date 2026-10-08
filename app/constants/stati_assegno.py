"""Stati degli assegni: un registro solo, letto da router, servizi e chiusura.

Prima gli stati vivevano nel router (`ASSEGNO_STATI`), le liste di comodo in
ogni modulo che ne aveva bisogno (``["vuoto", "compilato"]`` nel pacchetto del
commercialista, ``["emesso", "incassato"]`` nel controllo di eliminazione).
Una lista che ne conosce solo una parte sbaglia in silenzio: il controllo di
eliminazione lasciava cancellare un assegno ``assegnato`` o ``stornato``, cioe'
un numero gia' uscito dal carnet.

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
__all__ = [
    "ASSEGNO_STATI",
    "STATI_DISPONIBILI",
    "STATI_NUMERO_CONSUMATO",
    "ASSEGNI_STATI_IN_PORTAFOGLIO",
]

#: Tutti gli stati ammessi, con l'etichetta. "assegnato"/"parzialmente_assegnato"
#: li scrive il collegamento a fatture (auto-matcher e collegamento manuale).
#: I colori li decide l'interfaccia, non il registro.
ASSEGNO_STATI = {
    "vuoto": {"label": "Vuoto"},
    "compilato": {"label": "Compilato"},
    "emesso": {"label": "Emesso"},
    "parzialmente_assegnato": {"label": "Parzialmente assegnato"},
    "assegnato": {"label": "Assegnato"},
    "incassato": {"label": "Incassato"},
    "annullato": {"label": "Annullato"},
    "stornato": {"label": "Stornato"},
    "scaduto": {"label": "Scaduto"},
}

#: Numeri ancora nel carnet: si possono compilare, e solo questi si eliminano.
STATI_DISPONIBILI = frozenset({"vuoto", "compilato"})

#: Un numero uscito dal carnet resta consumato: da questi stati non si torna
#: a "vuoto" o "compilato", nemmeno con un PUT generico, e la scheda non si
#: elimina (annullo e storno hanno un motivo e restano nello storico).
STATI_NUMERO_CONSUMATO = frozenset(ASSEGNO_STATI) - STATI_DISPONIBILI

#: `vuoto` e `compilato` non sono ancora usciti; `incassato` e' chiuso;
#: `annullato`, `stornato` e `scaduto` non valgono piu'.
ASSEGNI_STATI_IN_PORTAFOGLIO = (
    "emesso",
    "parzialmente_assegnato",
    "assegnato",
)
