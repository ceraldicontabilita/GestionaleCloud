"""
Motore controlli Noleggio Auto (specifica utente 10-07-2026).

Tre responsabilità, tutte centralizzate qui:

1. `driver_alla_data(veicolo, data)` — lo STORICO assegnazioni: il
   responsabile del veicolo non è il driver attuale ma quello valido
   alla data dell'evento (verbale del 10/03 → chi aveva l'auto il 10/03).

2. `contiene_segnali_cessazione(fattura)` — cerca nelle righe le diciture
   di chiusura contratto ("cessazione contratto", "ultimo canone",
   "restituzione veicolo"...). Lo stato del contratto lo cambia SOLO
   l'utente: il motore produce al massimo un avviso informativo.

3. `controlla_regolarita_canoni(db)` — per i veicoli con contratto ATTIVO
   controlla che arrivino fatture con regolarità (soglia
   NOLEGGIO_GIORNI_SENZA_FATTURA, default 35 giorni — scelta utente).
   Se mancano fatture: prima rilegge l'ultima fattura; se contiene
   segnali di cessazione propone "contratto cessato" (avviso info),
   altrimenti avviso SOFT "da verificare" (mai allarme grave immediato).
   REGOLA NON NEGOZIABILE: contratto cessato → MAI l'avviso di fattura
   mancante, lo storico costi resta.
"""
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .constants import FORNITORI_NOLEGGIO, TARGA_PATTERN, COLLECTION

logger = logging.getLogger(__name__)


def _solo_cifre(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _testo_fattura(invoice: Dict[str, Any]) -> str:
    """Testo indicizzabile completo, incluse targhe negli ADG XML."""
    parti = [str(invoice.get("descrizione") or "")]
    for linea in invoice.get("linee") or []:
        parti.append(str(linea.get("descrizione") or linea.get("Descrizione") or ""))
        for dato in linea.get("altri_dati_gestionali") or []:
            if isinstance(dato, dict):
                parti.extend(str(v) for v in dato.values() if v is not None)
            else:
                parti.append(str(dato))
    parti.extend(str(c) for c in (invoice.get("causali") or []))
    return " ".join(parti).upper()

# Diciture di chiusura contratto (specifica utente, minuscole per confronto)
DICITURE_CESSAZIONE = [
    "cessazione contratto",
    "contratto cessato",
    "fine contratto",
    "chiusura contratto",
    "restituzione veicolo",
    "ultimo canone",
    "conguaglio finale",
    "addebito finale",
    "periodo finale",
    "fine noleggio",
]

# Stati contratto che escludono ogni controllo di regolarità
STATI_CONTRATTO_CHIUSI = {"cessato", "chiuso", "archiviato"}


def contiene_segnali_cessazione(invoice: Dict[str, Any]) -> List[str]:
    """Ritorna le diciture di cessazione trovate nelle righe/causali."""
    testi: List[str] = []
    for linea in invoice.get("linee") or []:
        testi.append(str(linea.get("descrizione") or linea.get("Descrizione") or ""))
        altre = linea.get("altri_dati_gestionali") or []
        if isinstance(altre, list):
            testi.extend(str(x) for x in altre)
    for causale in invoice.get("causali") or []:
        testi.append(str(causale))
    testo = " ".join(testi).lower()
    return [d for d in DICITURE_CESSAZIONE if d in testo]


def driver_alla_data(veicolo: Dict[str, Any], data_evento: Optional[str]) -> Dict[str, Any]:
    """Responsabile del veicolo alla data dell'evento (YYYY-MM-DD).

    Usa lo storico `assegnazioni` [{driver, driver_id, dal, al}] se
    presente; l'assegnazione corrente vale come voce aperta (al=None).
    Senza storico che copre la data → fallback al driver attuale, con
    fonte esplicita così l'interfaccia può distinguere.
    """
    data = (data_evento or "")[:10]
    assegnazioni = veicolo.get("assegnazioni") or []
    if data and assegnazioni:
        for a in assegnazioni:
            dal = (a.get("dal") or "")[:10]
            al = (a.get("al") or "")[:10]
            if dal and data >= dal and (not al or data <= al):
                return {
                    "driver": a.get("driver"),
                    "driver_id": a.get("driver_id"),
                    "fonte": "storico_assegnazioni",
                }
    return {
        "driver": veicolo.get("driver") or veicolo.get("driver_nome"),
        "driver_id": veicolo.get("driver_id"),
        "fonte": "driver_attuale",
    }


async def _ultima_fattura_per_targa(db, targa: str, fornitore_piva: Optional[str]) -> Optional[Dict[str, Any]]:
    """Ultima fattura (per data) di un noleggiatore che cita la targa."""
    pive = [fornitore_piva] if fornitore_piva else list(FORNITORI_NOLEGGIO.values())
    pive_norm = {_solo_cifre(p) for p in pive if p}
    targa_up = targa.upper()
    cursor = db["invoices"].find(
        # I dati storici contengono P.IVA sia normalizzate sia formattate:
        # filtrare qui per uguaglianza esatta nascondeva fatture realmente
        # caricate. La selezione del noleggiatore viene fatta sotto dopo la
        # normalizzazione, su un insieme comunque limitato.
        {},
        {"_id": 0, "id": 1, "invoice_number": 1, "invoice_date": 1,
         "supplier_name": 1, "supplier_vat": 1, "descrizione": 1,
         "linee.descrizione": 1, "linee.altri_dati_gestionali": 1, "causali": 1},
    ).sort("invoice_date", -1).limit(5000)
    fallback = None
    async for inv in cursor:
        if _solo_cifre(inv.get("supplier_vat")) not in pive_norm:
            continue
        testo = _testo_fattura(inv)
        if targa_up in testo:
            return inv
        # Fornitore con un solo veicolo: qualunque sua fattura vale
        if fallback is None and fornitore_piva:
            fallback = inv
    if fallback and fornitore_piva:
        altri = await db[COLLECTION].count_documents(
            {"fornitore_piva": fornitore_piva, "targa": {"$ne": targa_up}}
        )
        if altri == 0:
            return fallback
    return None


async def controlla_regolarita_canoni(db) -> Dict[str, Any]:
    """Controllo giornaliero regolarità fatture per i veicoli attivi."""
    soglia_giorni = int(os.environ.get("NOLEGGIO_GIORNI_SENZA_FATTURA", "35") or 35)
    oggi = datetime.now(timezone.utc).date()

    # Anagrafica nota dalla specifica: la Stelvio GG782PN è a contratto
    # cessato. Idempotente e SOLO se lo stato non è mai stato impostato:
    # non sovrascrive mai una scelta fatta dall'utente.
    await db[COLLECTION].update_one(
        {"targa": "GG782PN", "stato_contratto": {"$exists": False}},
        {"$set": {"stato_contratto": "cessato",
                  "stato_contratto_fonte": "specifica_utente_2026_07_10"}},
    )

    esiti = {"controllati": 0, "senza_fattura_recente": 0,
             "cessazioni_rilevate": 0, "alert_soft": 0, "saltati_cessati": 0}

    async for veicolo in db[COLLECTION].find({}, {"_id": 0}):
        targa = (veicolo.get("targa") or "").upper()
        if not targa:
            continue
        stato = (veicolo.get("stato_contratto") or "").lower()
        if stato in STATI_CONTRATTO_CHIUSI:
            # REGOLA: contratto cessato → mai avvisi di fattura mancante
            esiti["saltati_cessati"] += 1
            continue

        esiti["controllati"] += 1
        ultima = await _ultima_fattura_per_targa(db, targa, veicolo.get("fornitore_piva"))
        if not ultima or not ultima.get("invoice_date"):
            continue  # nessuno storico fatture: niente da sorvegliare

        try:
            data_ultima = datetime.strptime(ultima["invoice_date"][:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        giorni_passati = (oggi - data_ultima).days
        if giorni_passati <= soglia_giorni:
            from app.services.alert_engine import risolvi_alert
            await risolvi_alert("NOL_FATTURA_MANCANTE", targa, db, "fattura_recente_rilevata")
            continue

        esiti["senza_fattura_recente"] += 1
        # Un solo avviso per "buco": se l'ultima fattura vista è la stessa
        # dell'ultimo avviso, non ripetere.
        if veicolo.get("alert_canoni_su_fattura") == ultima.get("id"):
            continue

        segnali = contiene_segnali_cessazione(ultima)
        try:
            from app.services.alert_engine import genera_alert
            if segnali:
                # Probabile cessazione: avviso INFORMATIVO, lo stato lo
                # confermi tu dalla scheda veicolo.
                await genera_alert(
                    "NOL_CESSAZIONE_RILEVATA", targa, COLLECTION,
                    f"Veicolo {targa}: nessuna fattura da {giorni_passati} giorni e "
                    f"l'ultima ({ultima.get('invoice_number', '?')} del "
                    f"{ultima['invoice_date'][:10]}) contiene '{segnali[0]}' — "
                    f"probabile contratto cessato: conferma lo stato dalla scheda veicolo",
                    db,
                )
                esiti["cessazioni_rilevate"] += 1
            else:
                await genera_alert(
                    "NOL_FATTURA_MANCANTE", targa, COLLECTION,
                    f"Veicolo {targa} (contratto attivo): nessuna fattura di noleggio "
                    f"da {giorni_passati} giorni (ultima: "
                    f"{ultima.get('invoice_number', '?')} del {ultima['invoice_date'][:10]}) "
                    f"— da verificare, non è detto sia un problema",
                    db,
                )
                esiti["alert_soft"] += 1
        except Exception:
            logger.exception(f"Alert regolarità canoni non generato per {targa}")

        await db[COLLECTION].update_one(
            {"targa": targa},
            {"$set": {"alert_canoni_su_fattura": ultima.get("id"),
                      "ultimo_controllo_canoni": datetime.now(timezone.utc).isoformat()}},
        )

    logger.info(f"[Noleggio] Controllo canoni: {esiti}")
    return esiti
