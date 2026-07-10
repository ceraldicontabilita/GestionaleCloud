"""
Motore condiviso per validazione ed estrazione IBAN.

Prima di questo modulo la stessa regex per riconoscere un IBAN italiano era
duplicata identica in app/services/suppliers/iban_service.py e
app/routers/suppliers_module/iban.py, e la validazione "vera" (lunghezza +
prefisso paese) viveva solo in app/services/suppliers/validators.py.
Questo modulo e' l'unico punto di verita' per entrambe le cose.

Nota: la validazione qui e' solo di formato (lunghezza 27 + prefisso "IT"),
non calcola il check digit MOD97. Nessuna implementazione esistente nel
repo lo faceva, quindi non e' stato introdotto per non cambiare
comportamento: se in futuro serve un controllo piu' rigoroso va aggiunto
esplicitamente.
"""
import re

# Regex per riconoscere un IBAN italiano in un testo libero (fatture XML,
# estratti conto, buste paga): IT + 2 cifre di controllo + 1 CIN + 5 ABI +
# 5 CAB + 12 conto.
IBAN_PATTERN = re.compile(r'IT\d{2}[A-Z]?\d{5}\d{5}[A-Z0-9]{12}', re.IGNORECASE)

IBAN_ITALIANO_LUNGHEZZA = 27


def valida_iban(iban: str) -> bool:
    """Valida formato base di un IBAN italiano (lunghezza + prefisso paese)."""
    if not iban:
        return False
    iban_clean = "".join(c for c in iban if c.isalnum()).upper()
    return len(iban_clean) == IBAN_ITALIANO_LUNGHEZZA and iban_clean.startswith("IT")


def estrai_iban_da_testo(testo: str):
    """Cerca il primo IBAN italiano valido in un testo libero, o None."""
    if not testo:
        return None
    match = IBAN_PATTERN.search(testo.upper())
    if match and valida_iban(match.group(0)):
        return match.group(0)
    return None
