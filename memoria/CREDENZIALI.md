# Credenziali — Ceraldi ERP
> Template di riferimento | Le credenziali reali sono nel file `backend/.env`
> NON committare mai credenziali reali nel repository

---

## ⚠️ AVVISO SICUREZZA

Questo file contiene **solo placeholder** — NON le credenziali reali.
Le credenziali reali vanno in `backend/.env` (file escluso dal versionamento via `.gitignore`).

---

## 1. GitHub

```
Repository: github.com/ceraldicontabilita/gestionale2
Branch: main
Token PAT: [GITHUB_PERSONAL_ACCESS_TOKEN]
```

---

## 2. MongoDB Atlas

```
URI: mongodb+srv://[USER]:[PASSWORD]@cluster0.vofh7iz.mongodb.net/
Database: azienda_erp_db
Cluster: cluster0.vofh7iz
```

**Variabili .env:**
```env
MONGO_URL=mongodb+srv://[USER]:[PASSWORD]@cluster0.vofh7iz.mongodb.net/
DB_NAME=azienda_erp_db
```

---

## 3. PEC Aruba (Fatture SDI)

```
Email: fatturazioneceraldi@pec.it
IMAP: imaps.pec.aruba.it:993
SMTP: smtps.pec.aruba.it:465
```

**Variabili .env:**
```env
ARUBA_PEC_HOST=imaps.pec.aruba.it
ARUBA_PEC_USER=fatturazioneceraldi@pec.it
ARUBA_PEC_PASSWORD=[PASSWORD_PEC]
```

---

## 4. Gmail (Cedolini e documenti)

```
Email: ceraldigroupsrl@gmail.com
IMAP: imap.gmail.com:993
SMTP: smtp.gmail.com:587
Tipo password: App Password Google (16 caratteri, 4 gruppi separati da spazi)
```

**Variabili .env:**
```env
IMAP_USER=ceraldigroupsrl@gmail.com
IMAP_PASSWORD=[APP_PASSWORD_16_CHARS]
```

> L'App Password Google si genera su: account.google.com → Sicurezza → Password per le app.
> Da usare solo se l'autenticazione a 2 fattori è attiva.

---

## 5. Admin ERP

```
Auth: DISABILITATA (AUTH_DISABLED=true)
Accesso: diretto senza login
JWT Secret: [JWT_SECRET_64_CHARS] (generare con: openssl rand -hex 32)
```

**Variabili .env:**
```env
AUTH_DISABLED=true
JWT_SECRET=[JWT_SECRET]
```

---

## 6. PIN Tracciabilità (Reparti)

I PIN dei reparti sono configurati direttamente nell'app HACCP (ceraldiapp.it).
Non sono variabili d'ambiente del gestionale.

---

## 7. PIN Operatori (Dipendenti)

I PIN dei dipendenti sono salvati in formato bcrypt nella collection `dipendenti` in MongoDB.
Non vanno salvati in chiaro — usare solo hash bcrypt.

```python
import bcrypt
pin_hash = bcrypt.hashpw("1234".encode(), bcrypt.gensalt()).decode()
# Salvare pin_hash nel campo dipendente.pin
```

---

## 8. OpenAPI Imprese (Camera di Commercio)

```
Servizio: openapi.it (dati imprese italiane)
```

**Variabili .env:**
```env
OPENAPI_COMPANY_TOKEN=[TOKEN_OPENAPI]
```

---

## 9. Claude / Emergent (AI)

```
Servizio: Claude API (Anthropic) via piattaforma Emergent
```

**Variabili .env:**
```env
EMERGENT_LLM_KEY=[LLM_KEY]
```

---

## Template .env Completo

```env
# Database
MONGO_URL=mongodb+srv://[USER]:[PASSWORD]@cluster0.vofh7iz.mongodb.net/
DB_NAME=azienda_erp_db

# Email Gmail
IMAP_USER=ceraldigroupsrl@gmail.com
IMAP_PASSWORD=[APP_PASSWORD]

# PEC Aruba
ARUBA_PEC_HOST=imaps.pec.aruba.it
ARUBA_PEC_USER=fatturazioneceraldi@pec.it
ARUBA_PEC_PASSWORD=[PASSWORD_PEC]

# Auth (disabilitata)
AUTH_DISABLED=true
JWT_SECRET=[SECRET_64_CHARS]

# API esterne
OPENAPI_COMPANY_TOKEN=[TOKEN]
EMERGENT_LLM_KEY=[KEY]
```

---

*Template aggiornato: Aprile 2026*
