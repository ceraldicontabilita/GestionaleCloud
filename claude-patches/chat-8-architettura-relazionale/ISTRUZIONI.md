# PATCH Chat 8 — Architettura Relazionale
## Data: 22 Aprile 2026

---

## Cosa contiene questa patch

6 nuovi servizi backend in `app/services/` che costituiscono le fondamenta
del sistema relazionale. Nessun router viene modificato in questa patch.

### File nuovi da copiare

```
app/services/__init__.py
app/services/event_bus.py
app/services/alert_engine.py
app/services/audit_logger.py
app/services/deduplica.py
app/services/partite_aperte_engine.py
app/services/riconciliazione_engine.py
```

**Destinazione**: copiare la cartella `app/services/` nel repo.
Se `app/services/` non esiste, crearla.

---

## Modifiche manuali da fare in file esistenti

### 1. Aggiungere in `app/db_collections.py` (in fondo, prima dei commenti)

```python
# ===========================================
# SISTEMA RELAZIONALE — Chat 8
# ===========================================

# Partite Aperte (scadenziario materializzato)
COLL_PARTITE_APERTE = "partite_aperte"

# Riconciliazione Match (N:M tra movimenti e partite)
COLL_RICONCILIAZIONI_MATCH = "riconciliazioni_match"

# Audit Log unificato
COLL_AUDIT_LOG = "audit_log"

# Alert Definitions (catalogo codici)
COLL_ALERT_DEFINITIONS = "alert_definitions"
```

### 2. Aggiungere indici in `app/database.py` (dentro `_create_indexes`)

```python
# --- Partite Aperte ---
await _safe_index("partite_aperte", "id", unique=True, name="idx_pa_id")
await _safe_index("partite_aperte", [("stato", 1), ("tipo", 1)], name="idx_pa_stato_tipo")
await _safe_index("partite_aperte", [("controparte_id", 1), ("stato", 1)], name="idx_pa_controparte")
await _safe_index("partite_aperte", [("documento_id", 1), ("tipo", 1)], name="idx_pa_doc_tipo")
await _safe_index("partite_aperte", "data_scadenza", name="idx_pa_scadenza")

# --- Riconciliazioni Match ---
await _safe_index("riconciliazioni_match", "id", unique=True, name="idx_rm_id")
await _safe_index("riconciliazioni_match", [("movimento_id", 1)], name="idx_rm_movimento")
await _safe_index("riconciliazioni_match", [("partita_id", 1)], name="idx_rm_partita")
await _safe_index("riconciliazioni_match", [("stato", 1)], name="idx_rm_stato")

# --- Audit Log ---
await _safe_index("audit_log", "id", unique=True, name="idx_audit_id")
await _safe_index("audit_log", [("entita_id", 1), ("timestamp", -1)], name="idx_audit_entita")
await _safe_index("audit_log", [("modulo", 1), ("timestamp", -1)], name="idx_audit_modulo")

# --- Alert Definitions ---
await _safe_index("alert_definitions", "codice", unique=True, name="idx_alertdef_codice")

# --- Alerts (miglioramento indici esistenti) ---
await _safe_index("alerts", "id", unique=True, sparse=True, name="idx_alerts_id")
await _safe_index("alerts", [("codice", 1), ("entita_id", 1), ("stato", 1)], name="idx_alerts_codice_entita")
await _safe_index("alerts", [("modulo", 1), ("stato", 1)], name="idx_alerts_modulo_stato")
```

### 3. Aggiungere in `main.py` (dopo `await Database.connect_db()`)

```python
# Inizializza event bus
from app.services.event_bus import register_all_handlers
register_all_handlers()

# Seed alert definitions
from app.services.alert_engine import seed_alert_definitions
await seed_alert_definitions(Database.get_db())
```

---

## Come verificare che funziona

1. Avviare il backend
2. Verificare nei log: "Event bus pronto: X handler registrati"
3. Verificare nei log: "Seed alert_definitions: 48 codici"
4. In MongoDB, controllare che la collezione `alert_definitions` contenga 48 documenti
5. Testare manualmente:
   ```python
   from app.services.alert_engine import genera_alert, risolvi_alert
   db = Database.get_db()
   
   # Genera un alert
   await genera_alert("FORN_MP_MANCANTE", "test_id", "fornitori", "Test", db)
   
   # Verifica che esiste
   alert = await db["alerts"].find_one({"codice": "FORN_MP_MANCANTE", "entita_id": "test_id"})
   
   # Risolvilo
   await risolvi_alert("FORN_MP_MANCANTE", "test_id", db)
   ```

---

## Documenti di riferimento

- `PIANO_LAVORO_RELAZIONALE.md` — architettura completa, catalogo alert, mappa moduli
- `DIARIO.md` — cronologia sviluppo
- `README.md` — aggiornato con sezione architettura relazionale
- `memoria/INDEX.md` — aggiornato: collezioni corrette, servizi core, regole critiche 16 punti
- `memoria/PRD.md` — aggiornato: stato implementazione, architettura relazionale
- `memoria/LOGICA_OPERATIVA.md` — aggiunto sezione 5 "Sistema relazionale a eventi" con mappa
- `memoria/BACKLOG.md` — aggiunta nota collegamento al piano relazionale

**Tutti i file .md vanno copiati nelle rispettive posizioni nel repo:**
- `README.md` → root del repo
- `PIANO_LAVORO_RELAZIONALE.md` → root del repo
- `DIARIO.md` → root del repo
- `memoria/*.md` → `memoria/` nel repo

---

## Prossima patch (Chat 9)

Handler eventi per Fase 2: Fatture ↔ Fornitori ↔ Prima Nota.
Quando una fattura XML viene importata, il sistema automaticamente:
1. Crea/aggiorna il fornitore
2. Crea la partita aperta
3. Genera alert se metodo pagamento mancante
4. Instrada verso cassa o banca
5. Invia righe merce al magazzino
