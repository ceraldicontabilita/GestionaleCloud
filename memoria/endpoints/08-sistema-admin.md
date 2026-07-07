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
