# 08 — Sistema, Admin, Report e Integrazioni

Documentazione endpoint dei moduli di sistema: autenticazione, amministrazione, configurazione, dashboard/report/export, scadenze/alert/notifiche, operazioni batch e coerenza dati, commercialista, integrazioni esterne (OpenAPI.it, WhatsApp), API pubbliche/alias e dizionario articoli.

Contesto trasversale:
- **Auth**: JWT HS256 firmato con `settings.SECRET_KEY` (env + segreto in `sistema_stato.auth_secret`). Middleware globale `app/middleware/authentication.py` protegge TUTTO `/api/*` salvo `PUBLIC_PATHS`/`PUBLIC_PREFIXES` (tra cui `/api/auth/*`, `/api/public/*`, `/api/f24-public/*`, `/api/openclaw/*`, `/api/enhanced-parser/info`, health, docs). Il token è accettato da header `Authorization: Bearer` o cookie `access_token`; per i WebSocket da query `?token=`.
- I prefissi indicati sono quelli effettivi da `app/router_registry.py`.

---

## auth.py (montato senza prefisso extra: prefisso interno `/api`)
Login/logout single-user admin (credenziali da env `ADMIN_EMAIL` + `ADMIN_PASSWORD` in chiaro o `ADMIN_PASSWORD_HASH` bcrypt). Emette JWT HS256 (7 giorni) con PyJWT e lo salva in cookie httpOnly `access_token` + cookie flag `session_active`. Nessuna collezione MongoDB: utente unico da variabili d'ambiente.

### POST /api/login — login legacy
**Cosa fa**: autentica l'admin con email+password e imposta i cookie di sessione.
**Logica codice**: confronto case-insensitive con `ADMIN_EMAIL`, poi `_check_password` (prima password in chiaro da env, fallback bcrypt); `_make_token` firma JWT con `sub`=email, scadenza 7 giorni; set cookie `access_token` (httpOnly) e `session_active`.
**Note**: NON è nei percorsi pubblici del middleware → senza token la richiesta viene bloccata con 401 prima di arrivare al router: alias di fatto inutilizzabile da utente non loggato (il frontend usa `/api/auth/login`). Cookie con `secure=False` (rischio in produzione HTTPS).

### POST /api/logout — logout legacy
**Cosa fa**: cancella i cookie `access_token` e `session_active`.
**Logica codice**: `response.delete_cookie` sui due cookie; nessun accesso DB.
**Note**: come `/api/login`, non è pubblico nel middleware (serve token per chiamarlo — coerente, ma è un alias legacy di `/api/auth/logout`).

### GET /api/me — utente corrente (legacy)
**Cosa fa**: restituisce l'email dell'utente autenticato.
**Logica codice**: `verify_token` legge il JWT da cookie `access_token` o header Bearer, lo decodifica con `SECRET_KEY` e ritorna `payload["sub"]`; 401 se assente/scaduto/invalido.

### GET /api/auth/verify — verifica sessione (frontend AuthContext)
**Cosa fa**: verifica che la sessione sia attiva e ritorna l'utente per il frontend.
**Logica codice**: stesso `verify_token`; risponde `{ok, user:{email, name:"Admin", role:"admin"}, email}` con ruolo admin hardcoded.
**Note**: pubblico per il middleware (prefisso `/api/auth/`), ma la verifica JWT è fatta internamente dall'endpoint.

### POST /api/auth/login — login (alias usato dal frontend)
**Cosa fa**: come `/api/login` ma ritorna anche `access_token` e oggetto `user` nel body.
**Logica codice**: stessa validazione email/password e stessi cookie; il commento nel codice segnala che il token nel body è ignorato dal frontend (usa il cookie).
**Note**: pubblico (in `PUBLIC_PATHS` e prefisso `/api/auth/`). Logica duplicata riga per riga con `/api/login`.

### POST /api/auth/logout — logout (alias frontend)
**Cosa fa**: cancella i cookie di sessione.
**Logica codice**: identico a `/api/logout`.
**Note**: pubblico (prefisso `/api/auth/`).

## pin_login.py (prefisso `/api/auth`)
Login rapido via PIN per l'app mobile: il PIN viene confrontato come SHA-256 con l'hash in env `PIN_HASH_ADMIN` (se assente il PIN login è disattivato). Anti brute-force in-memory per IP (8 tentativi → lock 60s). Entrambi gli endpoint sono pubblici per il middleware (prefisso `/api/auth/`).

### POST /api/auth/pin-login — login via PIN (mobile)
**Cosa fa**: scambia un PIN numerico valido con un JWT admin + cookie di sessione.
**Logica codice**: rate-limit per IP (`_is_locked`/`_register_failure`); valida PIN (numerico, 4-12 cifre); SHA-256 vs `PIN_HASH_ADMIN`; cerca l'utente in `users` (username "ceraldi" via `UserRepository`, fallback primo `role:"admin"`, poi primo `is_active:true`); firma JWT (jose) con `sub`=user_id, `role`, `auth_method:"pin"`, scadenza `ACCESS_TOKEN_EXPIRE_MINUTES`; aggiorna `last_login`; set cookie `access_token` httpOnly.
**Note**: endpoint pubblico. Il doppio fallback può concedere token admin al "primo utente attivo" se non esiste alcun admin in `users` (rischio, mitigato dal fatto che il PIN resta il gate).

### GET /api/auth/pin-login/health — health check PIN login
**Cosa fa**: verifica che il router PIN sia registrato e se il PIN è configurato.
**Logica codice**: nessun DB; ritorna `configured: bool(PIN_HASH_ADMIN)`, username admin e durata token.
**Note**: pubblico; espone lo username admin di riferimento (informativo).

## admin.py (prefisso `/api/admin`)
Funzioni amministrative: riepilogo dashboard admin, statistiche DB, saldi apertura anno, gestione collezioni (lista/reset) e utility di bonifica dati fatture. Alcuni endpoint usano `Depends(get_current_user)`, altri si affidano solo al middleware globale.

### GET /api/admin/dashboard-summary — riepilogo pagina admin
**Cosa fa**: ritorna in un'unica chiamata contatori, alert e stato sync per la pagina admin.
**Logica codice**: `asyncio.gather` di 5 blocchi: conteggi (`invoices`, `fornitori`, `dipendenti`, `prima_nota_cassa`, `prima_nota_banca`, `f24_unificato`), alert non letti/non risolti (`alerts`), segnalazioni agenti non lette (`agenti_segnalazioni`), "sync status" (in realtà semplici count delle stesse collezioni), promemoria commercialista attivo nei primi 10 giorni del mese (calcolo mese precedente, nessun DB).
**Note**: ogni blocco ha try/except che degrada a valori vuoti (errori DB silenziosi); `health` è hardcoded "healthy".

### GET /api/admin/stats — statistiche database
**Cosa fa**: conta i documenti delle collezioni principali.
**Logica codice**: `count_documents({})` su `invoices`, `fornitori`, `warehouse_inventory`, `dipendenti`, `prima_nota_cassa`, `prima_nota_banca`, `f24_unificato`; richiede `get_current_user`.
**Note**: sottoinsieme duplicato di `dashboard-summary`.

### GET /api/admin/year-opening-balances/{year} — saldi di apertura anno
**Cosa fa**: legge i saldi di apertura per l'anno indicato.
**Logica codice**: `opening_balances.find_one({year})` senza `_id`; default `{year, balances:{}}` se assente.

### PUT /api/admin/year-opening-balances/{year} — aggiorna saldi apertura
**Cosa fa**: salva/aggiorna i saldi di apertura di un anno.
**Logica codice**: upsert su `opening_balances` con `$set` del body + `year` + `updated_at`; nessuna validazione sulla struttura del body.

### GET /api/admin/collections — elenco collezioni
**Cosa fa**: lista tutte le collezioni MongoDB con conteggio documenti.
**Logica codice**: `list_collection_names()` poi `count_documents({})` per ciascuna (loop sequenziale).

### POST /api/admin/reset-collections — svuota collezioni selezionate
**Cosa fa**: cancella TUTTI i documenti delle collezioni passate in query `selected`.
**Logica codice**: protegge `users`, `system_settings`, `settings`; per ogni collezione esistente esegue `delete_many({})`; ritorna conteggi eliminati. Parametro `delete_files` accettato ma MAI usato.
**Note**: operazione distruttiva irreversibile; `delete_files` è ignorato (il nome promette una pulizia file che non avviene).

### GET /api/admin/fatture-stats — statistiche metodi pagamento fatture
**Cosa fa**: riepiloga i metodi di pagamento delle fatture e quante ne sono prive.
**Logica codice**: count totale su `invoices`; aggregate `$group` per `metodo_pagamento`; count fatture con metodo assente/null/vuoto.

### POST /api/admin/fatture-set-metodo-pagamento — imposta metodo pagamento mancante
**Cosa fa**: assegna in massa un metodo di pagamento alle fatture che non ne hanno.
**Logica codice**: `update_many` su `invoices` (filtro metodo assente/null/"") con `$set` di `metodo_pagamento` (default "Bonifico") e timestamp; la "conferma doppia" citata nel docstring è demandata al frontend, il backend non la verifica.

### DELETE /api/admin/cleanup-trattenute-disciplinari — bonifica one-shot rollback Task 4
**Cosa fa**: elimina i record orfani delle trattenute disciplinari (sistema rollbackato, PR #50).
**Logica codice**: count + `delete_many` su `trattenute_dipendenti` con `source:"trattenute_disciplinari"`; idempotente, non tocca i record legacy con altri `source`.
**Note**: endpoint one-shot legacy, candidato a rimozione dopo l'esecuzione.

## admin_export.py (montato su `/api` + prefisso interno `/admin/export` → `/api/admin/export`)
Download e lista dei file di export generati sul filesystem del server. Nessun accesso MongoDB.

### GET /api/admin/export — lista file export disponibili
**Cosa fa**: elenca i file presenti nella directory export con dimensione, data e URL di download.
**Logica codice**: scandisce `ALLOWED_DIRS = ["/tmp/uploads"]` con `os.listdir`/`os.stat`; ordina per data modifica desc.
**Note**: il docstring del modulo e di `_safe_path` dicono `/app/uploads/` ma il codice usa SOLO `/tmp/uploads` — docstring non veritiero.

### GET /api/admin/export/{filename} — download file export
**Cosa fa**: scarica un singolo file di export (CSV/JSON/PDF/XLSX).
**Logica codice**: `_safe_path` anti path-traversal (rifiuta `/`, `\`, `..`; `realpath` deve restare sotto `/tmp/uploads`); `FileResponse` con media-type dall'estensione.

## config.py (prefisso `/api/config`)
Micro-router per la configurazione email "storica" salvata nella collection `config` (documento `{type:"email"}`). Due endpoint, entrambi con `get_current_user`. Convive sullo stesso prefisso con `configurazioni.py` senza collisioni di path.

### GET /api/config/email — legge config email
**Cosa fa**: restituisce la configurazione SMTP.
**Logica codice**: `find_one` su `config` con `{type:"email"}` senza `_id`; default con campi SMTP vuoti.
**Note**: restituisce il documento integrale: eventuale password SMTP salvata viene esposta in chiaro (nessun mascheramento, a differenza di `configurazioni.py`).

### PUT /api/config/email — aggiorna config email
**Cosa fa**: salva la configurazione SMTP.
**Logica codice**: body libero `Dict`, forza `type:"email"` e `updated_at`, `update_one` upsert su `config`. Nessuna validazione di schema.
**Note**: terzo sistema di configurazione email del progetto (vedi `configurazioni.py` e `settings_router.py`) — sovrapposizione funzionale su collezioni diverse.

## configurazioni.py (prefisso `/api/config`)
Configurazioni di sistema: account email IMAP multipli (collection `email_accounts`) e parole chiave per il filtro documenti (doc `{tipo:"parole_chiave"}` in `system_config`). Nessun endpoint usa `get_current_user` (protezione solo dal middleware).

### GET /api/config/email-accounts — lista account email
**Cosa fa**: elenca gli account IMAP configurati con password mascherata.
**Logica codice**: `find` su `email_accounts` (max 100, senza `_id`); sostituisce `app_password` con `app_password_masked` (ultime 4 cifre); se la collection è vuota crea e inserisce un account di default copiando `EMAIL_USER`/`EMAIL_APP_PASSWORD` dall'ambiente.
**Note**: GET con side-effect di scrittura (insert account default); la app password di `.env` viene persistita in chiaro nel DB.

### POST /api/config/email-accounts — crea account email
**Cosa fa**: aggiunge un nuovo account IMAP.
**Logica codice**: valida con Pydantic `EmailAccountInput`; rifiuta email duplicata (400); genera `id` uuid4, `created_at`, `is_env_default:False`; `insert_one` su `email_accounts`; risposta con password mascherata.
**Note**: `app_password` salvata in chiaro nel DB.

### PUT /api/config/email-accounts/{account_id} — aggiorna account email
**Cosa fa**: modifica parzialmente un account esistente.
**Logica codice**: `find_one` per `id` (404 se assente); `EmailAccountUpdate` con `exclude_unset` e scarto dei `None`; `update_one` con `updated_at`.

### DELETE /api/config/email-accounts/{account_id} — elimina account email
**Cosa fa**: rimuove un account IMAP.
**Logica codice**: 404 se inesistente; 400 se `is_env_default` (account default non eliminabile); `delete_one` su `email_accounts`.

### POST /api/config/email-accounts/{account_id}/test — test connessione IMAP
**Cosa fa**: verifica il login IMAP dell'account e conta le email in INBOX.
**Logica codice**: legge l'account da `email_accounts` (password in chiaro); `imaplib.IMAP4_SSL` + `login` + `search ALL`; errori restituiti come `{success:false}` con HTTP 200.
**Note**: chiamata IMAP sincrona e bloccante dentro handler async (blocca l'event loop; `settings_router._test_imap` invece usa `asyncio.to_thread`).

### GET /api/config/parole-chiave — lista parole chiave
**Cosa fa**: restituisce le parole chiave per categoria (generale, fatture, f24, buste_paga).
**Logica codice**: `find_one` su `system_config` `{tipo:"parole_chiave"}`; se assente inserisce un set di default e lo restituisce.
**Note**: anche qui GET con side-effect di scrittura.

### PUT /api/config/parole-chiave — sostituisce parole di una categoria
**Cosa fa**: rimpiazza l'intera lista di parole di una categoria.
**Logica codice**: query params `categoria` + `parole` (lista); valida la categoria contro whitelist; `update_one` upsert con `$set`.

### POST /api/config/parole-chiave/aggiungi — aggiunge una parola
**Cosa fa**: aggiunge una singola parola a una categoria.
**Logica codice**: `$addToSet` sulla categoria + `updated_at`, upsert su `system_config`.
**Note**: non valida `categoria` (a differenza della PUT): consente di iniettare campi arbitrari nel documento di configurazione.

### DELETE /api/config/parole-chiave/rimuovi — rimuove una parola
**Cosa fa**: toglie una parola da una categoria.
**Logica codice**: `$pull` sulla categoria + `updated_at` (senza upsert); nessuna validazione di `categoria`.
**Note**: il modello Pydantic `ParolaChiaveInput` è definito ma mai usato (codice morto).

## settings.py (prefisso `/api/settings`)
Impostazioni applicative aziendali (collection `settings`, doc `{type:"app_settings"}`), logo aziendale (collection `settings_assets` + copie file in `frontend/public/`) e preferenze utente (collection `user_preferences`). Tutti gli endpoint tranne `GET /logo` richiedono `get_current_user`.

### GET /api/settings — legge impostazioni app
**Cosa fa**: restituisce le impostazioni aziendali (ragione sociale, P.IVA, valuta…).
**Logica codice**: `find_one` su `settings` `{type:"app_settings"}` senza `_id`; default hardcoded (IVA 22%, EUR); eccezioni ingoiate con `{}`.

### PUT /api/settings — aggiorna impostazioni app
**Cosa fa**: salva le impostazioni aziendali.
**Logica codice**: body libero `Dict`; forza `type`, `updated_at`, `updated_by` (=`current_user["user_id"]`); `update_one` upsert su `settings`. Nessuna validazione di schema.

### GET /api/settings/logo — logo aziendale
**Cosa fa**: restituisce l'immagine del logo.
**Logica codice**: legge `settings_assets` `{id:"logo_principale"}`, decodifica base64 e risponde con il media type salvato (cache 24h); fallback sui file `frontend/public/logo-ceraldi.png|logo_ceraldi.png`; 404 se nessuno.
**Note**: senza `get_current_user` ma comunque dietro il middleware (non pubblico).

### POST /api/settings/logo — upload logo
**Cosa fa**: carica un nuovo logo (PNG/JPG/SVG) e sincronizza i file pubblici del frontend.
**Logica codice**: valida `content_type` (ma in caso di tipo non valido risponde 200 con `{"error":...}`, non 4xx); salva base64 in `settings_assets` con upsert; `_write_logo_files` scrive i file pubblici (best-effort). Richiede `get_current_user`.
**Note**: nessun limite di dimensione file; l'SVG in fallback viene servito come `image/png`.

### GET /api/settings/user-preferences — preferenze utente
**Cosa fa**: legge le preferenze del singolo utente.
**Logica codice**: `find_one` su `user_preferences` per `user_id` del token; default `{user_id, document_keywords:[]}`.

### PUT /api/settings/user-preferences — salva preferenze utente
**Cosa fa**: aggiorna le preferenze del singolo utente.
**Logica codice**: body libero; forza `user_id` dal token e `updated_at`; `update_one` upsert su `user_preferences`.

## settings_router.py (prefisso `/api/settings`)
Impostazioni Gmail/IMAP salvate nella stessa collection `settings` di `settings.py` ma con chiave diversa (`{chiave:"gmail"}`). Nessun `get_current_user` (solo middleware). Registrato prima di `settings.py` sullo stesso prefisso; i path non collidono.

### GET /api/settings/gmail — legge impostazioni Gmail
**Cosa fa**: restituisce utente/host IMAP e se esiste una password (mai la password).
**Logica codice**: `find_one` su `settings` `{chiave:"gmail"}`; fallback alle env `IMAP_USER`/`IMAP_HOST`/`IMAP_PASSWORD` con `sorgente:"env"`.

### POST /api/settings/gmail — salva impostazioni Gmail
**Cosa fa**: salva credenziali Gmail e testa subito la connessione.
**Logica codice**: valida `imap_user` obbligatorio e app password ≥8 caratteri (spazi rimossi); upsert su `settings`; poi `_test_imap` (IMAP4_SSL in `asyncio.to_thread`); risponde `ok` o `salvato_con_errore` (salva comunque anche se il test fallisce).
**Note**: `gmail_app_password` persistita in chiaro nel DB.

### POST /api/settings/gmail/test — test connessione Gmail
**Cosa fa**: verifica il login IMAP con le credenziali salvate (o da env).
**Logica codice**: legge `settings` `{chiave:"gmail"}` con fallback env; `_test_imap` async (thread); ritorna `{ok, messaggio|error}` sempre con HTTP 200.

## reports/dashboard.py (prefisso `/api/dashboard`)
KPI e statistiche per la dashboard principale: riepiloghi annuali, trend mensili entrate/uscite, confronto anno su anno, stato riconciliazione e bilancio istantaneo. Nessun endpoint usa `Depends(get_current_user)` (due usano `get_optional_user`): protezione delegata al middleware. 8 endpoint effettivi (non 9), tutti GET.

### GET /api/dashboard/summary — riepilogo dashboard
**Cosa fa**: conteggi e totale fatture dell'anno per le card della dashboard, con cache 60s.
**Logica codice**: legge `invoices` (count + aggregate `$sum` su `total_amount`/`importo_totale`), `suppliers`, `warehouse_products`, `employees`, `estratto_conto_movimenti` (count `riconciliato:True`); 6 query in parallelo con `asyncio.gather`; cache in-memory da `app.middleware.performance` (`dashboard_summary_{anno}`); filtro date su `invoice_date`/`data` come stringhe ISO.
**Note**: la description dichiara "no auth required - public endpoint" ma è FALSO: il path non è in whitelist, il JWT è richiesto. In caso di eccezione restituisce tutti zeri con HTTP 200 (errore mascherato).

### GET /api/dashboard/kpi — KPI dashboard
**Cosa fa**: conta fatture e fornitori totali e somma l'importo complessivo delle fatture.
**Logica codice**: `invoices` (count + aggregate `$sum $total_amount` senza filtri data), `suppliers` (count); auth opzionale via `get_optional_user`.
**Note**: valori placeholder: `pending_payments` e `monthly_revenue` sempre 0; `monthly_expenses` = totale storico di TUTTE le fatture (etichetta fuorviante). Duplica concettualmente `/api/analytics/kpi` con logica più povera. Errori → zeri.

### GET /api/dashboard/stats — statistiche dashboard
**Cosa fa**: conta le fatture create nel mese corrente; il resto è vuoto.
**Logica codice**: `invoices` count su `created_at >= inizio mese`; auth opzionale.
**Note**: quasi-stub: `monthly_suppliers`, `overdue_invoices`, `pending_reconciliations` sempre 0 e `chart_data` sempre vuoto, nonostante la description prometta "detailed statistics".

### GET /api/dashboard/trend-mensile — trend mensile entrate/uscite
**Cosa fa**: serie mensile di entrate (corrispettivi), uscite (fatture), IVA debito/credito e saldi, con totali, medie e picchi annuali.
**Logica codice**: 2 aggregate: `corrispettivi` (mese estratto con `$substr` da `data`, somma `totale`/`totale_iva`) e `invoices` (`data_ricezione` con fallback `invoice_date`, somma `total_amount`/`importo_totale` e `iva`/`importo_iva`); saldi/medie/picchi calcolati in Python; errori delle singole aggregate solo loggati (mesi a zero).
**Note**: versione ottimizzata (2 query) dello stesso trend calcolato da `/api/analytics/dashboard` con ~36 query; le due implementazioni usano campi diversi (lordo vs imponibile) e possono dare numeri diversi.

### GET /api/dashboard/spese-per-categoria — spese per categoria
**Cosa fa**: top 10 categorie di spesa per il grafico a torta, con percentuali.
**Logica codice**: aggregate su `estratto_conto_movimenti` (`tipo:"uscita"`, `data` regex `^anno`, group su `categoria`, `$abs` importo); fallback su `invoices` raggruppate per `supplier_name` se l'estratto conto è vuoto; tronca nomi >25 caratteri.
**Note**: il fallback mischia semantiche (fornitore ≠ categoria) senza segnalarlo nel payload.

### GET /api/dashboard/confronto-annuale — confronto con anno precedente
**Cosa fa**: confronta entrate, uscite, saldo e numero fatture tra `anno` e `anno-1` con variazioni percentuali.
**Logica codice**: per ciascun anno: aggregate `corrispettivi` (somma `totale`), aggregate + count `invoices` (regex `^anno` su `data_ricezione`/`invoice_date`); helper `calc_variazione` (vecchio=0 → 100%).

### GET /api/dashboard/stato-riconciliazione — stato riconciliazione
**Cosa fa**: percentuali di fatture pagate e salari riconciliati nell'anno, con importi pagati/da pagare.
**Logica codice**: `invoices`: 2 count (totali e `pagato:True`) + aggregate importi raggruppati su `pagato`; `prima_nota_salari`: 2 count su `anno` e `riconciliato:True`; percentuale globale = media semplice delle due percentuali.

### GET /api/dashboard/bilancio-istantaneo — bilancio istantaneo
**Cosa fa**: calcola ricavi, costi, saldo IVA e utile lordo dell'anno dalle fatture/corrispettivi caricati.
**Logica codice**: aggregate su `corrispettivi` (regex `^anno` su `data`, esclude `entity_status:"deleted"`), `invoices_emesse` e `invoices` (match esteso su `anno` int/str, `invoice_date`, `data_ricezione`, `data_documento`; catene di `$ifNull` sui doppi nomi campo IT/EN); più 2 count.
**Note**: solo qui viene escluso `entity_status:"deleted"` (dai soli corrispettivi). Ricavi/costi a lordo IVA: l'"utile lordo" non è confrontabile con `/api/analytics/*` (imponibili). Errore → payload di zeri con campo `error` (HTTP 200).

## reports/exports.py (prefisso `/api/exports`)
Export Excel "strutturati" (5 endpoint GET) via layer servizi (`InvoiceServiceV2`, `WarehouseService`, `EmployeeService`) e helper `excel_exporter` (richiede openpyxl → 500 se assente). Tutti richiedono `Depends(get_current_user)`. Montato sullo stesso prefisso di `simple_exports.py` (nessuna collisione di path, ma funzioni duplicate).

### GET /api/exports/excel — export generico (stub)
**Cosa fa**: restituisce un file `export.xlsx` completamente vuoto (0 byte).
**Logica codice**: nessun DB; `StreamingResponse(io.BytesIO(b""))` con content-type xlsx.
**Note**: endpoint morto/stub: produce un file non apribile come xlsx valido.

### GET /api/exports/invoices/excel — export fatture Excel
**Cosa fa**: esporta fino a 10.000 fatture in Excel con filtri opzionali data/stato pagamento.
**Logica codice**: `InvoiceServiceV2.get_all(skip=0, limit=10000)` su `invoices`; filtri applicati in Python sui campi `date` e `payment_status`; `excel_exporter.export_invoices()`.
**Note**: i filtri usano il campo `date`, ma le fatture usano `invoice_date`/`data_ricezione`: con `start_date`/`end_date` valorizzati il filtro rischia di escludere tutto.

### GET /api/exports/warehouse/excel — export inventario Excel
**Cosa fa**: esporta l'inventario magazzino in Excel, con filtro categoria e opzione solo sottoscorta.
**Logica codice**: `WarehouseService.list_products(user_id, category)` su `warehouse_products`; filtro `stock < min_stock` in Python; `excel_exporter.export_warehouse_inventory()`.

### GET /api/exports/employees/excel — export dipendenti Excel
**Cosa fa**: esporta i dipendenti (default solo attivi) in Excel.
**Logica codice**: `EmployeeService.list_employees(user_id, active_only)` su `employees`; `excel_exporter.export_employees()`.
**Note**: duplicato funzionale di `GET /api/exports/employees` (simple_exports) con fonte dati diversa (`employees` vs `dipendenti`).

### GET /api/exports/accounting/excel — report contabile mensile Excel
**Cosa fa**: riepilogo mensile fatture (imponibile, IVA, totale, pagato/da pagare) in Excel.
**Logica codice**: valida `month` formato `YYYY-MM` (400); `get_all(limit=10000)` su `invoices`, filtro in Python `inv.get('date','').startswith(month)`; totali da `total_amount`/`vat_amount`, pagate = `payment_status=='paid'`; `excel_exporter.export_accounting_report()`.
**Note**: stesso problema del campo `date` inesistente: il report mensile rischia di essere sempre a zero.

## reports/simple_exports.py (prefisso `/api/exports`)
Export "semplificati" (8 endpoint GET): query dirette MongoDB senza layer servizi, output Excel via pandas/openpyxl oppure JSON grezzo con `?format=json`. Nessuna dipendenza auth negli handler (solo middleware, dichiarato correttamente nel docstring).

### GET /api/exports/invoices — export fatture
**Cosa fa**: esporta tutte le fatture (max 10.000) in xlsx o JSON.
**Logica codice**: `db["invoices"].find({},{"_id":0}).sort("data_fattura",-1)`; DataFrame pandas → `ExcelWriter` (foglio "Fatture"); colonne di default se vuoto.
**Note**: ordina su `data_fattura`, campo non usato altrove (`invoice_date`/`data_ricezione`): ordinamento probabilmente inefficace. Duplica `GET /api/exports/invoices/excel`.

### GET /api/exports/suppliers — export fornitori
**Cosa fa**: esporta tutti i fornitori (max 5.000) in xlsx o JSON.
**Logica codice**: `db["fornitori"].find(...).sort("denominazione",1)`; foglio "Fornitori".
**Note**: legge `fornitori`, mentre dashboard.py conta `Collections.SUPPLIERS`: possibile doppia collezione fornitori (IT/EN).

### GET /api/exports/products — export prodotti magazzino
**Cosa fa**: esporta i prodotti magazzino (max 10.000) in xlsx o JSON.
**Logica codice**: `db["warehouse_products"].find(...).sort("nome",1)`; foglio "Prodotti".
**Note**: duplica `GET /api/exports/warehouse/excel`; report_pdf `/magazzino` invece legge `warehouse_inventory` (terza collezione).

### GET /api/exports/employees — export dipendenti
**Cosa fa**: esporta i dipendenti (max 1.000) in xlsx o JSON.
**Logica codice**: `db["dipendenti"].find(...).sort("nome_completo",1)`; foglio "Dipendenti".
**Note**: legge `dipendenti` mentre `exports.py` usa `employees`: fonti incoerenti per lo stesso dato.

### GET /api/exports/cash — export Prima Nota Cassa
**Cosa fa**: esporta i movimenti di cassa (max 10.000) in xlsx o JSON, con range date opzionale.
**Logica codice**: `prima_nota_cassa` con filtro `data $gte/$lte` da `data_da`/`data_a`; sort `data` desc; foglio "Prima Nota Cassa".

### GET /api/exports/bank — export Prima Nota Banca
**Cosa fa**: come `/cash` ma sulla banca.
**Logica codice**: identica su `prima_nota_banca`; foglio "Prima Nota Banca".

### GET /api/exports/salari — export Prima Nota Salari
**Cosa fa**: esporta i movimenti salari (max 10.000) in xlsx o JSON, con range date opzionale.
**Logica codice**: identica su `prima_nota_salari`; foglio "Prima Nota Salari".

### GET /api/exports/riconciliazione — export riconciliazione bancaria
**Cosa fa**: esporta i movimenti banca con stato riconciliazione, più foglio di riepilogo con percentuale.
**Logica codice**: `prima_nota_banca` (filtro opzionale `riconciliato != True` con `solo_non_riconciliati`); arricchisce in Python `stato_riconciliazione`, `data_riconciliazione`, `riferimento_estratto_conto`; xlsx a 2 fogli o JSON con contatori.
**Note**: nonostante il nome, non incrocia `estratto_conto_movimenti`: usa solo i flag già presenti sui movimenti banca.

## reports/report_pdf.py (prefisso `/api/report-pdf`)
Generazione report PDF con ReportLab (A4, stili custom, helper `format_euro`/`format_date_it`). 4 endpoint GET, tutti `StreamingResponse` PDF in download. Nessuna dipendenza auth negli handler (solo middleware).

### GET /api/report-pdf/mensile — report mensile PDF
**Cosa fa**: PDF mensile con fatture passive, corrispettivi, riepilogo IVA e movimenti cassa/banca.
**Logica codice**: 4 find con regex `^YYYY-MM`: `invoices` (`invoice_date`), `corrispettivi` (`data`/`data_trasmissione`), `prima_nota_cassa`, `prima_nota_banca` (max 1.000 ciascuno); totali in Python; entrate/uscite per segno di `importo`; 4 tabelle + footer.
**Note**: l'IVA dei corrispettivi, se manca il campo `iva`, è stimata come `totale/11` (IVA fissa 10% hardcoded anche nell'etichetta): imprecisa con aliquote miste. Il docstring promette anche le "Scadenze" che NON sono nel PDF.

### GET /api/report-pdf/dipendenti — report dipendenti PDF
**Cosa fa**: PDF con elenco dipendenti attivi, contratto e stato libretto sanitario.
**Logica codice**: `employees` (filtro `status in [attivo, active, None]`, max 500), `contratti_dipendenti` (`stato:"attivo"`), `libretti_sanitari`; join in Python su `dipendente_id`; flag "SCADUTO" se `data_scadenza` < oggi.
**Note**: `anno`/`mese` influenzano solo titolo e filename: le "buste paga se specificato mese" promesse dal docstring non vengono lette.

### GET /api/report-pdf/scadenze — report scadenze PDF
**Cosa fa**: PDF delle scadenze entro N giorni (default 30): fatture da pagare, contratti, libretti sanitari, F24.
**Logica codice**: 4 find (max 100 ciascuno): `invoices` (`data_scadenza <= limite`, `stato_pagamento in [non_pagata, da_pagare, None]`), `contratti_dipendenti` (`data_fine` tra oggi e limite, attivi), `libretti_sanitari` (`data_scadenza <= limite`), `f24_unificato` (`pagato != True`); sezioni rese solo se non vuote; fatture troncate alle prime 20.
**Note**: fatture, libretti e F24 non hanno limite inferiore sulla data: includono anche scaduti da anni.

### GET /api/report-pdf/magazzino — report magazzino PDF
**Cosa fa**: PDF riepilogo magazzino con valore totale e raggruppamento per categoria.
**Logica codice**: `warehouse_inventory.find()` (max 5.000); valore = `prezzi.avg * giacenza`; raggruppamento per `categoria` in Python; tabella ordinata per valore decrescente.
**Note**: legge `warehouse_inventory` mentre dashboard/exports usano `warehouse_products`: se non sincronizzate i numeri divergono.

## reports/analytics.py (prefisso `/api/analytics`)
Analytics di business: ricavi = corrispettivi (imponibile), costi = fatture ricevute meno note credito TD04/TD08 (imponibile). Tutti e 4 gli endpoint GET richiedono `Depends(get_current_user)`.

### GET /api/analytics/dashboard — dashboard analytics
**Cosa fa**: ricavi, costi netti, utile, margine %, trend mensile, top 5 fornitori e distribuzione costi per categoria.
**Logica codice**: aggregate su `corrispettivi` (`totale_imponibile`, `totale`) e `invoices` (2 aggregate escluse/incluse NC via `tipo_documento`, imponibile con fallback `total_amount - iva`); trend con 3 aggregate per mese in loop (~36 query); top fornitori (group `supplier_name`, limit 5) e categorie (group `category`, limit 8) filtrati per anno solo se `year` esplicito.
**Note**: N+1 sul trend; senza `?year=` il trend usa l'anno corrente ma top fornitori/categorie sono su tutto lo storico (payload internamente incoerente). Duplica `/api/dashboard/trend-mensile` con metriche diverse.

### GET /api/analytics/suppliers — analytics fornitori
**Cosa fa**: numero fornitori distinti e top 10 per spesa (imponibile).
**Logica codice**: `invoices.distinct("supplier_name")` con filtro anno opzionale (regex su `invoice_date`/`data_ricezione`); aggregate group su `supplier_name`, escluso `None`, sort desc, limit 10.

### GET /api/analytics/kpi — riepilogo KPI
**Cosa fa**: ricavi, costi netti (fatture - NC), utile, margine % e medie mensili dell'anno.
**Logica codice**: 3 aggregate: `corrispettivi` (`totale_imponibile`), `invoices` senza NC, `invoices` solo NC (TD04/TD08), su range `YYYY-01-01`/`YYYY-12-31`; medie divise per mesi trascorsi.
**Note**: stesso nome route di `GET /api/dashboard/kpi` ma logica completamente diversa: rischio di confusione lato frontend.

### GET /api/analytics/self-repair — diagnostica dati
**Cosa fa**: diagnostica di coerenza dati in sola lettura, nonostante il nome "repair".
**Logica codice**: count su `corrispettivi` (totali e senza `totale_imponibile`), count su `invoices` (senza `imponibile`, warning se >50%), aggregate distribuzione `tipo_documento`; errori raccolti nel payload con `status:"error"`.
**Note**: il nome promette "self-repair" ma NON ripara nulla: solo controlli in lettura.

## scadenze.py (prefisso `/api/scadenze`)
Sistema scadenze fiscali e pagamenti: genera scadenze fiscali fisse italiane (IVA trimestrale, F24 al 16 del mese), deriva scadenze di pagamento dalle fatture, gestisce scadenze personalizzate (CRUD su `notifiche_scadenze`) e calcola la liquidazione IVA trimestrale/mensile. Espone anche un widget riepilogo per la dashboard. 10 endpoint.

### GET /api/scadenze — alias lista scadenze (senza slash)
**Cosa fa**: restituisce tutte le scadenze; alias nascosto (`include_in_schema=False`) di `/tutte`.
**Logica codice**: delega a `get_tutte_scadenze` con gli stessi parametri (`anno`, `mese`, `tipo`, `include_passate`, `limit`).
**Note**: tripla duplicazione: ``, `/` e `/tutte` sono la stessa route.

### GET /api/scadenze/ — alias lista scadenze (con slash)
**Cosa fa**: identico al precedente, per chiamate con slash finale.
**Logica codice**: delega a `get_tutte_scadenze`; anch'esso `include_in_schema=False`.

### GET /api/scadenze/tutte — lista completa scadenze
**Cosa fa**: unisce scadenze fiscali generate, fatture in scadenza e scadenze custom, ordinate per data con statistiche.
**Logica codice**: legge `notifiche_scadenze` (filtro `completata:False` se non `include_passate`) e `invoices` via `_get_fatture_in_scadenza` (scadenza = data fattura + 30 giorni fissi; filtri `pagato≠True`, `status≠paid`, `stato_pagamento∉[pagata,pagato]`); genera scadenze fiscali con `_genera_scadenze_fiscali(anno, mese)` (F24 il 16, IVA nei mesi 3/5/8/11); arricchisce con `giorni_mancanti`/`urgente` e statistiche (urgenti ≤3gg, prossimi 7gg, totale importi); `limit` solo sulla lista.
**Note**: la scadenza fattura è sempre stimata a +30gg dalla data fattura, ignorando i termini reali di pagamento.

### GET /api/scadenze/prossime — prossime scadenze (widget dashboard)
**Cosa fa**: scadenze entro N giorni (default 30), con `prossima_scadenza` in evidenza.
**Logica codice**: genera scadenze fiscali per i mesi coperti dall'intervallo, legge `invoices` (`_get_fatture_in_scadenza`) e `notifiche_scadenze` (`completata:False`, `data_scadenza ≤ limite`); filtra a `[oggi, oggi+giorni]`, ordina, aggiunge `giorni_mancanti`/`urgente`, tronca a `limit`.

### GET /api/scadenze/iva/{anno} — liquidazione IVA trimestrale
**Cosa fa**: calcola per i 4 trimestri IVA a debito, a credito, saldo e importo da versare con date di scadenza (16/5, 20/8, 16/11, 16/3 anno+1).
**Logica codice**: per ogni mese aggrega `corrispettivi` (somma `totale_iva`, regex su `data`) per il debito e `invoices` (somma `iva`, regex su `data_ricezione` o `invoice_date`) per il credito; ritorna anche totale annuo e prossima scadenza.
**Note**: 24 aggregazioni separate; il credito somma l'IVA di tutte le fatture senza distinguere note di credito o esigibilità.

### GET /api/scadenze/iva-mensile/{anno} — liquidazione IVA mensile
**Cosa fa**: come sopra ma mese per mese (versamento il 16 del mese successivo), con saldo progressivo a riporto credito.
**Logica codice**: stesse aggregazioni per ciascuno dei 12 mesi; calcola `saldo_progressivo` cumulato e `da_versare_effettivo` (F24 dovuto solo se il progressivo è > 0), oltre a totali annui.

### POST /api/scadenze/crea — crea scadenza personalizzata
**Cosa fa**: inserisce una scadenza/notifica custom.
**Logica codice**: valida presenza `data_scadenza` e `descrizione` (400); genera `id` uuid4, default `tipo=CUSTOM`, `priorita=media`, `completata=False`; `insert_one` su `notifiche_scadenze`.

### PUT /api/scadenze/completa/{notifica_id} — completa scadenza custom
**Cosa fa**: marca una scadenza custom come completata.
**Logica codice**: `update_one` su `notifiche_scadenze` per `id`, set `completata=True` + `completata_at`; 404 se `modified_count == 0`.

### DELETE /api/scadenze/{notifica_id} — elimina scadenza custom
**Cosa fa**: elimina una scadenza personalizzata.
**Logica codice**: `delete_one` su `notifiche_scadenze` per `id`; 404 se non trovata.
**Note**: route parametrica catch-all alla radice del prefisso.

### GET /api/scadenze/dashboard-widget — riepilogo alert scadenze
**Cosa fa**: contatori compatti per dashboard: fatture da pagare (30gg), contratti in scadenza (60gg), libretti sanitari scaduti/in scadenza, F24 da pagare, scadenze fiscali entro 15gg.
**Logica codice**: `count_documents` su `invoices` (campo persistito `data_scadenza` + `stato_pagamento ∈ [non_pagata, da_pagare, null]`), `contratti_dipendenti` (`data_fine` entro 60gg, `stato=attivo`), `libretti_sanitari`. Il conteggio "F24 da pagare" (righe 642-650) SOMMA DUE collezioni: `f24_unificato` (`data_scadenza ≤ +30gg`, `pagato ≠ True`, alimentata da upload manuale) + `f24_commercialista` (`scadenza ≤ +30gg`, `status ≠ "pagato"`, alimentata dalla scansione email) — il commento nel codice spiega che contando solo la prima gli F24 arrivati via email sparivano dall'alert. Scadenze fiscali via `_genera_scadenze_fiscali` filtrate a 15gg.
**Note**: i due archivi F24 hanno schemi diversi (`pagato`/`data_scadenza` vs `status`/`scadenza`); i criteri "fattura da pagare" qui differiscono da `/tutte` e `/prossime` (campo persistito vs +30gg calcolati): widget e lista possono divergere. Costante `SCADENZE_FISCALI` definita ma mai usata (le stesse date sono hardcoded in `_genera_scadenze_fiscali`).

## alerts.py (prefisso `/api/alerts`)
Gestione alert di sistema sulla collezione `alerts`, con doppio schema convivente: legacy (`letto`/`risolto` booleani) e relazionale (`stato: aperto|risolto`, `severita`, `modulo`). Include alert specifici per fornitori senza metodo di pagamento. 7 endpoint.

### GET /api/alerts/summary — badge topnav alert aperti
**Cosa fa**: conteggi degli alert aperti per severità e modulo, più i 5 critici recenti per il dropdown.
**Logica codice**: query compatibile con entrambi gli schemi (`stato="aperto"` OR `stato` assente AND `risolto≠True`); due aggregate su `alerts` (group per `severita` e `modulo`), poi `find` dei critici recenti (sort `created_at` desc, limit 5).
**Note**: severità fuori da {critical, warning, info} scartate dal totale (solo `null` mappato a `info`).

### GET /api/alerts/lista — lista alert con statistiche
**Cosa fa**: lista alert filtrabile per `tipo`, `letto`, `risolto` con statistiche globali.
**Logica codice**: `find` su `alerts` sort `created_at` desc (limit 1-200); statistiche con `count_documents` (`{}`, `{letto:False}`, `{risolto:False}`) e aggregate per `tipo`.
**Note**: le stats usano match esatto `False`: non contano i documenti dello schema relazionale privi di quei campi — numeri potenzialmente diversi da `/summary`.

### GET /api/alerts/fornitori-senza-metodo — alert fornitori senza pagamento
**Cosa fa**: lista gli alert non risolti di tipo `fornitore_senza_metodo_pagamento`.
**Logica codice**: `find` su `alerts` con `{tipo, risolto:False}`, sort `created_at` desc, max 100.

### POST /api/alerts/{alert_id}/segna-letto — segna letto
**Cosa fa**: marca un alert come letto.
**Logica codice**: `update_one` per `id`, set `letto=True` + `letto_il`; 404 se `modified_count == 0`.

### POST /api/alerts/{alert_id}/risolvi — risolvi alert
**Cosa fa**: marca un alert come risolto (e letto).
**Logica codice**: `update_one` set `risolto=True`, `risolto_il`, `letto=True`; 404 se nessuna modifica.
**Note**: scrive solo i campi legacy; non aggiorna `stato` dello schema relazionale: un alert relazionale risolto qui resta `stato:aperto` per `/summary`.

### DELETE /api/alerts/{alert_id} — elimina alert
**Cosa fa**: elimina un alert.
**Logica codice**: `delete_one` per `id`; 404 se non trovato.

### POST /api/alerts/risolvi-fornitore/{fornitore_piva} — risoluzione massiva per fornitore
**Cosa fa**: risolve tutti gli alert "fornitore senza metodo pagamento" di una P.IVA quando il metodo viene configurato.
**Logica codice**: `update_many` su `alerts` (tipo + `fornitore_piva` + `risolto:False`), set `risolto=True`, `risolto_il`, `note_risoluzione`; ritorna il numero risolti.

## notifications.py (prefisso `/api/notifications`)
Notifiche di sistema sulla collezione `notifications`, con flusso "da revisionare" basato sul flag `reviewed`. Modulo minimale: 6 funzioni / 7 route (la prima ha doppio path).

### GET /api/notifications (e alias GET /api/notifications/all) — tutte le notifiche
**Cosa fa**: restituisce le notifiche, opzionalmente filtrate per `tipo` (scadenza, alert, verbale).
**Logica codice**: `find` su `notifications`, sort `created_at` desc, limit 1-500; due decoratori route sulla stessa funzione.
**Note**: eccezioni loggate ma silenziate con `return []` (il client non distingue errore da lista vuota).

### GET /api/notifications/review — notifiche da revisionare
**Cosa fa**: lista notifiche non ancora revisionate.
**Logica codice**: `find` con `{reviewed:{$ne:True}}`, sort `created_at` desc, limit 1-200; errori silenziati con `[]`.

### GET /api/notifications/unread-count — conteggio non lette
**Cosa fa**: numero di notifiche non revisionate (badge).
**Logica codice**: `count_documents` con `{reviewed:{$ne:True}}`; in errore ritorna `{count:0}`.

### POST /api/notifications/review/{notification_id}/mark-reviewed — segna revisionata
**Cosa fa**: marca una singola notifica come revisionata.
**Logica codice**: `update_one` per `id`, set `reviewed=True` + `reviewed_at` (datetime nativo, non stringa ISO come altrove).
**Note**: risponde sempre 200; se non trovata cambia solo il messaggio, mai 404.

### POST /api/notifications/mark-all-read — segna tutte lette
**Cosa fa**: marca tutte le notifiche non revisionate come revisionate.
**Logica codice**: `update_many` su `{reviewed:{$ne:True}}`, ritorna `count` = `modified_count`.

### DELETE /api/notifications/{notification_id} — elimina notifica
**Cosa fa**: cancella una notifica.
**Logica codice**: `delete_one` per `id`.
**Note**: 200 anche se non trovata (solo messaggio diverso).

## todo.py (prefisso `/api/todo`)
CRUD completo di task/promemoria sulla collezione `todo_tasks` con modelli Pydantic (`TaskCreate`, `TaskUpdate`), priorità con ordinamento numerico (`priorita_ordine`), scadenze e collegamento a documenti (fattura/verbale/fornitore). 10 endpoint.

### GET /api/todo/lista — lista task con filtri e stats
**Cosa fa**: lista filtrabile per stato, priorità, categoria, scadenza entro N giorni e ricerca testo.
**Logica codice**: query dinamica su `todo_tasks` (regex case-insensitive su titolo/descrizione per `cerca`); sort composto `completato, priorita_ordine, scadenza`; 6 `count_documents` per statistiche.
**Note**: il docstring del modulo promette "filtri per assegnatario", ma il filtro `assegnato_a` NON è implementato.

### POST /api/todo/crea — crea task
**Cosa fa**: crea un task con priorità, scadenza, categoria e documenti collegati.
**Logica codice**: valida via `TaskCreate`; mappa priorità→`priorita_ordine` (alta=1, media=2, bassa=3); `id` uuid4, timestamps ISO UTC; `insert_one` su `todo_tasks`.

### PUT /api/todo/{task_id} — aggiorna task
**Cosa fa**: aggiornamento parziale di un task esistente.
**Logica codice**: `find_one` per esistenza (404); `$set` solo dei campi non-None di `TaskUpdate` (riallinea `priorita_ordine`, gestisce `completato_at`); `update_one` e rilettura.

### PUT /api/todo/{task_id}/completa — completa task
**Cosa fa**: marca il task completato.
**Logica codice**: `update_one` set `completato=True`, `completato_at`, `updated_at`; 404 se `modified_count == 0`.
**Note**: un task già completato produce `modified_count=0` → 404 fuorviante (idem `/riapri`).

### PUT /api/todo/{task_id}/riapri — riapre task
**Cosa fa**: riporta un task completato a "da fare".
**Logica codice**: `update_one` set `completato=False`, `completato_at=None`, `updated_at`; 404 se nessuna modifica.

### DELETE /api/todo/{task_id} — elimina task
**Cosa fa**: cancella un task.
**Logica codice**: `delete_one` per `id`; 404 se `deleted_count == 0`.

### GET /api/todo/categorie — categorie disponibili
**Cosa fa**: unione di 9 categorie predefinite e categorie effettivamente usate.
**Logica codice**: aggregate `$group` per `categoria`, merge con lista hardcoded, dedup e sort alfabetico.

### GET /api/todo/scadenze-oggi — task in scadenza oggi
**Cosa fa**: task non completati con scadenza esattamente oggi.
**Logica codice**: `find` con `{completato:{$ne:True}, scadenza: oggi}` (confronto stringa `YYYY-MM-DD`), max 100.

### GET /api/todo/scadenze-settimana — task in scadenza a 7 giorni
**Cosa fa**: task non completati con scadenza tra oggi e +7 giorni.
**Logica codice**: `find` con range stringa su `scadenza`, sort crescente, max 100.

### GET /api/todo/statistiche — statistiche complete
**Cosa fa**: totali, ripartizione per priorità, scaduti, in scadenza oggi, ripartizione per categoria, percentuale completamento.
**Logica codice**: 8 `count_documents` + una aggregate per categoria sui non completati.

## agenti.py (prefisso `/api/agenti`)
Interfaccia verso il sottosistema Agenti AI: segnalazioni prodotte dagli agenti (`agenti_segnalazioni`), stato agenti (`agenti_stato`), pattern appresi (`agenti_apprendimenti`) ed esecuzione manuale dell'orchestratore. 8 endpoint.

### GET /api/agenti/segnalazioni — lista segnalazioni
**Cosa fa**: elenca le segnalazioni AI, filtrabili per `non_lette` e `tipo`.
**Logica codice**: `find` su `agenti_segnalazioni` (se `non_lette=True` filtra `letta:False`), sort `created_at` desc, limit default 50.

### GET /api/agenti/segnalazioni/count — badge non lette
**Cosa fa**: conteggio segnalazioni non lette.
**Logica codice**: `count_documents` con `{letta:False}` (match esatto: documenti senza il campo non contati).

### GET /api/agenti/segnalazioni/summary — contatori per tipo (widget)
**Cosa fa**: conta le segnalazioni non risolte per tipo, accorpando le "anomalia" nelle "urgente".
**Logica codice**: aggregate `$group` per `tipo` su `{risolta:{$ne:True}}`; tipi fuori da {urgente, avviso, info, suggerimento, anomalia} ignorati; `totale` calcolato dopo il merge.

### PUT /api/agenti/segnalazioni/{sid}/letta — segna letta
**Cosa fa**: marca una segnalazione come letta.
**Logica codice**: `update_one` per `id`, set `letta=True` + `letta_at`; risponde sempre `{status:ok}`.
**Note**: nessun controllo di esistenza (mai 404), a differenza di alerts/todo.

### PUT /api/agenti/segnalazioni/{sid}/risolta — segna risolta
**Cosa fa**: marca una segnalazione come risolta.
**Logica codice**: `update_one` set `risolta=True` + `risolta_at`; sempre `{status:ok}` anche se l'id non esiste.

### GET /api/agenti/stato — stato agenti
**Cosa fa**: restituisce lo stato di tutti gli agenti AI.
**Logica codice**: `find` completo su `agenti_stato` (max 20 documenti).

### POST /api/agenti/run — esecuzione manuale agenti
**Cosa fa**: lancia in modo sincrono tutti gli agenti AI tramite l'orchestratore.
**Logica codice**: import lazy di `app.agents.orchestrator.run_agenti` con il db; eccezioni catturate e restituite come `{status:"errore", error}`.
**Note**: risponde comunque HTTP 200 in errore; endpoint potenzialmente lungo/costoso senza lock anti-concorrenza.

### GET /api/agenti/pattern-appresi — pattern della LearningCervello
**Cosa fa**: lista i pattern appresi con confidenza ≥ 0.3, opzionalmente per categoria.
**Logica codice**: `find` su `agenti_apprendimenti` (`confidenza ≥ 0.3`), sort `occorrenze` desc, max 100; deriva l'elenco categorie dai risultati.

## rapido.py (prefisso `/api/rapido`)
Endpoint "quick-entry" per la pagina Inserimento Rapido: registrazioni veloci in prima nota cassa/banca (corrispettivi, versamenti, apporti soci, acconti), pagamento fatture con event bus e presenze giornaliere. 8 endpoint.

### GET /api/rapido/dipendenti-attivi — anagrafica dipendenti attivi
**Cosa fa**: lista compatta dei dipendenti attivi per le select del form.
**Logica codice**: `find` su `dipendenti` (`attivo:True` o campo assente, esclusi i `merged_into`), proiezione id/nome, sort `nome_completo`, max 200.

### GET /api/rapido/ultimi-inserimenti — storico inserimenti rapidi
**Cosa fa**: ultimi movimenti creati dalla pagina rapida (default 5).
**Logica codice**: `find` su `prima_nota_cassa` con `source` regex `rapido`, sort `created_at` desc.

### POST /api/rapido/corrispettivo — registra corrispettivo in cassa
**Cosa fa**: inserisce un'entrata di cassa categoria "Corrispettivi".
**Logica codice**: valida `importo > 0` (400); `insert_one` su `prima_nota_cassa` con `tipo=entrata`, `source=rapido_corrispettivo`, data default oggi.
**Note**: NON scrive nella collezione `corrispettivi`: questo incasso non entra nel calcolo IVA di `/api/scadenze/iva*`.

### POST /api/rapido/versamento-banca — versamento contanti in banca
**Cosa fa**: registra l'uscita di cassa per un versamento in banca.
**Logica codice**: valida `importo > 0`; `insert_one` su `prima_nota_cassa` con `tipo=uscita`, categoria "Versamento", `source=rapido_versamento`.
**Note**: registra SOLO l'uscita cassa — non crea la corrispondente entrata in `prima_nota_banca` (giroconto incompleto rispetto al nome).

### POST /api/rapido/apporto-soci — finanziamento soci
**Cosa fa**: registra un'entrata di cassa "Finanziamento soci".
**Logica codice**: valida `importo > 0`; `insert_one` su `prima_nota_cassa` con `tipo=entrata`, `source=rapido_apporto_soci`.

### POST /api/rapido/paga-fattura — pagamento rapido fattura
**Cosa fa**: registra il pagamento di una fattura in cassa o banca, marca la fattura pagata e propaga l'evento.
**Logica codice**: parametri in query string (`invoice_id`, `metodo_pagamento`, `importo`); 400 senza `invoice_id`, 404 se la fattura non esiste; importo default dal totale fattura; anti-duplicato via `find_one({fattura_id})` nella collezione scelta (`prima_nota_cassa` o `prima_nota_banca`); `insert_one` movimento uscita, `update_one` su `invoices` (`pagato=True`, `stato_pagamento=pagata`); `propagate_event(FATTURA_PAGATA)` sull'event bus (eccezioni solo loggate).
**Note**: anti-duplicato solo sulla collezione del metodo corrente — pagamento doppio possibile con metodo diverso; parametri query string in un POST, atipico rispetto al resto del modulo.

### POST /api/rapido/acconto-dipendente — acconto a dipendente
**Cosa fa**: registra un'uscita di cassa come acconto a un dipendente.
**Logica codice**: valida `importo > 0` e `dipendente_id` presente; `insert_one` su `prima_nota_cassa` categoria "Acconti dipendenti".
**Note**: non verifica che il `dipendente_id` esista in `dipendenti`.

### POST /api/rapido/presenza — presenza giornaliera
**Cosa fa**: registra una presenza (tipo/ore/note) per un dipendente.
**Logica codice**: valida `dipendente_id`; `insert_one` su `presenze_giornaliere` con default `tipo=presente`, `ore=8`, `source=rapido`.
**Note**: nessun anti-duplicato (stessa persona/data inseribile più volte) né verifica esistenza dipendente.

## batch_operations.py (prefisso `/api/batch`)
Operazioni massive "N operazioni con 1 chiamata API": riconciliazione, pagamenti, categorizzazione, chiusura scadenze e processamento fatture pendenti. Nessuna autorizzazione per ruolo. Il docstring del modulo elenca solo 4 endpoint, ma ne esistono 6.

### POST /api/batch/riconcilia — riconciliazione massiva movimenti
**Cosa fa**: marca N movimenti bancari come riconciliati con fattura/F24/cedolino e chiude le scadenze.
**Logica codice**: per ogni item aggiorna `estratto_conto_movimenti` (`riconciliato="riconciliato"`, `{tipo_match}_id`, timestamp); poi il documento collegato in `invoices`/`f24_unificato`/`cedolini` (`status` o `stato_pagamento`="pagato" + `movimento_banca_id`); infine `update_one` su `scadenzario` (stato="pagato"). Errori raccolti per item, non bloccanti.
**Note**: nessuna verifica di esistenza — un ID inesistente conta come "successo" (update a 0 match). Non propaga eventi sul bus (incoerente con `/auto-riconcilia-tutto`). Chiusura scadenza con `update_one`: se più scadenze matchano ne chiude una sola.

### POST /api/batch/paga — pagamento massivo con bonifici cumulativi
**Cosa fa**: genera bonifici raggruppando N fatture per IBAN fornitore e le mette "in_pagamento".
**Logica codice**: legge `invoices` per gli id richiesti, raggruppa per `iban_fornitore` (fallback "NO_IBAN"), inserisce un doc per gruppo in `bonifici_generati` (id `bon-<timestamp>-<ultime4 IBAN>`, stato "da_eseguire") e aggiorna ogni fattura con `status="in_pagamento"` e `bonifico_id`.
**Note**: id bonifico basato su timestamp al secondo → collisione possibile; non controlla se la fattura è già pagata; id inesistenti ignorati in silenzio. Scrive in `bonifici_generati` mentre `verifica-bonifici-vs-banca` legge `bonifici_transfers`.

### POST /api/batch/categorizza — assegnazione massiva centro di costo
**Cosa fa**: assegna un centro di costo a N fatture.
**Logica codice**: carica `centri_costo` per risolvere il nome (mappa `_id` e `id`); per ogni item aggiorna `invoices` con `centro_costo_id`, `centro_costo_nome`, timestamp.
**Note**: validazione solo cosmetica: se il centro non esiste usa l'id come nome e scrive comunque (nessun 404/400).

### POST /api/batch/chiudi-scadenze — chiusura massiva scadenze
**Cosa fa**: marca N scadenze come pagate con nota di chiusura.
**Logica codice**: `update_many` su `scadenzario` (`stato="pagato"`, `data_chiusura`, `nota_chiusura`); ritorna i documenti modificati.

### POST /api/batch/auto-riconcilia-tutto — riconciliazione automatica euristica
**Cosa fa**: matcha automaticamente movimenti bancari in uscita non riconciliati con fatture aperte per importo simile.
**Logica codice**: legge fino a 500 `estratto_conto_movimenti` non riconciliati con importo negativo; per ciascuno cerca in `invoices` (status aperti, importo ±2€), score 90 se diff<0.5€, 70 se <2€, +20 se il nome fornitore compare nella descrizione; se score ≥ `min_confidence` e non `dry_run`: aggiorna movimento, fattura a `status="pagato"`, chiude scadenza in `scadenzario`, propaga `FATTURA_PAGATA` via event bus. Primo match e `break`.
**Note**: RISCHIO: `dry_run=False` di default (scrive subito) e con `min_confidence=90` basta la sola corrispondenza di importo (diff<0.5€) senza riscontro fornitore; salta la fase "in_pagamento" (incoerente con `/paga`).

### POST /api/batch/processa-fatture-pendenti — processamento fatture in attesa
**Cosa fa**: classifica per centro di costo e/o crea la scadenza mancante per le fatture pendenti.
**Logica codice**: legge `invoices` con status in attesa; keyword da `fornitori_learning` (`keywords` → `centro_costo_suggerito`); azione "classifica": primo match keyword nel nome fornitore → set `centro_costo_id`; azione "scadenza": se assente in `scadenzario`, insert con id deterministico `scad-<fattura_id>` e stato "da_pagare".
**Note**: la classificazione imposta solo `centro_costo_id` senza `centro_costo_nome` (incoerente con `/categorizza`).

## batch_reprocessing.py (prefisso `/api/batch-reprocess`)
Riprocessamento massivo dei PDF di F24 e cedolini tramite `BatchReprocessingService`. Job in background con `asyncio.create_task` e stato in variabile globale di modulo `_job_state`.

### GET /api/batch-reprocess/preview — anteprima documenti riprocessabili
**Cosa fa**: conta i documenti con PDF disponibili per il riprocessamento.
**Logica codice**: `count_documents` su collezioni F24 (`f24_models`, `f24`, `f24_uploaded`, filtro `pdf_data`) e cedolini (`cedolini`, `payslips`, `buste_paga`, `extracted_documents`, filtro `pdf_data`/`file_base64`/`pdf_base64`); errori per collezione silenziati con `except: pass`.

### GET /api/batch-reprocess/status — stato del job
**Cosa fa**: restituisce lo stato corrente (`running`, `progress`, `result`, `error`).
**Logica codice**: ritorna il dizionario globale `_job_state`; nessun DB.

### POST /api/batch-reprocess/start — avvia riprocessamento completo
**Cosa fa**: lancia in background il riprocessamento F24 + cedolini.
**Logica codice**: se `_job_state["running"]` risponde "Job gia in corso" (HTTP 200); altrimenti `asyncio.create_task(_run_job(...))` → `BatchReprocessingService.reprocess_all(dry_run)`; `dry_run` query param, default `True`.
**Note**: stato in-process, non condiviso tra worker: lock e status non affidabili con più worker; rifiuto per job in corso risponde 200 anziché 409.

### POST /api/batch-reprocess/f24-only — solo F24
**Cosa fa**: come `/start` ma chiama `reprocess_all_f24(dry_run)`.
**Logica codice**: identica a `/start` con method "f24"; stesse note su `_job_state`.

### POST /api/batch-reprocess/cedolini-only — solo cedolini
**Cosa fa**: come `/start` ma chiama `reprocess_all_cedolini(dry_run)`.
**Logica codice**: identica a `/start` con method "cedolini".

## auto_repair.py (prefisso `/api/auto-repair`)
Micro-modulo con un solo endpoint di riparazione dati sui verbali di noleggio orfani.

### POST /api/auto-repair/collega-targa-driver — collega targa a driver
**Cosa fa**: assegna il driver a tutti i verbali di noleggio con quella targa privi di driver.
**Logica codice**: valida il dipendente su `dipendenti` (404 se assente), calcola il nome (`nome_completo` o `cognome nome`); `update_many` su `verbali_noleggio` (targa uppercase, `driver_id` nullo/vuoto/assente); setta `driver_id`, `driver_nome`, `auto_repaired=True`, `updated_at`. Parametri via query string.

## sync_relazionale.py (montato su `/api` + prefisso interno `/sync` → `/api/sync`)
Sincronizza fatture ↔ prima nota cassa/banca ↔ corrispettivi ↔ estratto conto con helper interni (`sync_fattura_to_prima_nota`, `sync_corrispettivo_to_prima_nota`, ecc.). Nel codice restano commenti su un endpoint eliminato perché "pericoloso" (`/fatture-to-banca`). 8 endpoint.

### POST /api/sync/match-fatture-cassa — match fatture ↔ prima nota cassa
**Cosa fa**: aggancia i movimenti di cassa "pagamento fornitore" alle fatture e le marca pagate in Cassa.
**Logica codice**: legge `prima_nota_cassa` (uscite categoria fornitori senza `fattura_id`), estrae il numero fattura da `riferimento` o via regex dalla descrizione, cerca in `invoices` per numero (regex) + importo ±0,50€; se trova: aggiorna fattura (`metodo_pagamento="Cassa"`, `pagato/paid=True`, `data_pagamento`, `prima_nota_cassa_id`) e movimento (`fattura_id`, `riconciliato=True`).
**Note**: il docstring dichiara match per "numero + fornitore + importo" ma il fornitore NON è verificato. Numero fattura iniettato non-escapato in regex (caratteri speciali alterano il match). Contatore `already_linked` mai incrementato.

### POST /api/sync/match-fatture-banca — match fatture ↔ estratto conto
**Cosa fa**: aggancia le fatture "Bonifico" non associate ai movimenti bancari e le marca pagate.
**Logica codice**: legge `invoices` con metodo bonifico e senza `estratto_conto_id`; cerca in `estratto_conto_movimenti` un'uscita con importo ±1€, senza `fattura_id`, descrizione che matcha (regex) fornitore[:20] o numero fattura; aggiorna fattura (`estratto_conto_id`, `pagato/paid=True`, `data_pagamento`) e movimento.
**Note**: se `numero` è stringa vuota la regex `""` matcha qualunque descrizione → match sul solo importo (falsi positivi di pagamento). Regex non escapate. `already_matched` mai incrementato.

### GET /api/sync/fatture-cassa-dettaglio — dettaglio associazioni cassa
**Cosa fa**: riepilogo di fatture collegate alla cassa e movimenti cassa con fattura.
**Logica codice**: conta/lista `invoices` con `prima_nota_cassa_id` e `prima_nota_cassa` con `fattura_id`; conteggi e primi 10 esempi. Sola lettura.

### POST /api/sync/sync-fattura/{fattura_id} — sincronizza fattura → prima nota
**Cosa fa**: crea/aggiorna il movimento di prima nota (cassa o banca in base al metodo pagamento) per una fattura.
**Logica codice**: `sync_fattura_to_prima_nota`: legge `invoices`; metodo "cassa"/"contanti" → `prima_nota_cassa`, altrimenti `prima_nota_banca`; upsert manuale (cerca per `fattura_id`, update o insert con uuid) di un movimento "uscita" categoria "Fornitori" con `riconciliato=True`. Errori ritornati come `{"success":False}` con HTTP 200.

### POST /api/sync/sync-corrispettivo/{corrispettivo_id} — sincronizza corrispettivo → cassa
**Cosa fa**: crea/aggiorna in prima nota cassa l'entrata lorda (imponibile+IVA) di un corrispettivo.
**Logica codice**: `sync_corrispettivo_to_prima_nota`: legge `corrispettivi`, calcola `totale_lordo`, upsert su `prima_nota_cassa` per `corrispettivo_id` con tipo "entrata", categoria "Corrispettivi", dettaglio (imponibile/IVA/n. scontrini), `riconciliato=False`.

### POST /api/sync/sync-all-corrispettivi — sincronizza corrispettivi di un anno
**Cosa fa**: applica il sync a tutti i corrispettivi dell'anno indicato.
**Logica codice**: `Body {anno}`; legge `corrispettivi` con `data` regex anno (max 1000) e itera `sync_corrispettivo_to_prima_nota`; contatori created/updated/errors.
**Note**: limite fisso 1000: oltre, i rimanenti vengono ignorati silenziosamente.

### PUT /api/sync/update-fattura-everywhere/{fattura_id} — aggiornamento propagato
**Cosa fa**: aggiorna campi di una fattura e propaga a prima nota cassa/banca, spostando il movimento se cambia il metodo di pagamento.
**Logica codice**: whitelist campi (`metodo_pagamento`, `pagato`, `data_pagamento`, `importo`, `note`); sincronizza `pagato`→`paid`; aggiorna `invoices` (404 se assente); poi `update_one` su `prima_nota_cassa` e `prima_nota_banca` per `fattura_id`; se cambia metodo, `delete_one` dal registro sbagliato e ricreazione via `sync_fattura_to_prima_nota`.
**Note**: BUG: gli update su prima nota fanno `$set` incondizionato di `importo`, `pagato` e `data` con `update_data.get(...)` → i campi non inviati vengono sovrascritti con `null` sui movimenti collegati (es. aggiornare solo `note` azzera importo/data/pagato in prima nota).

### GET /api/sync/stato-sincronizzazione — stato sincronizzazione
**Cosa fa**: dashboard di conteggi sullo stato di sync del sistema.
**Logica codice**: serie di `count_documents` su `invoices` (totali, pagate, cassa, banca, senza metodo), `prima_nota_cassa` (uscite/entrate/con fattura), `prima_nota_banca`, `corrispettivi`. Sola lettura.

## verifica_coerenza.py (prefisso `/api/verifica-coerenza`)
Endpoint di sola lettura per il controllo di consistenza dati (IVA, versamenti, bonifici, saldi) delegati al service `app/services/verifica_coerenza.py` (`VerificaCoerenza`, `esegui_verifica_completa`, `esegui_verifica_iva`). 7 endpoint.

### GET /api/verifica-coerenza/completa/{anno} — verifica completa annuale
**Cosa fa**: esegue tutte le verifiche di coerenza (IVA, versamenti, saldi, F24) per l'anno.
**Logica codice**: delega a `esegui_verifica_completa(anno)`; eccezioni → HTTP 500.

### GET /api/verifica-coerenza/iva/{anno}/{mese} — verifica IVA mensile
**Cosa fa**: confronta i valori IVA tra fatture, corrispettivi e liquidazione per un mese.
**Logica codice**: valida mese 1-12 (400), delega a `esegui_verifica_iva(anno, mese)`.

### GET /api/verifica-coerenza/discrepanze/{anno} — solo discrepanze
**Cosa fa**: restituisce le sole discrepanze dell'anno, filtrabili per severità.
**Logica codice**: esegue l'INTERA `esegui_verifica_completa(anno)` e filtra in memoria per `severita` (`critical`/`warning`/`info`).
**Note**: costo pieno della verifica completa anche per un semplice filtro.

### GET /api/verifica-coerenza/widget — widget alert discrepanze
**Cosa fa**: check veloce del mese corrente per il widget mostrato in tutte le pagine.
**Logica codice**: `VerificaCoerenza(db)`, chiama `verifica_coerenza_iva_tra_pagine` e `verifica_versamenti_vs_banca` per il mese corrente; max 5 discrepanze in output, più aggregati IVA e flag versamenti.
**Note**: in caso di eccezione risponde HTTP 200 con `has_discrepanze=False` e campo `error` — può mascherare guasti come "tutto ok".

### GET /api/verifica-coerenza/confronto-iva-completo/{anno} — confronto IVA 12 mesi
**Cosa fa**: tabella mese-per-mese di IVA a credito (fatture) vs debito (corrispettivi) con saldo annuale.
**Logica codice**: loop 1-12 su `verifica_coerenza_iva_tra_pagine`, accumula totali, calcola saldo/da_versare/a_credito per mese; include le discrepanze accumulate.

### GET /api/verifica-coerenza/verifica-bonifici-vs-banca/{anno} — bonifici vs banca
**Cosa fa**: confronta il totale dei bonifici registrati con i bonifici in uscita dell'estratto conto.
**Logica codice**: aggregation su `bonifici_transfers` (totale, count, riconciliati per anno via regex data) e su `estratto_conto_movimenti` (importi negativi con "BONIFICO"/"SEPA" in `descrizione_originale`); differenza, flag `coerente` (<1€), alert warning/critical.
**Note**: legge `bonifici_transfers`, mentre `/api/batch/paga` scrive in `bonifici_generati`: i bonifici del batch sfuggono a questa verifica.

### GET /api/verifica-coerenza/riepilogo-giornaliero — dashboard verifiche
**Cosa fa**: verifica completa dell'anno corrente con stato semaforico (OK/ATTENZIONE/CRITICO).
**Logica codice**: `VerificaCoerenza.verifica_completa(anno corrente)`; arricchisce con `data_verifica`, mese corrente e `stato_generale`/`stato_colore` dai contatori critical/warning.
**Note**: duplica in gran parte `/completa/{anno}` (stesso motore, decorazioni in più).
