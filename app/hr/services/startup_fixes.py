"""Fix una-tantum richiesti dal titolare in chat, applicati all'avvio dell'app.

Ogni fix ha un marcatore in `impostazioni` per essere eseguito UNA VOLTA SOLA:
così se il titolare in futuro riattiva a mano un dipendente, un riavvio non
riapplica la cessazione. Quando un fix risulta applicato in produzione, la sua
voce si può rimuovere da questo modulo.
"""
import logging
from datetime import datetime, timezone

from app.hr.database import Database

logger = logging.getLogger(__name__)


async def applica_fix_avvio():
    """Fix una-tantum in ordine di richiesta (ognuno col suo marcatore)."""
    # 29/07/2026 — Lubrano Di Diego Cristian non più in carico
    await _cessa_per_nome("startup_fix_lubrano_cessato", "lubrano")
    await _fix_nome_carotenuto()
    # 29/07/2026 — Dias Mahathelge Kris non più in forza
    await _cessa_per_nome("startup_fix_dias_cessato", "dias")
    # 31/07/2026 — Moscato Emanuele sparito dalle liste (pagina TFR): va rimesso attivo
    await _riattiva_per_nome("startup_fix_moscato_attivo", "moscato", "MSCMNL88R26F839C")


async def _cessa_per_nome(fix_id: str, pattern: str):
    """Cessa i dipendenti ancora attivi il cui nome contiene 'pattern' (sparisce
    da Turni e da tutte le liste attive), con lo stesso iter del pulsante 'Cessa'
    in Anagrafica (evento DIPENDENTE_CESSATO). Una volta sola per fix_id."""
    try:
        db = Database.get_db()
        if await db.impostazioni.find_one({"id": fix_id}):
            return
        oggi = datetime.now(timezone.utc).date().isoformat()
        adesso = datetime.now(timezone.utc).isoformat()
        cessati = []
        async for d in db.dipendenti.find(
                {"merged_into": {"$exists": False},
                 "$or": [{"cognome": {"$regex": pattern, "$options": "i"}},
                         {"nome": {"$regex": pattern, "$options": "i"}},
                         {"nome_completo": {"$regex": pattern, "$options": "i"}}]},
                {"_id": 0}):
            if (d.get("stato") or "") == "cessato":
                continue
            nome = d.get("nome_completo") or f"{d.get('cognome', '')} {d.get('nome', '')}".strip()
            await db.dipendenti.update_one({"id": d["id"]}, {"$set": {
                "stato": "cessato", "attivo": False,
                "data_dimissione": oggi, "cessato_il": adesso,
                "motivo_cessazione": "non più in carico (richiesta titolare)",
            }})
            try:
                from app.hr.services.event_bus import propagate_event, EventTypes
                await propagate_event(EventTypes.DIPENDENTE_CESSATO, {
                    "dipendente_id": d["id"], "nome_completo": nome,
                    "data_cessazione": oggi,
                }, db, source_module="startup_fix", user="system")
            except Exception as e:
                logger.warning(f"Fix {fix_id}: evento cessazione non propagato per {nome}: {e}")
            cessati.append(nome)
        await db.impostazioni.update_one(
            {"id": fix_id},
            {"$set": {"id": fix_id, "done": True, "applicato_il": adesso, "cessati": cessati}},
            upsert=True)
        logger.info(f"Fix {fix_id}: cessati {cessati}" if cessati
                    else f"Fix {fix_id}: nessun dipendente attivo trovato, marcato come applicato")
    except Exception as e:
        logger.warning(f"Fix {fix_id} non riuscito (non blocca l'avvio): {e}")


async def _riattiva_per_nome(fix_id: str, pattern: str, codice_fiscale: str = ""):
    """Rimette 'attivo' un dipendente sparito dalle liste (le pagine di gestione
    mostrano solo stato == 'attivo'). Cerca prima per codice fiscale, poi per nome;
    se il record risulta accorpato per errore a un altro (merged_into), lo sgancia.
    Una volta sola per fix_id, così una futura cessazione fatta apposta non viene annullata."""
    try:
        db = Database.get_db()
        if await db.impostazioni.find_one({"id": fix_id}):
            return
        adesso = datetime.now(timezone.utc).isoformat()
        doc = None
        if codice_fiscale:
            doc = await db.dipendenti.find_one(
                {"codice_fiscale": codice_fiscale, "merged_into": {"$exists": False}}, {"_id": 0})
        if not doc:
            doc = await db.dipendenti.find_one(
                {"merged_into": {"$exists": False},
                 "$or": [{"cognome": {"$regex": pattern, "$options": "i"}},
                         {"nome_completo": {"$regex": pattern, "$options": "i"}}]},
                {"_id": 0})
        sganciato = False
        if not doc and codice_fiscale:
            # Ultimo tentativo: record accorpato per errore a un duplicato.
            doc = await db.dipendenti.find_one({"codice_fiscale": codice_fiscale}, {"_id": 0})
            sganciato = doc is not None
        esito = "non trovato"
        if doc:
            nome = doc.get("nome_completo") or f"{doc.get('cognome', '')} {doc.get('nome', '')}".strip()
            if doc.get("stato") == "attivo" and not sganciato:
                esito = f"{nome}: già attivo (stato invariato)"
            else:
                update = {"$set": {"stato": "attivo", "attivo": True},
                          "$unset": {"data_dimissione": "", "cessato_il": "",
                                     "motivo_cessazione": ""}}
                if sganciato:
                    update["$unset"]["merged_into"] = ""
                await db.dipendenti.update_one({"id": doc["id"]}, update)
                esito = f"{nome}: riattivato (stato precedente: {doc.get('stato') or '—'}" \
                        + (", sganciato da accorpamento)" if sganciato else ")")
        await db.impostazioni.update_one(
            {"id": fix_id},
            {"$set": {"id": fix_id, "done": True, "applicato_il": adesso, "esito": esito}},
            upsert=True)
        logger.info(f"Fix {fix_id}: {esito}")
    except Exception as e:
        logger.warning(f"Fix {fix_id} non riuscito (non blocca l'avvio): {e}")


async def _fix_nome_carotenuto():
    """29/07/2026 — refuso in anagrafica: 'CARATENUTO' va corretto in
    'CAROTENUTO ANTONELLA' (cognome CAROTENUTO, nome ANTONELLA)."""
    try:
        db = Database.get_db()
        fix_id = "startup_fix_nome_carotenuto"
        if await db.impostazioni.find_one({"id": fix_id}):
            return
        adesso = datetime.now(timezone.utc).isoformat()
        corretti = []
        async for d in db.dipendenti.find(
                {"merged_into": {"$exists": False},
                 "$or": [{"cognome": {"$regex": "caratenuto", "$options": "i"}},
                         {"nome": {"$regex": "caratenuto", "$options": "i"}},
                         {"nome_completo": {"$regex": "caratenuto", "$options": "i"}}]},
                {"_id": 0}):
            await db.dipendenti.update_one({"id": d["id"]}, {"$set": {
                "cognome": "CAROTENUTO", "nome": "ANTONELLA",
                "nome_completo": "CAROTENUTO ANTONELLA",
            }})
            corretti.append(d.get("nome_completo") or f"{d.get('cognome', '')} {d.get('nome', '')}".strip())
        await db.impostazioni.update_one(
            {"id": fix_id},
            {"$set": {"id": fix_id, "done": True, "applicato_il": adesso, "corretti": corretti}},
            upsert=True)
        if corretti:
            logger.info(f"Fix avvio: corretti in CAROTENUTO ANTONELLA: {corretti}")
        else:
            logger.info("Fix avvio: nessun 'Caratenuto' trovato, marcato come applicato")
    except Exception as e:
        logger.warning(f"Fix nome Carotenuto non riuscito (non blocca l'avvio): {e}")
