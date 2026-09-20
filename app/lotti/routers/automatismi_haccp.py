"""automatismi_haccp.py — tre ingressi che NON registrano niente.

Qui vivevano tre generatori che fabbricavano registrazioni HACCP: controlli
dell'olio «sempre entro le soglie», temperature di cottura conformi e reclami
a fornitori estratti a sorte da un elenco di motivi verosimili. Un registro
cosi' non dice cosa e' stato fatto, dice cosa avrebbe fatto comodo scrivere, e
davanti a un'ispezione risponde chi lo esibisce.

Sono stati disattivati mettendogli davanti un `return 0`, e il corpo era
rimasto dietro: bastava togliere una riga per rimetterli in funzione. Ora il
corpo non c'e' piu'.

Le tre funzioni restano perche' lo scheduler le chiama ancora (job
`automatismi_haccp`) e perche' `tests/runtime/test_critical_safety_boundaries.py`
verifica che ritornino zero: e' la prova, scritta, che da qui non nasce nessuna
evidenza. Una misura, un controllo o un reclamo li registra una persona.
"""
import logging

logger = logging.getLogger(__name__)


async def genera_controllo_olio_automatico():
    """Nessun controllo dell'olio si crea da solo: lo registra chi lo esegue."""
    logger.warning("[HACCP-auto] controllo olio atteso: nessuna rilevazione sintetica creata")
    return 0


async def genera_temperature_cottura_automatico():
    """Nessuna temperatura di cottura si crea da sola: la misura una persona."""
    logger.warning("[HACCP-auto] temperatura cottura attesa: nessuna rilevazione sintetica creata")
    return 0


async def genera_reclamo_fornitore_automatico():
    """Nessun reclamo si crea da solo: lo apre chi ha visto la merce."""
    logger.warning("[HACCP-auto] reclamo fornitore atteso: nessun reclamo sintetico creato")
    return 0
