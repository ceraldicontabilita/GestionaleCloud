# Audit di Sicurezza — Backend `app/` (GestionaleCloud)

_Audit canonico Fase D, 13/07/2026. Sola lettura, nessuna modifica al codice._

**Nota trasversale**: il sistema è di fatto **mono-utente admin**. Sia il login
email (`app/routers/auth.py`) sia il PIN (`app/routers/pin_login.py`) rilasciano
**sempre** un JWT con `role: "admin"`. Molti controlli vanno letti in quest'ottica.

## Riepilogo per gravità

### P0 — Critico
Nessun problema P0 isolato, **ma la combinazione** SECRET_KEY non obbligatoria +
fallback deterministico da MONGO_URL + CORS wildcard con credenziali + rate
limiting inattivo sul login costituisce un rischio aggregato molto alto di
compromissione dell'autenticazione. Trattare i tre come massima priorità.

### P1 — Importante
1. **SECRET_KEY** non obbligatoria e fallback deterministico prevedibile derivato
   dall'URI Mongo → forgiabilità JWT (`config.py:34,266-270,341-358`).
2. **CORS wildcard + credentials**: `["*"]` con `allow_credentials=True` e auth via
   cookie (`config.py:44-46,293-306`; `main.py:155-163`).
3. **Rate limiting inattivo**: slowapi configurato ma mai applicato (manca
   `SlowAPIMiddleware`/`@limiter.limit`); login email senza lockout
   (`main.py:165-174`; `auth.py:92`).
4. **Autorizzazioni**: ruoli esistono ma ogni login è admin e molti endpoint
   distruttivi non usano `get_current_admin_user` (`auth.py:108`,
   `pin_login.py:195`, `dependencies.py:104`).
5. **Ponte ERP pubblico se manca il secret**: `POST /api/erp/ponte/fattura-ricevuta`
   whitelistato dall'auth; se `ERP_BRIDGE_SECRET` non è impostato accetta scritture
   con solo un warning (`erp_bridge.py:83-90`).
6. **Regex injection / ReDoS su endpoint pubblici**: `public_api.py:754-796,815,851`
   con parametro `q` non `re.escape`-ato.

### P2 — Igiene
1. Fail-fast disattivato di default e connessione DB non bloccante
   (`config.py:341`; `main.py:32-35`).
2. Upload senza limite di dimensione e ZIP ricorsivo senza limiti
   (`fatture_upload.py:997,945-981`; `MAX_UPLOAD_SIZE_MB` definito ma non usato).
3. Audit log incompleto: login, cambio password e delete massivi non finiscono in
   `audit_log` (`admin.py`, `admin_rollback.py:223`, `auth_service.py`).
4. Regex non-escaped nei repository e servizi interni (`supplier_repository.py:211`,
   `employee_repository.py:150`, `invoice_repository.py:374`, `warehouse_repository.py:277`,
   `warehouse_helpers.py:318-410`, `riconciliazione_smart.py:289`,
   `riconciliazione_completa.py:51`, `bonifici_module/associazioni.py:358`).
5. Durata token incoerente: login email 7 giorni vs regola "1 ora" (`auth.py:29`).
6. Password admin confrontata in chiaro con `==` e email/identità di default
   hardcoded (`auth.py:20,35`; `config.py:176`).
7. Whitelist auth per prefisso troppo ampia: `/api/auth/` e `/api/public/`
   (`authentication.py:62-67`).
8. Default `DB_NAME` divergenti (`config.py:28` = `azienda_erp_db` vs `239,286`
   = `Gestionale`).

## Dettaglio per punto

### 1. SECRET_KEY — PARZIALE (tendente a PROBLEMA)
- `SECRET_KEY: Optional[str] = None` (`config.py:34`): l'app parte anche senza.
- Fallback deterministico debole: `sha256("ceraldi-jwt-fallback::" + MONGO_URL)`
  (`config.py:266-270`). Chi conosce/deduce l'URI Mongo può ricalcolare la chiave
  e forgiare JWT admin.
- Fail-fast solo se `FAIL_FAST_SECRETS` attivo E `ENVIRONMENT=production`
  (`config.py:341-358`); di default non fallisce.
- **Fix**: SECRET_KEY obbligatoria (fail-fast incondizionato in produzione),
  rimuovere il fallback derivato dall'URI.

### 2. FAIL_FAST — PARZIALE
- `validate_startup()` (`config.py:330-375`, chiamato da `main.py:37`) copre solo
  SECRET_KEY e URI. Disattivo di default. `connect_db()` in try/except che ingoia
  l'errore (`main.py:32-35`): parte anche con DB down.
- **Fix**: fail-fast di default in produzione, includere fallimento DB.

### 3. DB_NAME / MONGO_URL — PARZIALE
- URI `Optional = None` (`config.py:26-27`). Nessuna credenziale hardcoded. Default
  `DB_NAME` divergente (`config.py:28` vs `239,286`).
- **Fix**: URI obbligatorio, uniformare `DB_NAME`.

### 4. AUTENTICAZIONE — OK (con riserve)
- Middleware globale `AuthenticationMiddleware` (`authentication.py:79`, montato
  `main.py:176-178`). JWT HS256, `algorithms=[settings.ALGORITHM]` (niente
  `alg:none`), scadenza 60 min scorrevole.
- Positivo: `/api/f24-public/` rimosso dalla whitelist (`authentication.py:69-76`).
- Riserve: whitelist per prefisso `/api/auth/` e `/api/public/` troppo ampia;
  token email da 7 giorni (`auth.py:29`) incoerente coi 60 min del middleware.
- **Fix**: whitelist a path espliciti; allineare durata token.

### 5. AUTORIZZAZIONI — PROBLEMA (P1)
- `get_current_admin_user` esiste (`dependencies.py:104-108`) ma usato in pochi
  punti; ogni login è `role:"admin"` (`auth.py:108`, `pin_login.py:195`). Endpoint
  distruttivi come `DELETE /api/fatture/all` (`fatture_upload.py:1243`) senza dep admin.
- **Fix**: documentare il mono-utente oppure ruoli reali + proteggere i distruttivi.

### 6. UPLOAD FILE — PARZIALE
- Estensione validata (`fatture_upload.py:994,1201-1213`). **Nessun limite di
  dimensione**: `await file.read()` intero in memoria (`997,1199`); ZIP ricorsivo
  senza limiti (`945-981`). `MAX_UPLOAD_SIZE_MB` (`config.py:51`) non applicato.
- **Fix**: limite dimensione (streaming) + limiti su file estratti da ZIP.

### 7. CORS — PROBLEMA (P1)
- `CORS_ORIGINS="*"`, `ALLOW_CREDENTIALS=True` (`config.py:44-46`);
  `get_cors_origins()` ritorna `["*"]` (`config.py:293-306`); montato con
  `allow_credentials` (`main.py:155-163`). Con auth via cookie httponly è rischio
  concreto (Origin riflesso). Difesa residua: `samesite="lax"`.
- **Fix**: mai `"*"` con `allow_credentials=True`; lista esplicita di origin.

### 8. RATE LIMITING — PROBLEMA (P1)
- `Limiter(default_limits=["200/minute"])` + handler (`main.py:165-174`) ma
  **manca `SlowAPIMiddleware` e nessun `@limiter.limit`**: i limiti non si
  applicano. Login email senza lockout (`auth.py:92`). Unica difesa reale: lockout
  in-memory sul PIN (`pin_login.py:75-105`, non condiviso tra worker).
- **Fix**: `SlowAPIMiddleware` + limite stringente su `/api/auth/login` e `pin-login`.

### 9. AUDIT LOG — PARZIALE
- `audit_logger.log_evento` su collection `audit_log`, usato da event bus e alcuni
  router (16 file). **Non copre** login riusciti/falliti (solo `logger`,
  `auth_service.py:189,199,213`) né delete massivi (`admin_rollback.py:223`,
  `admin.py:159-190`, `fatture_upload.py:1243`).
- **Fix**: audit_log per login, cambio password, operazioni distruttive (con utente+IP).

### 10. SEGRETI NEL CODICE — PARZIALE
- Nessun segreto hardcoded. `.env` in `.gitignore` (`.gitignore:46-53`).
- Minori: `ADMIN_EMAIL` fallback hardcoded (`auth.py:20`, `pin_login.py:50`);
  `ADMIN_PASSWORD` confrontata con `==` in chiaro (`auth.py:35`).
- **Fix**: preferire `ADMIN_PASSWORD_HASH` (bcrypt) + confronto costante-tempo.

### 11. ENDPOINT DISTRUTTIVI — PARZIALE
- Buoni: `admin_rollback` richiede periodo esplicito + admin (`169-237`);
  `DELETE /api/fatture/all` richiede `?confirm=CONFERMA_ELIMINAZIONE` (`1243-1256`)
  ma senza dep admin; `reset_collections` protegge `users`/`settings` (`admin.py:163-190`).
- Problema: ponte ERP aperto se manca il secret (vedi P1 #5).
- **Fix**: ponte ERP fail-closed (401) senza secret; dep admin su `DELETE /api/fatture/all`.

### 12. INJECTION — PARZIALE
- Niente `$where`/`eval`/`mapReduce` con input utente. Regex non-escaped: vedi P1 #6
  (endpoint pubblici) e P2 #4 (interni). Buon esempio: `fatture_upload.py:247` usa
  `re.escape`.
- **Fix**: `re.escape()` su tutti i valori utente usati come `$regex`, priorità a `public_api`.
