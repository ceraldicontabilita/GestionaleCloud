# Patch chat-8 — Fix reload continuo + router duplicati

## BUG CRITICO (causa reload continuo dell'app)

### frontend/src/main.jsx
**Sostituisce:** `frontend/src/main.jsx`

**Problema:** `LearningMachine` viene usata nelle route (righe 191-192) ma non è mai importata con `lazy()`. Questo causa un `ReferenceError` a runtime che fa crashare il router React → React Router rimonta tutto → loop infinito di reload. L'intera app risulta inutilizzabile.

**Fix applicato:** Aggiunta riga:
```js
const LearningMachine = lazy(() => import("./pages/LearningMachine.jsx"));
```
subito dopo l'import di `TracciabilitaPage`.

---

## BUG MEDIO (endpoint duplicati nel backend)

### app/main.py
**Sostituisce:** `app/main.py`

**Problema 1:** `settings_router` era registrato due volte:
- `app.include_router(settings_router.router, prefix="/api", ...)` ← RIMOSSA
- `app.include_router(settings_router.router, prefix="/api/settings", ...)` ← MANTENUTA

**Problema 2:** I router Tracciabilità erano registrati due volte:
- Primo blocco `# --- Tracciabilita HACCP ---` (22 router, riga ~351) ← RIMOSSO
- Secondo blocco `_TR_ROUTERS` (43 router, riga ~480) ← MANTENUTO (più completo)

---

## Come applicare
1. Copia `main.jsx` → `frontend/src/main.jsx`
2. Copia `main.py` → `app/main.py`
3. Rebuild frontend + restart backend
