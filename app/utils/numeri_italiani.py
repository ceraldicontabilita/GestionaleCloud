"""
Motore condiviso per il parsing di importi in formato italiano.

Prima di questo modulo la stessa logica (spesso con piccole varianti non
intenzionali) era duplicata in una decina di parser diversi (F24, cedolini,
estratti conto, distinte bonifici). Questa funzione e' l'unione di TUTTI i
comportamenti oggi in produzione, cosi' da poter sostituire le versioni
locali senza cambiare il risultato per nessun chiamante esistente:

- tollera None, stringa vuota, input non stringa (cast automatico)
- rimuove simbolo euro e spazi
- riconosce sia "1.234,56" (punto migliaia, virgola decimale) sia il caso
  raro "1,234.56" (virgola migliaia, punto decimale), guardando l'ordine
  dei due separatori quando sono entrambi presenti
- puo' mantenere o azzerare il segno (alcuni parser vogliono sempre un
  valore assoluto, altri devono preservare gli importi negativi)
- puo' rimuovere i suffissi "h"/"hm" usati nei giustificativi presenze
  (es. "8,66hm" = ore)
- riconosce il punto usato SOLO come separatore migliaia senza virgola
  decimale ("1.234" = milleduecentotrentaquattro, "12.345.678"): se ogni
  gruppo dopo il primo punto e' di esattamente 3 cifre, i punti vengono
  rimossi come migliaia (comportamento storico dei parser F24 ed estratto
  conto, dove il formato e' sempre italiano)
"""
import re

# "1.234", "12.345.678": punto solo come separatore migliaia, nessuna virgola
_SOLO_MIGLIAIA = re.compile(r'^[+-]?\d{1,3}(\.\d{3})+$')


def parse_importo_ita(value, *, default: float = 0.0, keep_sign: bool = True,
                       strip_ore_suffix: bool = False) -> float:
    """Converte un importo in formato italiano in float.

    Restituisce `default` per input vuoto/non convertibile, mai un'eccezione:
    e' il comportamento gia' seguito da tutti i parser esistenti.
    """
    if value is None:
        return default
    s = str(value).strip()
    if not s:
        return default

    s = s.replace('€', '').replace(' ', '')
    if strip_ore_suffix:
        s = s.replace('hm', '').replace('h', '')
    if not keep_sign:
        s = s.replace('+', '').replace('-', '')

    if ',' in s and '.' in s:
        if s.index('.') < s.index(','):
            # formato italiano standard: punto migliaia, virgola decimale
            s = s.replace('.', '').replace(',', '.')
        else:
            # formato anglosassone misto: virgola migliaia, punto decimale
            s = s.replace(',', '')
    elif ',' in s:
        s = s.replace(',', '.')
    elif _SOLO_MIGLIAIA.match(s):
        # solo punti in posizione migliaia, niente virgola: "1.234" -> 1234
        s = s.replace('.', '')

    try:
        result = float(s)
    except (ValueError, TypeError):
        return default

    return abs(result) if not keep_sign else result
