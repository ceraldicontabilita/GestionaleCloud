"""
Event Bus Sincrono — Gestionale Ceraldi Group
==============================================
Orchestra la comunicazione tra moduli.
Ogni operazione CRUD significativa chiama propagate_event() che
esegue gli handler registrati in modo sincrono.

Utilizzo nei router:
    from app.services.event_bus import propagate_event
    
    # Dopo aver salvato una fattura:
    await propagate_event("fattura.created", {
        "fattura_id": fattura["id"],
        "fornitore_piva": fattura.get("fornitore_piva"),
        "totale": fattura.get("total_amount"),
        ...
    }, db)
"""
import logging
from typing import Dict, Any, List, Callable, Awaitable
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ============================================================
# REGISTRO HANDLER
# ============================================================
# Mappa: event_type -> lista di handler async
_handlers: Dict[str, List[Callable]] = {}


def register_handler(event_type: str, handler: Callable[..., Awaitable]):
    """Registra un handler per un tipo di evento."""
    if event_type not in _handlers:
        _handlers[event_type] = []
    _handlers[event_type].append(handler)
    logger.debug(f"Handler registrato per '{event_type}': {handler.__name__}")


# ============================================================
# TIPI DI EVENTO SUPPORTATI
# ============================================================
class EventTypes:
    """Costanti per i tipi di evento del gestionale."""
    
    # Fatture
    FATTURA_CREATED = "fattura.created"
    FATTURA_UPDATED = "fattura.updated"
    FATTURA_PAGATA = "fattura.pagata"
    FATTURA_DELETED = "fattura.deleted"
    
    # Fornitori
    FORNITORE_CREATED = "fornitore.created"
    FORNITORE_UPDATED = "fornitore.updated"
    
    # F24
    F24_ACQUISITO = "f24.acquisito"
    F24_PAGATO = "f24.pagato"
    F24_RICONCILIATO = "f24.riconciliato"
    
    # Cedolini
    CEDOLINO_IMPORTATO = "cedolino.importato"
    CEDOLINO_PAGATO = "cedolino.pagato"
    CEDOLINO_RICONCILIATO = "cedolino.riconciliato"
    
    # Banca
    MOVIMENTO_BANCA_IMPORTATO = "movimento_banca.importato"
    MOVIMENTO_BANCA_CLASSIFICATO = "movimento_banca.classificato"
    
    # Cassa
    MOVIMENTO_CASSA_CREATO = "movimento_cassa.creato"
    MOVIMENTO_CASSA_CONFERMATO = "movimento_cassa.confermato"
    
    # Corrispettivi
    CORRISPETTIVO_REGISTRATO = "corrispettivo.registrato"
    # Import massivo XML corrispettivi (distinto dal singolo registrato sopra)
    CORRISPETTIVI_IMPORTATI = "corrispettivi.importati"

    # Estratto conto (import massivo movimenti — migrato dal vecchio bus core)
    ESTRATTO_CONTO_IMPORTATO = "estratto_conto.importato"
    
    # Trasferimenti
    TRASFERIMENTO_CREATO = "trasferimento.creato"
    
    # Riconciliazione
    MATCH_CONFERMATO = "match.confermato"
    MATCH_RESPINTO = "match.respinto"
    
    # Dipendenti
    DIPENDENTE_CREATED = "dipendente.created"
    DIPENDENTE_UPDATED = "dipendente.updated"
    DIPENDENTE_CESSATO = "dipendente.cessato"
    
    # Documenti
    DOCUMENTO_ACQUISITO = "documento.acquisito"
    DOCUMENTO_CLASSIFICATO = "documento.classificato"
    DOCUMENTO_INSTRADATO = "documento.instradato"
    
    # Partite
    PARTITA_CREATA = "partita.creata"
    PARTITA_CHIUSA = "partita.chiusa"
    PARTITA_PARZIALE = "partita.parziale"


# ============================================================
# DISPATCHER PRINCIPALE
# ============================================================
async def propagate_event(
    event_type: str,
    payload: Dict[str, Any],
    db,
    source_module: str = "",
    user: str = "sistema"
) -> List[Dict[str, Any]]:
    """
    Propaga un evento a tutti gli handler registrati.
    
    Args:
        event_type: tipo evento (da EventTypes)
        payload: dati dell'evento
        db: repository asincrono Drive/Sheets
        source_module: modulo che ha generato l'evento
        user: utente o "sistema"
    
    Returns:
        Lista di risultati dagli handler
    """
    results = []
    handlers = _handlers.get(event_type, [])
    
    if not handlers:
        logger.debug(f"Nessun handler per evento '{event_type}'")
        return results
    
    # Arricchisci payload con metadati
    event_context = {
        "event_type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_module": source_module,
        "user": user,
        **payload
    }
    
    for handler in handlers:
        try:
            result = await handler(event_context, db)
            if result:
                results.append({
                    "handler": handler.__name__,
                    "success": True,
                    "result": result
                })
        except Exception as e:
            logger.error(
                f"Errore in handler '{handler.__name__}' per evento "
                f"'{event_type}': {e}",
                exc_info=True
            )
            results.append({
                "handler": handler.__name__,
                "success": False,
                "error": str(e)
            })
            # Visibilità sui fallimenti (ereditata dal vecchio bus core, che
            # segnalava gli handler falliti): best-effort, non deve mai
            # bloccare la propagazione degli altri handler. Upsert con
            # contatore: un handler rotto durante un import massivo (es. ZIP
            # di 365 corrispettivi = 365 eventi) produce UNA segnalazione
            # aggiornata, non centinaia di duplicati.
            try:
                await db["agenti_segnalazioni"].update_one(
                    {
                        "tipo": "event_handler_fallito",
                        "evento": event_type,
                        "handler": handler.__name__,
                        "letta": False,
                    },
                    {
                        "$set": {
                            "errore": str(e)[:500],
                            "source_module": source_module,
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        },
                        "$inc": {"occorrenze": 1},
                        "$setOnInsert": {
                            "created_at": datetime.now(timezone.utc).isoformat(),
                        },
                    },
                    upsert=True,
                )
            except Exception:
                pass
    
    logger.info(
        f"Evento '{event_type}' propagato: "
        f"{len(handlers)} handler, "
        f"{sum(1 for r in results if r.get('success'))} ok, "
        f"{sum(1 for r in results if not r.get('success'))} errori"
    )
    
    return results


# ============================================================
# HELPER PER REGISTRAZIONE BATCH
# ============================================================
def register_all_handlers():
    """
    Registra tutti gli handler dei moduli.
    Chiamare all'avvio dell'app (in main.py dopo connect_db).

    Gli handler vengono importati qui per evitare import circolari.
    """
    logger.info("Registrazione handler event bus...")

    # --- Fase 2: Fatture ↔ Fornitori ↔ Prima Nota (Chat 9) ---
    try:
        from app.services.handlers.fattura_handlers import (
            on_fattura_created_crea_partita,
            on_fattura_created_alert_fornitore,
            on_fattura_created_audit,
            on_fattura_created_iva,
            on_fattura_pagata_risolvi,
            on_fornitore_aggiornato_risolvi,
        )
        register_handler(EventTypes.FATTURA_CREATED, on_fattura_created_crea_partita)
        register_handler(EventTypes.FATTURA_CREATED, on_fattura_created_alert_fornitore)
        register_handler(EventTypes.FATTURA_CREATED, on_fattura_created_audit)
        register_handler(EventTypes.FATTURA_CREATED, on_fattura_created_iva)
        from app.services.reconciliation_orchestrator import on_fattura_created_riprocessa
        register_handler(EventTypes.FATTURA_CREATED, on_fattura_created_riprocessa)
        register_handler(EventTypes.FATTURA_PAGATA, on_fattura_pagata_risolvi)
        register_handler(EventTypes.FORNITORE_UPDATED, on_fornitore_aggiornato_risolvi)
    except Exception as e:
        logger.warning(f"Handler fatture non registrati: {e}")

    # NOTA: la "Fase 3: Banca ↔ Riconciliazione" (banca_handlers.py, motore di
    # matching a 4 livelli su MOVIMENTO_BANCA_IMPORTATO/MATCH_CONFERMATO) è
    # stata rimossa: quell'evento non veniva mai propagato dal vero upload
    # estratto conto (PrimaNota.jsx -> /api/estratto-conto-movimenti/import),
    # quindi il motore non aveva mai girato su dati reali. La riconciliazione
    # automatica live è ora unica, in app/services/riconciliazione_bancaria.py
    # — vedi PROMPT_MASTER.md, sezioni 6 e 10.

    # --- Fase 4: F24 (Chat 9c) ---
    try:
        from app.services.handlers.f24_handlers import (
            on_f24_acquisito_crea_partita,
            on_f24_pagato_risolvi,
        )
        register_handler(EventTypes.F24_ACQUISITO, on_f24_acquisito_crea_partita)
        from app.services.reconciliation_orchestrator import on_f24_acquisito_riprocessa
        register_handler(EventTypes.F24_ACQUISITO, on_f24_acquisito_riprocessa)
        register_handler(EventTypes.F24_PAGATO, on_f24_pagato_risolvi)
    except Exception as e:
        logger.warning(f"Handler F24 non registrati: {e}")

    # --- Fase 5: Cedolini (Chat 9c) ---
    try:
        from app.services.handlers.cedolino_handlers import (
            on_cedolino_importato,
            on_cedolino_pagato_risolvi,
        )
        register_handler(EventTypes.CEDOLINO_IMPORTATO, on_cedolino_importato)
        from app.services.reconciliation_orchestrator import on_cedolino_importato_riprocessa
        register_handler(EventTypes.CEDOLINO_IMPORTATO, on_cedolino_importato_riprocessa)
        register_handler(EventTypes.CEDOLINO_PAGATO, on_cedolino_pagato_risolvi)
    except Exception as e:
        logger.warning(f"Handler cedolini non registrati: {e}")

    # Estratto conto: riesamina documenti arrivati prima o dopo la banca.
    try:
        from app.services.reconciliation_orchestrator import on_estratto_conto_importato_riprocessa
        register_handler(EventTypes.ESTRATTO_CONTO_IMPORTATO, on_estratto_conto_importato_riprocessa)
    except Exception as e:
        logger.warning(f"Handler riconciliazione documenti non registrato: {e}")

    # --- Fase 6: Corrispettivi (Chat 9c) ---
    try:
        from app.services.handlers.corrispettivo_handlers import on_corrispettivo_split
        register_handler(EventTypes.CORRISPETTIVO_REGISTRATO, on_corrispettivo_split)
    except Exception as e:
        logger.warning(f"Handler corrispettivi non registrati: {e}")

    # --- Fase 7: Trasferimenti (Chat 9c) ---
    # on_trasferimento_crea_lato_opposto NON è più registrato (17/07/2026):
    # creava entrate fantasma a ogni spostamento cassa/banca di una
    # fattura. La doppia scrittura vera di versamenti/prelievi la fa
    # l'estratto conto (bank/estratto_conto.py, ripara-versamenti-cassa).

    # --- Dipendenti (Chat 9d) ---
    try:
        from app.services.handlers.dipendente_handlers import (
            on_dipendente_created,
            on_dipendente_updated_risolvi,
            on_dipendente_cessato,
        )
        register_handler(EventTypes.DIPENDENTE_CREATED, on_dipendente_created)
        register_handler(EventTypes.DIPENDENTE_UPDATED, on_dipendente_updated_risolvi)
        register_handler(EventTypes.DIPENDENTE_CESSATO, on_dipendente_cessato)
    except Exception as e:
        logger.warning(f"Handler dipendenti non registrati: {e}")

    # --- Magazzino (Chat 9d) ---
    try:
        from app.services.handlers.magazzino_handlers import on_fattura_righe_magazzino
        register_handler(EventTypes.FATTURA_CREATED, on_fattura_righe_magazzino)
    except Exception as e:
        logger.warning(f"Handler magazzino non registrati: {e}")

    # --- Scadenziario fornitori ---
    # Migrato dal vecchio app.core.event_bus: era registrato su "fattura.importata",
    # un evento mai pubblicato nel percorso reale di import fattura (solo questo bus,
    # con FATTURA_CREATED, viene davvero attivato) — la scheda "scadenzario" in
    # GestioneCespiti.jsx (/api/scadenzario-fornitori/) restava quindi vuota per ogni
    # fattura importata. Vedi memoria/moduli/MAGAZZINO.md per lo stesso pattern di bug.
    try:
        from app.handlers.scadenziario import handler_crea_scadenza
        register_handler(EventTypes.FATTURA_CREATED, handler_crea_scadenza)
    except Exception as e:
        logger.warning(f"Handler scadenziario non registrato: {e}")

    # --- Classificazione centro di costo / deducibilità IVA e IRES ---
    # Stesso pattern di migrazione: era su "fattura.importata" (mai pubblicato).
    try:
        from app.handlers.learning import handler_classifica_cdc
        register_handler(EventTypes.FATTURA_CREATED, handler_classifica_cdc)
    except Exception as e:
        logger.warning(f"Handler classificazione CDC non registrato: {e}")

    # --- Controllo IBAN mancante su fornitore nuovo ---
    # Stesso pattern: era su "fornitore.creato" (app.core.event_bus, mai pubblicato).
    try:
        from app.handlers.fornitore import handler_controlla_iban_mancante
        register_handler(EventTypes.FATTURA_CREATED, handler_controlla_iban_mancante)
    except Exception as e:
        logger.warning(f"Handler controllo IBAN non registrato: {e}")

    # --- Auto-cespiti da righe fattura XML ---
    # Richiesta utente 15/07/2026: le attrezzature/impianti individuati nelle
    # fatture XML devono confluire da soli nel registro cespiti, non solo con
    # lo scan manuale "Scan Fatture XML" (che resta per il backfill dello
    # storico importato prima di questo handler).
    try:
        from app.handlers.cespiti import handler_auto_cespite_da_fattura
        register_handler(EventTypes.FATTURA_CREATED, handler_auto_cespite_da_fattura)
    except Exception as e:
        logger.warning(f"Handler auto-cespiti non registrato: {e}")

    # --- Documenti/Inbox (Chat 9d) ---
    try:
        from app.services.handlers.documento_handlers import (
            on_documento_acquisito,
            on_documento_instradato,
        )
        register_handler(EventTypes.DOCUMENTO_ACQUISITO, on_documento_acquisito)
        register_handler(EventTypes.DOCUMENTO_INSTRADATO, on_documento_instradato)
    except Exception as e:
        logger.warning(f"Handler documenti non registrati: {e}")

    # --- Handler migrati dal vecchio bus core (app/core/event_bus.py, rimosso) ---
    # Il vecchio bus aveva una registry separata: gli eventi pubblicati qui non
    # raggiungevano i suoi handler e viceversa. Da questa migrazione esiste UNA
    # SOLA registry. Ordine di registrazione = vecchio ordine di priorità.
    try:
        from app.handlers.prima_nota import handler_prima_nota_cedolino
        from app.handlers.tfr import handler_aggiorna_tfr
        from app.handlers.notifiche import handler_notifica_cedolino

        def _con_nome_dipendente(handler):
            # Il vecchio bus usava "nome_dipendente", i publisher di questo bus
            # usano "dipendente_nome": normalizza senza toccare gli handler.
            async def adapter(event_context, db):
                payload = {**event_context,
                           "nome_dipendente": event_context.get("nome_dipendente")
                           or event_context.get("dipendente_nome") or ""}
                return await handler(payload, db)
            adapter.__name__ = f"{handler.__name__}_adapter"
            return adapter

        # Prima di questa migrazione prima_nota_salari e TFR scattavano SOLO
        # per i cedolini passati da cedolini_manager (doppio publish sui due
        # bus): i cedolini importati via pipeline email/salari_unificati/
        # buste-paga non creavano né il movimento stipendio né la quota TFR.
        # Ora scattano per tutti i canali; gli handler sono idempotenti
        # (anti-duplicato per dipendente+mese+anno).
        register_handler(EventTypes.CEDOLINO_IMPORTATO, _con_nome_dipendente(handler_prima_nota_cedolino))
        register_handler(EventTypes.CEDOLINO_IMPORTATO, handler_aggiorna_tfr)
        register_handler(EventTypes.CEDOLINO_IMPORTATO, _con_nome_dipendente(handler_notifica_cedolino))
    except Exception as e:
        logger.warning(f"Handler cedolini (ex bus core) non registrati: {e}")

    try:
        from app.handlers.estratto_conto import handler_matching_estratto_conto
        register_handler(EventTypes.ESTRATTO_CONTO_IMPORTATO, handler_matching_estratto_conto)
    except Exception as e:
        logger.warning(f"Handler matching estratto conto non registrato: {e}")

    try:
        from app.handlers.corrispettivi import (
            handler_prima_nota_corrispettivi,
            handler_check_coerenza_pos,
        )
        register_handler(EventTypes.CORRISPETTIVI_IMPORTATI, handler_prima_nota_corrispettivi)
        register_handler(EventTypes.CORRISPETTIVI_IMPORTATI, handler_check_coerenza_pos)
    except Exception as e:
        logger.warning(f"Handler corrispettivi importati non registrati: {e}")

    try:
        from app.handlers.fornitore import handler_aggiorna_learning_fornitore
        # Sul vecchio bus era su "fornitore.aggiornato"; qui l'evento canonico
        # è FORNITORE_UPDATED. Con payload scarno (solo id+metodo) l'handler fa
        # skip da solo; quando aggiorna, unisce le keyword senza mai cancellarle.
        register_handler(EventTypes.FORNITORE_UPDATED, handler_aggiorna_learning_fornitore)
    except Exception as e:
        logger.warning(f"Handler learning fornitore non registrato: {e}")


    registered = sum(len(h) for h in _handlers.values())
    logger.info(f"Event bus pronto: {registered} handler registrati per {len(_handlers)} tipi evento")


# ============================================================
# UTILITY: lista eventi registrati (per debug/admin)
# ============================================================
def get_registered_events() -> Dict[str, List[str]]:
    """Ritorna mappa evento -> nomi handler registrati."""
    return {
        event_type: [h.__name__ for h in handlers]
        for event_type, handlers in _handlers.items()
    }
