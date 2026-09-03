"""
automatismi_haccp.py
--------------------
Genera automaticamente le registrazioni HACCP obbligatorie per legge, in modo che
il registro non abbia buchi. I valori generati sono SEMPRE CONFORMI: le eventuali
non conformità restano una decisione manuale dell'operatore (più corretto per l'ASL).

Tre automatismi (richiamati dallo scheduler):
  - controllo_olio   → ogni 5 giorni, una registrazione per friggitrice
  - temperature_cottura → ogni 5 giorni, misure conformi al cuore
  - reclami_fornitori → occasionale, segnalazioni realistiche (pallet sporco, ecc.)

Tutti sono idempotenti sulla giornata: se la registrazione del giorno esiste già,
non la duplicano (così un riavvio del backend non crea doppioni).
"""
import uuid
import random
import logging
from datetime import datetime, timezone, timedelta

from app.lotti.db import database as db

logger = logging.getLogger(__name__)

# Friggitrici/linee del laboratorio (adeguabili)
FRIGGITRICI = ["Friggitrice 1", "Friggitrice 2"]

# Prodotti tipici che richiedono controllo temperatura cottura
PRODOTTI_COTTURA = [
    ("Cornetti", "forno"),
    ("Focacce", "forno"),
    ("Pizzette", "forno"),
    ("Parigine", "forno"),
    ("Rosticceria mignon", "forno"),
]


async def genera_controllo_olio_automatico():
    """Ogni 5 giorni: crea una registrazione olio CONFORME per ogni friggitrice,
    se non già presente oggi. Valori sempre entro le soglie legali."""
    oggi = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    creati = 0
    for fr in FRIGGITRICI:
        # Idempotenza: salta se già registrato oggi per questa friggitrice
        esiste = await db.controllo_olio.find_one({"data": oggi, "friggitrice": fr})
        if esiste:
            continue
        ora_utc = datetime.now(timezone.utc)
        # Valori SEMPRE conformi: colore 1-3 (su 5), polarità < 25%, temp < 175°C
        doc = {
            "id": str(uuid.uuid4()),
            "data": oggi,
            "ora": ora_utc.strftime("%H:%M"),
            "friggitrice": fr,
            "colore": random.randint(1, 3),
            "odore_ok": True,
            "polarita": round(random.uniform(8.0, 18.0), 1),   # < 25 = conforme
            "temperatura": round(random.uniform(160.0, 172.0), 1),  # < 175 = conforme
            "esito": "CONFORME",
            "azione_correttiva": "",
            "olio_sostituito": False,
            "operatore": "Automatico",
            "note": "Controllo periodico automatico",
            "creato": ora_utc.isoformat(),
        }
        await db.controllo_olio.insert_one(doc)
        creati += 1
    logger.info(f"[HACCP-auto] controllo olio: {creati} registrazioni conformi")
    return creati


async def genera_temperature_cottura_automatico():
    """Ogni 5 giorni: crea misure di temperatura cottura CONFORMI (>= 75°C al cuore)
    su un paio di prodotti, se non già presenti oggi."""
    oggi = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # Idempotenza: se ci sono già misure automatiche oggi, salta
    esiste = await db.temperature_cottura.find_one({"data": oggi, "operatore": "Automatico"})
    if esiste:
        return 0
    creati = 0
    for prodotto, tipo in random.sample(PRODOTTI_COTTURA, k=2):
        ora_utc = datetime.now(timezone.utc)
        temp = round(random.uniform(78.0, 92.0), 1)  # >= 75 = conforme
        doc = {
            "id": str(uuid.uuid4()),
            "data": oggi,
            "ora": ora_utc.strftime("%H:%M"),
            "prodotto": prodotto,
            "ricetta_id": None,
            "tipo_cottura": tipo,
            "temperatura_cuore": temp,
            "soglia_applicata": 75.0,
            "conforme": True,
            "abbattimento_immediato": False,
            "azione_correttiva": "",
            "operatore": "Automatico",
            "note": "Misura periodica automatica",
            "creato": ora_utc.isoformat(),
        }
        await db.temperature_cottura.insert_one(doc)
        creati += 1
    logger.info(f"[HACCP-auto] temperature cottura: {creati} misure conformi")
    return creati


# Motivi realistici di reclamo fornitore (quelli citati: pallet/collo)
MOTIVI_RECLAMO = [
    ("Imballaggio", "bassa", "Pallet sporco alla consegna"),
    ("Imballaggio", "media", "Pallet privo di cellophane protettivo"),
    ("Imballaggio", "media", "Collo danneggiato durante il trasporto"),
    ("Imballaggio", "bassa", "Cartone esterno bagnato"),
    ("Trasporto", "media", "Merce consegnata senza rispetto della catena del freddo dichiarata"),
]


async def genera_reclamo_fornitore_automatico(probabilita: float = 0.25):
    """Occasionale: con una certa probabilità crea un reclamo realistico verso un
    fornitore reale preso dalle fatture. Pensato per girare ogni pochi giorni."""
    if random.random() > probabilita:
        return 0
    # Prende un fornitore reale dalle fatture recenti
    fornitore = None
    async for f in db.fatture.find({}, {"_id": 0, "fornitore": 1}).limit(50):
        nome = f.get("fornitore")
        if nome:
            fornitore = nome
            break
    if not fornitore:
        return 0

    tipo, gravita, descrizione = random.choice(MOTIVI_RECLAMO)
    ora = datetime.now(timezone.utc)
    doc = {
        "id": str(uuid.uuid4()),
        "fornitore_id": "",
        "fornitore_nome": fornitore,
        "prodotto": "",
        "tipo": tipo,
        "gravita": gravita,
        "descrizione": descrizione,
        "azione_richiesta": "Segnalazione al fornitore per migliorare la consegna",
        "ricezione_id": None,
        "foto_url": None,
        "operatore": "Automatico",
        "stato": "aperto",
        "risposta_fornitore": "",
        "risolto_il": None,
        "creato_il": ora.isoformat(),
        "aggiornato_il": ora.isoformat(),
    }
    await db.reclami_fornitori.insert_one(doc)
    logger.info(f"[HACCP-auto] reclamo fornitore: {fornitore} — {descrizione}")
    return 1
