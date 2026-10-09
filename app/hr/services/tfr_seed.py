"""Caricamento una-tantum dei periodi TFR forniti dal titolare in chat (28-29/07/2026).

All'avvio dell'app inserisce le scalette di Vespa, Taiano, Moscato, Parisi e
Carotenuto nel simulatore TFR, così il titolare non deve caricare nulla a mano.
È idempotente per dipendente: chi ha già periodi salvati non viene toccato
(quindi non sovrascrive mai modifiche fatte dopo dall'interfaccia). Quando i
dati saranno confermati in produzione, questo modulo si può rimuovere.
"""
import logging
from datetime import datetime, timezone
from uuid import uuid4

from app.hr.database import Database

logger = logging.getLogger(__name__)

# codice fiscale -> (nome per il log/fallback ricerca, [(inizio, fine|None=in corso, €/settimana)])
_SEED = {
    "VSPVCN67T26F839P": ("Vespa", [
        ("2015-07-22", "2015-12-31", 240.0),
        ("2016-01-01", "2016-12-31", 240.0),
        ("2017-01-01", "2017-12-31", 250.0),
        ("2018-01-01", "2018-12-31", 250.0),
        ("2019-01-01", "2019-12-31", 270.0),
        ("2020-01-01", "2020-12-31", 270.0),
        ("2021-01-01", "2021-12-31", 270.0),
        ("2022-01-01", "2022-12-31", 300.0),
        ("2023-01-01", "2023-12-31", 300.0),
        ("2024-01-01", "2024-12-31", 300.0),
        ("2025-09-01", "2025-12-31", 350.0),
        ("2026-01-01", None, 350.0),
    ]),
    "TNALGU95L10F839Y": ("Taiano", [
        ("2020-01-01", "2020-12-31", 220.0),
        ("2021-01-01", "2021-12-31", 250.0),
        ("2022-01-01", "2022-12-31", 300.0),
        ("2023-01-01", "2023-12-31", 300.0),
        ("2024-01-01", "2024-12-31", 300.0),
        ("2025-01-01", "2025-08-30", 330.0),
        ("2025-09-01", "2025-12-31", 350.0),
        ("2026-01-01", None, 350.0),
    ]),
    "MSCMNL88R26F839C": ("Moscato", [
        ("2011-01-01", "2012-03-12", 150.0),
        ("2012-03-13", "2012-12-31", 180.0),
        ("2013-01-01", "2013-12-31", 180.0),
        ("2014-01-01", "2014-12-31", 200.0),
        ("2015-01-01", "2015-12-31", 240.0),
        ("2016-01-01", "2016-12-31", 240.0),
        ("2017-01-01", "2017-12-31", 250.0),
        ("2018-01-01", "2018-12-31", 250.0),
        ("2019-01-01", "2019-12-31", 270.0),
        ("2020-01-01", "2020-12-31", 270.0),
        ("2021-01-01", "2021-12-31", 270.0),
        ("2022-01-01", "2022-12-31", 300.0),
        ("2023-01-01", "2023-12-31", 300.0),
        ("2024-01-01", "2024-12-31", 300.0),
        ("2025-01-01", "2025-08-30", 330.0),
        ("2025-09-01", "2025-12-31", 350.0),
        ("2026-01-01", None, 350.0),
    ]),
    "PRSNTN80R12F839X": ("Parisi", [
        ("2019-09-26", "2019-12-31", 270.0),
        ("2020-01-01", "2020-12-31", 270.0),
        ("2021-01-01", "2021-12-31", 270.0),
        ("2022-01-01", "2022-12-31", 300.0),
        ("2023-01-01", "2023-12-31", 300.0),
        ("2024-01-01", "2024-12-31", 300.0),
        ("2025-01-01", "2025-08-30", 330.0),
        ("2025-09-01", "2025-12-31", 350.0),
        ("2026-01-01", None, 350.0),
    ]),
    "CRTNNL96P52F839M": ("Carotenuto", [
        ("2025-09-30", "2025-12-31", 250.0),
        ("2026-01-01", None, 250.0),
    ]),
}


async def seed_tfr_periodi():
    """Inserisce le scalette del titolare per i dipendenti che non ne hanno già."""
    try:
        db = Database.get_db()
        for cf, (nome, righe) in _SEED.items():
            dip = await db.dipendenti.find_one({"codice_fiscale": cf}, {"_id": 0, "id": 1})
            if not dip:
                dip = await db.dipendenti.find_one(
                    {"merged_into": {"$exists": False},
                     "$or": [{"cognome": {"$regex": nome, "$options": "i"}},
                             {"nome_completo": {"$regex": nome, "$options": "i"}}]},
                    {"_id": 0, "id": 1})
            if not dip:
                logger.warning(f"Seed TFR: dipendente {nome} non trovato in anagrafica, salto")
                continue
            esistenti = await db.tfr_simulazione_periodi.count_documents({"dipendente_id": dip["id"]})
            if esistenti:
                continue  # già popolato (o modificato a mano): non toccare
            # Si salvano solo date e importo: i valori si ricalcolano sempre alla lettura.
            for inizio, fine, importo in righe:
                await db.tfr_simulazione_periodi.insert_one({
                    "id": str(uuid4()), "dipendente_id": dip["id"],
                    "data_inizio": inizio, "data_fine": fine,
                    "importo_settimanale": importo,
                    "chiuso_automaticamente": False, "fonte": "seed_chat_titolare",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                })
            logger.info(f"Seed TFR: caricati {len(righe)} periodi per {nome}")
    except Exception as e:
        logger.warning(f"Seed TFR non riuscito (non blocca l'avvio): {e}")
