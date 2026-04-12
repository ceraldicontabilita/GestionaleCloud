# Istruzioni per GitHub Copilot — Ceraldi ERP

## Panoramica
ERP gestionale italiano per Ceraldi Group S.R.L. (P.IVA: 04523831214) — Bar/Pasticceria a Napoli.
Sistema NON multi-utente. Documentazione completa in `/memoria/`.

## Stack Tecnologico
- **Backend**: Python 3.x, FastAPI 0.110.1, Motor 3.3.1 (MongoDB async), APScheduler
- **Frontend**: React 18, Vite, lucide-react
- **Auth**: JWT — **DISABILITATA** (`AUTH_DISABLED=true`) — accesso diretto
- **Database**: MongoDB Atlas, DB: `azienda_erp_db`
- **Email**: IMAPClient (sincrono in `asyncio.to_thread()`)

## Architettura Backend
- Entry point: `backend/server.py` → `from app.main import app`
- App: `app/main.py` (FastAPI, ~75 router)
- Database: `app/database.py` → `Database.get_db()`
- Collections: `app/database/collections.py` ← usare SEMPRE queste costanti

## Regola Design Frontend (ASSOLUTA)
**NO Tailwind, NO Shadcn.** Usare ESCLUSIVAMENTE CSS inline con costanti da `frontend/src/lib/utils.js`:
```js
import { COLORS, STYLES, SPACING } from '../../lib/utils';
```
Icone: `lucide-react` only. NO emoji nel codice.

## Pattern Critici

### IMAP — sempre in thread
```python
# ✅ CORRETTO
raw = await asyncio.to_thread(funzione_sincrona_imap, user, password)

# ❌ SBAGLIATO — blocca il server
imap = imaplib.IMAP4_SSL("imap.gmail.com")  # BLOCCA!
```

### MongoDB — pattern corretti
```python
docs = await db["collection"].find({}, {"_id": 0}).to_list(None)
from datetime import datetime, timezone
now = datetime.now(timezone.utc)  # NON datetime.utcnow()
```

### React — hooks in sub-componenti
```jsx
// ✅ Ogni sub-componente che usa isMobile DEVE importarlo
const SubComponente = () => {
  const isMobile = useIsMobile();  // obbligatorio!
  return <div />;
};
```

## Regole Contabili Italiane (FONDAMENTALI)
- I **corrispettivi** sono l'UNICA fonte di RICAVI (collection: `corrispettivi`)
- Le **fatture ricevute** sono COSTI passivi (collection: `invoices`)
- I **cedolini** gestiscono buste paga (collection: `cedolini`)
- Il conto economico segue l'**art. 2425 c.c.**
- **Auto aziendali**: deducibilità 20%, IVA 40% (Art. 164 TUIR)
- **Telefonia**: deducibilità 80%, IVA 50% (Art. 102 TUIR)
- **TFR**: quota = `retribuzione / 13.5`, rivalutazione = `1.5% + 75% ISTAT`

## Collection MongoDB Canoniche
```
dipendenti (34)         ← HR — USARE QUESTA, non employees
cedolini (1658)         ← buste paga
invoices (224)          ← fatture passive SDI
suppliers (328)         ← fornitori (modulo principale)
prima_nota_cassa        ← prima nota cassa
prima_nota_banca        ← prima nota banca
corrispettivi (1114)    ← UNICA fonte ricavi
estratto_conto_movimenti ← movimenti bancari
f24_unificato (68)      ← F24
```

## File di Riferimento
- `memoria/INDEX.md` — Indice completo documentazione
- `memoria/ARCHITETTURA.md` — Struttura architetturale
- `memoria/LOGICA_OPERATIVA.md` — Logica business e regole critiche
- `memoria/REGOLE_CONTABILI.md` — Regole fiscali italiane
- `memoria/DESIGN_SYSTEM.md` — Design system frontend
- `memoria/DEBITO_TECNICO.md` — File da eliminare e collection duplicate

## Note Importanti
- NON eliminare `backend/server.py` — è l'entry point Supervisor/uvicorn
- NON commitare credenziali reali — usare `backend/.env` (escluso da git)
- Endpoint API: sempre sotto `/api/` (es. `/api/prima-nota/cassa`)
- Usare Pydantic v2 per modelli e schemi
- Commenti e nomi variabili in italiano o inglese tecnico
