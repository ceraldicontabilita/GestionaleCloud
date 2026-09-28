"""
Motore condiviso per validazione ed estrazione IBAN.

Prima di questo modulo la stessa regex per riconoscere un IBAN italiano era
duplicata identica in app/services/suppliers/iban_service.py e
app/routers/suppliers_module/iban.py, e la validazione "vera" (lunghezza +
prefisso paese) viveva solo in app/services/suppliers/validators.py.
Questo modulo e' l'unico punto di verita' per entrambe le cose.

Nota: ``valida_iban`` controlla solo la forma (lunghezza 27 + prefisso "IT");
chi scrive un IBAN in un ordine di pagamento usa ``iban_mod97_valido``, che
calcola anche la cifra di controllo.
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


def iban_mod97_valido(iban: str) -> bool:
    """Check digit ISO 13616 (MOD 97-10) di un IBAN di qualunque paese SEPA.

    Serve a chi scrive un IBAN in un ordine di pagamento: la sola forma
    (``valida_iban``) lascia passare una cifra sbagliata, e la banca rifiuta
    il bonifico o, peggio, lo manda a un altro conto.
    """
    pulito = "".join(c for c in str(iban or "") if c.isalnum()).upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", pulito):
        return False
    if pulito.startswith("IT") and len(pulito) != IBAN_ITALIANO_LUNGHEZZA:
        return False
    riordinato = pulito[4:] + pulito[:4]
    numero = "".join(str(int(c, 36)) for c in riordinato)
    return int(numero) % 97 == 1
