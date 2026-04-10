"""
EVENT BUS — Ceraldi ERP
=======================
Il Bus degli Eventi è il cuore del sistema relazionale.
Garantisce che ogni operazione importante scateni automaticamente
tutte le reazioni necessarie, nell'ordine giusto, senza dimenticare nulla.

COME FUNZIONA:
1. Un'azione pubblica un evento:  await bus.publish("fattura.importata", payload)
2. Il bus cerca tutti gli handler registrati per quel tipo di evento
3. Li chiama in ordine di priorità
4. Se un handler fallisce → lo riprova fino a 3 volte
5. Logga ogni successo/fallimento in eventi_log
6. Se fallisce 3 volte → crea segnalazione urgente per l'admin

TIPI DI EVENTO:
  fattura.importata         → quando arriva una fattura XML
  fattura.pagata            → quando una fattura viene marcata come pagata
  cedolino.importato        → quando arriva un cedolino PDF
  estratto_conto.importato  → quando viene caricato un estratto conto bancario
  corrispettivi.importati   → quando vengono importati i corrispettivi
  documento.ricevuto        → quando arriva un documento via email
  fornitore.creato          → quando viene creato un nuovo fornitore
  fornitore.aggiornato      → quando viene aggiornato un fornitore
  ingrediente.prezzo_cambiato → quando cambia il prezzo di un ingrediente

COME REGISTRARE UN HANDLER:
  from app.core.event_bus import bus

  @bus.on("fattura.importata", priority=10)
  async def handler_magazzino(payload: dict, db):
      # fai qualcosa con i dati della fattura
      ...

COME PUBBLICARE UN EVENTO:
  await bus.publish("fattura.importata", payload=fattura_dict, db=database)
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class EventBus:
    """Bus degli eventi centrale del sistema Ceraldi ERP."""

    def __init__(self):
        # Registry: tipo_evento → lista di (priority, nome, handler_func)
        self._handlers: Dict[str, List[tuple]] = {}

    def on(self, event_type: str, priority: int = 50, name: str = None):
        """
        Decoratore per registrare un handler su un tipo di evento.

        Args:
            event_type: Tipo di evento (es. "fattura.importata")
            priority:   Ordine di esecuzione (più basso = prima). Default 50.
            name:       Nome descrittivo dell'handler (default: nome funzione)

        Uso:
            @bus.on("fattura.importata", priority=10)
            async def handler_magazzino(payload, db):
                ...
        """
        def decorator(func: Callable):
            handler_name = name or func.__name__
            if event_type not in self._handlers:
                self._handlers[event_type] = []
            self._handlers[event_type].append((priority, handler_name, func))
            # Ordina per priorità ogni volta che si aggiunge un handler
            self._handlers[event_type].sort(key=lambda x: x[0])
            logger.debug(f"[EventBus] Registrato: {handler_name} su '{event_type}' (priority={priority})")
            return func
        return decorator

    def register(self, event_type: str, func: Callable, priority: int = 50, name: str = None):
        """Versione non-decoratore di on(). Utile per registrazioni dinamiche."""
        handler_name = name or func.__name__
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append((priority, handler_name, func))
        self._handlers[event_type].sort(key=lambda x: x[0])

    async def publish(
        self,
        event_type: str,
        payload: Dict[str, Any],
        db=None,
        save_to_db: bool = True,
        max_retries: int = 3,
    ) -> Dict[str, Any]:
        """
        Pubblica un evento e chiama tutti gli handler registrati.

        Args:
            event_type:   Tipo di evento (es. "fattura.importata")
            payload:      Dizionario con i dati dell'evento
            db:           Istanza database MongoDB
            save_to_db:   Se True, salva l'evento e i risultati in MongoDB
            max_retries:  Numero massimo di tentativi per handler in errore

        Returns:
            Dizionario con risultati per ogni handler
        """
        event_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        risultati = {
            "event_id":   event_id,
            "event_type": event_type,
            "timestamp":  now,
            "handlers":   {},
            "successi":   0,
            "fallimenti": 0,
        }

        handlers = self._handlers.get(event_type, [])

        if not handlers:
            logger.debug(f"[EventBus] Nessun handler per '{event_type}'")
            return risultati

        logger.info(f"[EventBus] Evento '{event_type}' → {len(handlers)} handler(s)")

        # Salva evento in MongoDB (se richiesto)
        evento_doc = None
        if save_to_db and db is not None:
            try:
                evento_doc = {
                    "id":           event_id,
                    "tipo":         event_type,
                    "payload":      payload,
                    "processato":   False,
                    "handlers_ok":  [],
                    "handlers_err": [],
                    "created_at":   now,
                }
                await db["eventi_sistema"].insert_one(evento_doc.copy())
            except Exception as e:
                logger.warning(f"[EventBus] Impossibile salvare evento in DB: {e}")

        # Esegui ogni handler in ordine di priorità
        for priority, handler_name, handler_func in handlers:
            tentativo = 0
            successo = False
            ultimo_errore = None

            while tentativo < max_retries and not successo:
                tentativo += 1
                try:
                    if asyncio.iscoroutinefunction(handler_func):
                        result = await handler_func(payload=payload, db=db)
                    else:
                        result = handler_func(payload=payload, db=db)

                    risultati["handlers"][handler_name] = {
                        "status":   "ok",
                        "tentativi": tentativo,
                        "result":   result,
                    }
                    risultati["successi"] += 1
                    successo = True
                    logger.info(f"[EventBus] ✅ {handler_name} completato (tentativo {tentativo})")

                except Exception as e:
                    ultimo_errore = str(e)
                    logger.warning(
                        f"[EventBus] ⚠️  {handler_name} fallito (tentativo {tentativo}/{max_retries}): {e}"
                    )
                    if tentativo < max_retries:
                        await asyncio.sleep(0.5 * tentativo)  # backoff

            if not successo:
                risultati["handlers"][handler_name] = {
                    "status":    "error",
                    "tentativi": max_retries,
                    "error":     ultimo_errore,
                }
                risultati["fallimenti"] += 1
                logger.error(f"[EventBus] ❌ {handler_name} fallito dopo {max_retries} tentativi")

                # Crea segnalazione urgente se l'handler critico fallisce
                if db is not None:
                    try:
                        await db["agenti_segnalazioni"].insert_one({
                            "id":          str(uuid.uuid4()),
                            "agente":      "EventBus",
                            "tipo":        "urgente",
                            "titolo":      f"Handler '{handler_name}' fallito su evento '{event_type}'",
                            "descrizione": (
                                f"L'handler '{handler_name}' ha fallito {max_retries} volte "
                                f"sull'evento '{event_type}' (ID: {event_id}). "
                                f"Ultimo errore: {ultimo_errore}. "
                                f"I dati potrebbero essere incompleti."
                            ),
                            "azione":      "Admin → Agenti → verifica segnalazioni urgenti",
                            "letta":       False,
                            "risolta":     False,
                            "dati": {
                                "event_id":     event_id,
                                "event_type":   event_type,
                                "handler_name": handler_name,
                                "errore":       ultimo_errore,
                            },
                            "created_at": datetime.now(timezone.utc).isoformat(),
                        })
                    except Exception:
                        pass

        # Aggiorna stato evento in MongoDB
        if save_to_db and db is not None and evento_doc is not None:
            try:
                await db["eventi_sistema"].update_one(
                    {"id": event_id},
                    {"$set": {
                        "processato":        True,
                        "handlers_ok":       [h for h, r in risultati["handlers"].items() if r["status"] == "ok"],
                        "handlers_err":      [h for h, r in risultati["handlers"].items() if r["status"] == "error"],
                        "processed_at":      datetime.now(timezone.utc).isoformat(),
                        "successi":          risultati["successi"],
                        "fallimenti":        risultati["fallimenti"],
                    }}
                )
            except Exception as e:
                logger.warning(f"[EventBus] Impossibile aggiornare stato evento: {e}")

        return risultati

    def list_handlers(self) -> Dict[str, List[str]]:
        """Restituisce tutti gli handler registrati per tipo di evento."""
        return {
            event_type: [name for _, name, _ in handlers]
            for event_type, handlers in self._handlers.items()
        }

    def handlers_count(self) -> int:
        """Numero totale di handler registrati."""
        return sum(len(h) for h in self._handlers.values())


# Istanza singleton — importa questa nei tuoi moduli
bus = EventBus()
