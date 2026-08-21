# 08 — Sistema, Admin, Report e Integrazioni

<!-- gestionalecloud-doc
status: reference
reviewed_at: 2026-08-21
storage_architecture: drive-only
-->

> [!IMPORTANT]
> Documento di riferimento del dominio. Per persistenza e cutover vale l'architettura Drive-only descritta nei documenti correnti; eventuali nomi di collection restano soltanto contesto storico.

Documentazione endpoint dei moduli di sistema: autenticazione, amministrazione, configurazione, dashboard/report/export, scadenze/alert/notifiche, operazioni batch e coerenza dati, commercialista, integrazioni esterne (OpenAPI.it, WhatsApp), API pubbliche/alias e dizionario articoli.

Contesto trasversale:
- **Auth**: JWT HS256 firmato con `settings.SECRET_KEY` (env + segreto in `sistema_stato.auth_secret`). Middleware globale `app/middleware/authentication.py` protegge TUTTO `/api/*` salvo `PUBLIC_PATHS`/`PUBLIC_PREFIXES` (tra cui `/api/auth/*`, `/api/public/*`, `/api/openclaw/*`, `/api/enhanced-parser/info`, health, docs). `/api/f24-public/*` **RIMOSSO dalla whitelist (lug 2026)**: esponeva lettura/scrittura di F24 reali senza alcuna verifica, vedi nota sotto. Il token è accettato da header `Authorization: Bearer` o cookie `access_token`; per i WebSocket da query `?token=` (verificato dentro l'handler stesso, non dal middleware — vedi nota sotto).
- I prefissi indicati sono quelli effettivi da `app/router_registry.py`.

---

## auth.py (montato senza prefisso extra: prefisso interno `/api`)
Login/logout single-user admin (credenziali da env `ADMIN_EMAIL` + `ADMIN_PASSWORD` in chiaro o `ADMIN_PASSWORD_HASH` bcrypt). Emette JWT HS256 (7 giorni) con PyJWT e lo salva in cookie httpOnly `access_token` + cookie flag `session_active`. Nessuna collezione Drive/Sheets: utente unico da variabili d'ambiente.

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
**Cosa fa**: lista tutte le collezioni Drive/Sheets con conteggio documenti.
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
Download e lista dei file di export generati sul filesystem del server. Nessun accesso Drive/Sheets.

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
Export "semplificati" (8 endpoint GET): query dirette Drive/Sheets senza layer servizi, output Excel via pandas/openpyxl oppure JSON grezzo con `?format=json`. Nessuna dipendenza auth negli handler (solo middleware, dichiarato correttamente nel docstring).

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

## commercialista.py (prefisso `/api/commercialista`)
Invio di documenti contabili mensili al commercialista via email SMTP (config da env `SMTP_HOST`/`SMTP_USER`/`SMTP_PASSWORD`), con export CSV/ZIP/Excel e sistema di alert/log. Email di default hardcoded (`rosaria.marotta@email.it`, "Dott.ssa Rosaria Marotta"). Tutti gli endpoint usano il decoratore `@handle_errors`. 14 endpoint.

### GET /api/commercialista/config — configurazione commercialista
**Cosa fa**: restituisce email/nome/alert del commercialista e lo stato SMTP.
**Logica codice**: `find_one` su `commercialista_config`; default hardcoded se assente; aggiunge `smtp_configured` da `get_smtp_config()` (env).

### PUT /api/commercialista/config — aggiorna configurazione
**Cosa fa**: salva email, nome, `alert_giorni`, `invio_automatico`.
**Logica codice**: upsert su `commercialista_config` con filtro vuoto `{}` (documento singolo). Nessuna validazione del formato email.

### GET /api/commercialista/prima-nota-cassa/{anno}/{mese} — Prima Nota Cassa mensile
**Cosa fa**: restituisce movimenti di cassa del mese con totali entrate/uscite/saldo.
**Logica codice**: query su `prima_nota_cassa` per regex `^YYYY-MM` sul campo `data`, sort data+categoria; fallback su `prima_nota_cassa` con `tipo_conto:"cassa"`, poi su `cash`. Totali tolleranti su campi alternativi (`type`/`tipo`, `amount`/`importo`).
**Note**: il commento dice "try prima_nota collection" ma il secondo tentativo interroga di nuovo `prima_nota_cassa` (fallback quasi inutile). Tutto ciò che non è "entrata/income/in" è classificato uscita.

### GET /api/commercialista/fatture-cassa/{anno}/{mese} — fatture pagate in contanti
**Cosa fa**: elenca le fatture del mese pagate per cassa/contanti con totale.
**Logica codice**: query su `invoices` con `$and` di due `$or`: regex case-insensitive `contant|cassa` su `metodo_pagamento`/`payment_method`/`modalita_pagamento` E regex mese su `data_pagamento`/`invoice_date`/`data_fattura`. Totale da `total_amount`/`importo_totale`.

### POST /api/commercialista/invia-prima-nota — invia Prima Nota via email
**Cosa fa**: invia email HTML al commercialista con riepilogo mensile e PDF allegato.
**Logica codice**: richiede `anno`/`mese` nel body; il PDF arriva DAL FRONTEND come `pdf_base64` (il backend non lo genera); riusa `get_prima_nota_cassa_mensile()` per il riepilogo; invia con `send_email_with_attachment()` (SMTP+STARTTLS); log in `commercialista_log`.
**Note**: se il decode base64 fallisce o `pdf_base64` manca, l'email parte comunque SENZA allegato ma il testo dice "in allegato" e la risposta è success.

### POST /api/commercialista/invia-carnet — invia carnet assegni via email
**Cosa fa**: invia email con riepilogo carnet assegni e PDF allegato.
**Logica codice**: richiede `carnet_id`; conteggi e totale (`assegni_count`, `totale_importo`) arrivano dal client senza verifica sul DB; log in `commercialista_log`.
**Note**: nessuna verifica che il carnet esista; dati riepilogo interamente fiduciari dal frontend.

### POST /api/commercialista/invia-fatture-cassa — invia fatture contanti via email
**Cosa fa**: invia email con elenco fatture pagate per cassa del mese e PDF allegato.
**Logica codice**: riusa `get_fatture_pagate_cassa()`; PDF da `pdf_base64` frontend; log in `commercialista_log`.
**Note**: codice quasi duplicato di invia-prima-nota.

### GET /api/commercialista/log — storico invii
**Cosa fa**: restituisce gli ultimi N invii (default 50).
**Logica codice**: `commercialista_log` sort `data_invio` desc.

### POST /api/commercialista/segna-inviata — segna Prima Nota come inviata
**Cosa fa**: registra manualmente un invio senza mandare email (spegne l'alert).
**Logica codice**: insert in `commercialista_log` con `success:True` e nota "Segnata manualmente come inviata".

### GET /api/commercialista/alert-status — stato alert invio mensile
**Cosa fa**: dice al frontend se mostrare il promemoria di invio della Prima Nota del mese precedente.
**Logica codice**: calcola mese precedente; deadline = giorno 2 del mese corrente h23:59 UTC; controlla in `commercialista_log` se esiste un invio `prima_nota_cassa` riuscito per quel mese; `show_alert = now <= deadline AND non inviata`.
**Note**: dopo il giorno 2 l'alert sparisce anche se la Prima Nota non è mai stata inviata.

### GET /api/commercialista/export-completo/{anno}/{mese} — export ZIP mensile
**Cosa fa**: scarica uno ZIP con CSV di fatture, corrispettivi, prima nota, buste paga + riepilogo IVA in TXT.
**Logica codice**: legge `invoices` (regex su `invoice_date`), `corrispettivi`, `prima_nota_cassa` (via `get_prima_nota_cassa_mensile`), `cedolini`; CSV (`;`) in memoria e `StreamingResponse` ZIP.
**Note**: IVA a debito con aliquota FISSA 10% scorporata dai corrispettivi (hardcoded). Nel CSV prima nota entrata/uscita dedotta dal SEGNO di `importo` mentre altrove si usa il campo `tipo` — criterio incoerente.

### GET /api/commercialista/export-excel/{anno}/{mese} — export Excel mensile
**Cosa fa**: genera XLSX con 5 fogli (Fatture Acquisto, Corrispettivi, Prima Nota Cassa, Riepilogo IVA, Riepilogo).
**Logica codice**: openpyxl con stili; legge `invoices`, `corrispettivi`, `prima_nota_cassa` con regex mese; totali in Python; IVA vendite = 10% fisso; `StreamingResponse` xlsx.
**Note**: duplica in gran parte export-completo.

### POST /api/commercialista/schedula-export — report mensile immediato o schedulato
**Cosa fa**: con `immediato:true` (default) genera un Excel di riepilogo e lo invia subito via email; altrimenti salva una schedulazione.
**Logica codice**: legge `commercialista_config` per l'email; se immediato legge `invoices` (range su `data_ricezione`), `corrispettivi`, `prima_nota_cassa`; crea Workbook riepilogativo, invia con `send_email_with_attachment`, logga in `export_log`. Se non immediato: insert in `scheduled_exports` con `status:"pending"`.
**Note**: il totale fatture legge il campo `totale` (altrove `total_amount`) → probabilmente sempre 0; filtro su `data_ricezione` anziché `invoice_date` (incoerente con gli altri endpoint); eccezioni restituite come `{"success":false}` con HTTP 200; nessun worker nel router processa `scheduled_exports` (schedulazione potenzialmente morta).

### GET /api/commercialista/export-log — storico export
**Cosa fa**: restituisce gli ultimi export inviati (default 20) e il conteggio totale.
**Logica codice**: `export_log` sort `inviato_at` desc + `count_documents`.
**Note**: log separato da `commercialista_log` (due storici paralleli).

## gestione_riservata.py (prefisso `/api/gestione-riservata`)
Registro di incassi e spese NON fatturati ("dati riservati") su collezione `gestione_riservata`, con soft-delete e calcolo del "volume d'affari reale" (ufficiale + extra). L'accesso è dichiarato "protetto con codice da variabile d'ambiente" (`GESTIONE_RISERVATA_CODE`), ma il codice è verificato SOLO da `/login`: gli altri endpoint sono protetti unicamente dal JWT globale. 7 endpoint.

### POST /api/gestione-riservata/login — verifica codice di accesso
**Cosa fa**: confronta il codice inviato con `GESTIONE_RISERVATA_CODE` (env) e risponde ok/401.
**Logica codice**: confronto stringa semplice; nessuna sessione/token dedicato: il "login" produce solo un flag lato client.
**Note**: il codice errato tentato viene scritto IN CHIARO nei log (`logger.warning`). Gating puramente cosmetico: qualunque utente JWT può chiamare gli altri endpoint senza passare dal login — il docstring del modulo è fuorviante.

### GET /api/gestione-riservata/movimenti — lista movimenti
**Cosa fa**: elenca i movimenti non fatturati, filtrabili per anno/mese/tipo.
**Logica codice**: `find` su `gestione_riservata` con `entity_status != "deleted"`, sort data desc, limite 10000.

### POST /api/gestione-riservata/movimenti — crea movimento
**Cosa fa**: inserisce un incasso o una spesa non fatturata.
**Logica codice**: `id` uuid4, deriva `anno`/`mese` dalla `data` (fallback oggi), campi tipo/descrizione/importo/categoria/note, `entity_status:"active"`; insert in `gestione_riservata`.

### PUT /api/gestione-riservata/movimenti/{movimento_id} — aggiorna movimento
**Cosa fa**: modifica i campi consentiti di un movimento.
**Logica codice**: `$set` selettivo su whitelist campi; ricalcola anno/mese se cambia la data; 404 se `matched_count == 0`; ritorna il documento aggiornato.
**Note**: `importo` salvato così com'è dal body (nessuna coercizione a float, a differenza della create).

### DELETE /api/gestione-riservata/movimenti/{movimento_id} — elimina movimento
**Cosa fa**: soft-delete del movimento.
**Logica codice**: `$set entity_status:"deleted"` + `deleted_at`; 404 se non trovato.

### GET /api/gestione-riservata/riepilogo — totali incassi/spese
**Cosa fa**: totali e conteggi per incassi, spese e saldo netto.
**Logica codice**: aggregate `$group` per `tipo` (esclusi deleted), filtri opzionali anno/mese.

### GET /api/gestione-riservata/volume-affari-reale — volume d'affari reale
**Cosa fa**: calcola corrispettivi ufficiali + incassi non fatturati - spese non fatturate.
**Logica codice**: aggregate su `corrispettivi` (regex anno o anno-mese su `data`) per il fatturato ufficiale; aggregate su `gestione_riservata` per gli extra; somma finale. Le fatture ricevute (`invoices`) sono deliberatamente escluse (sono costi).
**Note**: `fatturato_ufficiale` e `corrispettivi` nella risposta sono lo stesso valore duplicato.

## openapi_imprese.py (prefisso `/api/openapi-imprese`)
Integrazione con il servizio Company di OpenAPI.com (provider commerciale esterno, `company.openapi.com` — NON lo schema OpenAPI di FastAPI) tramite `app/services/openapi_company.py`, per arricchire/creare le schede fornitore (ragione sociale, PEC, SDI, ATECO...). Token da env `OPENAPI_COMPANY_TOKEN`, sovrascrivibile via query param. Nota: esiste anche `app/services/openapi_imprese.py` (`imprese.openapi.it`) ma questo router NON lo usa. 6 endpoint.

### GET /api/openapi-imprese/status — stato token/API
**Cosa fa**: verifica che il token sia configurato e che l'API risponda.
**Logica codice**: se il token esiste, chiama `OpenAPICompany.get_start_info("12485671007")` (P.IVA di OpenAPI stessa) come test reale.
**Note**: il test consuma una chiamata (potenzialmente a pagamento) a ogni invocazione.

### POST /api/openapi-imprese/aggiorna-fornitore — aggiorna/crea fornitore da P.IVA
**Cosa fa**: scarica i dati aziendali dal provider e li scrive sulla scheda fornitore (update o create).
**Logica codice**: valida P.IVA (11 cifre); cerca in `fornitori` per `partita_iva`/`piva`/`codice_fiscale`; `get_advanced_info` con fallback `get_start_info`; mappa con `map_company_to_fornitore`; recupera la PEC con chiamata separata se mancante; `$set` sul fornitore esistente o insert nuovo (uuid, `source:"openapi"`), con `openapi_last_update`.
**Note**: `force_update` del request model mai usato. Token accettato come query param (rischio leak in log/URL).

### GET /api/openapi-imprese/cerca — ricerca azienda per nome
**Cosa fa**: cerca aziende per denominazione (con filtro provincia) sul provider.
**Logica codice**: `OpenAPICompany.search_company(...)`; nessuna scrittura DB; errori del provider rilanciati come 400.

### GET /api/openapi-imprese/info/{partita_iva} — preview dati azienda
**Cosa fa**: recupera i dati aziendali senza toccare il database.
**Logica codice**: `get_start_info`/`get_advanced_info`/`get_full_info` in base al query param `tipo`; restituisce dati grezzi + `campi_mappati` via `map_company_to_fornitore`.

### GET /api/openapi-imprese/pec/{partita_iva} — solo PEC
**Cosa fa**: recupera la PEC dell'azienda dal provider.
**Logica codice**: `OpenAPICompany.get_pec(piva)`; 404 se non trovata; nessuna scrittura DB.

### GET /api/openapi-imprese/sdi/{partita_iva} — solo codice SDI
**Cosa fa**: recupera il Codice Destinatario SDI dal provider.
**Logica codice**: `OpenAPICompany.get_sdi_code(piva)`; 404 se non trovato; nessuna scrittura DB.

## openapi_it.py (prefisso `/api/openapi`)
Integrazione diretta (httpx) con i servizi OpenAPI.it: AISP/Open Banking per riconciliazione bancaria, bilanci XBRL e visure camerali. Chiave da env `OPENAPI_IT_KEY`, ambiente sandbox/produzione via `OPENAPI_IT_ENV` (URL: `sdi.openapi.it|.com` per AISP, `[test.]visurecamerali.openapi.it` per visure/bilanci). 10 endpoint.

### GET /api/openapi/aisp/status — info servizio AISP
**Cosa fa**: restituisce una descrizione statica del servizio AISP e dei requisiti PSD2.
**Logica codice**: risposta hardcoded, nessuna chiamata esterna né DB.
**Note**: il nome suggerisce un check reale ma è solo testo statico ("status: available" sempre).

### POST /api/openapi/aisp/connetti-conto — connetti conto bancario (consenso PSD2)
**Cosa fa**: richiede al provider un consenso AISP per un IBAN e restituisce l'URL di autorizzazione.
**Logica codice**: POST a `{base}/v1/aisp/consents` con IBAN/bank_code, `valid_until` hardcoded 2027-12-31; upsert in `conti_bancari_aisp` (consent_id, status, url).
**Note**: l'URL base AISP è quello del servizio SDI (`sdi.openapi.it`) — endpoint verosimilmente errato/mai funzionante.

### GET /api/openapi/aisp/movimenti — movimenti bancari via AISP
**Cosa fa**: scarica le transazioni del conto dal provider.
**Logica codice**: verifica in `conti_bancari_aisp` che `consent_status == "valid"` (400 altrimenti); GET `{base}/v1/aisp/accounts/{iban}/transactions` con header `Consent-ID`; nessuna persistenza.
**Note**: `consent_status` viene salvato alla connessione e mai aggiornato da alcun flusso del router: il check può non diventare mai "valid".

### POST /api/openapi/aisp/riconcilia-automatica — riconciliazione automatica
**Cosa fa**: matcha i movimenti bancari con le fatture non pagate e le marca come pagate.
**Logica codice**: chiama internamente `get_movimenti_bancari()`; per ogni movimento cerca in `invoices` una fattura con `total_amount` entro ±1€ e `status` non pagato; se trovata `$set status:"pagata"`, `data_pagamento`, `movimento_aisp_id`, `riconciliazione_automatica:True`.
**Note**: matching solo per importo (nessun controllo data/fornitore, prende la PRIMA fattura trovata) → alto rischio di riconciliazioni errate con effetto scrittura. Eccezioni restituite come HTTP 200 con chiave `error`.

### GET /api/openapi/xbrl/status — info servizio XBRL
**Cosa fa**: descrizione statica del servizio bilanci (feature, tassonomia, costi stimati).
**Logica codice**: risposta hardcoded; espone ambiente e base URL correnti.

### POST /api/openapi/xbrl/richiedi-bilancio — richiedi bilancio XBRL
**Cosa fa**: avvia la richiesta asincrona del bilancio (pronto in 10-15 min) e restituisce il request_id.
**Logica codice**: POST `{visure}/bilancio-ottico` con `cf_piva_id` (+`anno_chiusura` opzionale); insert in `richieste_bilanci` con status pending.

### GET /api/openapi/xbrl/bilancio/{request_id} — stato/contenuto bilancio
**Cosa fa**: interroga il provider sullo stato della richiesta e restituisce i link di download quando completata.
**Logica codice**: GET `{visure}/bilancio-ottico/{id}`; aggiorna `richieste_bilanci`; se completed espone `download_links` verso `/api/openapi/xbrl/download/{id}/{tipo}`.
**Note**: gli endpoint di download `/xbrl/download/...` NON esistono nel router — i link restituiti sono rotti (404).

### POST /api/openapi/xbrl/richiedi-riclassificato — bilancio riclassificato
**Cosa fa**: richiede il bilancio riclassificato con indici (liquidità, redditività...).
**Logica codice**: POST `{visure}/bilancio-riclassificato`; restituisce il request_id.
**Note**: la richiesta NON viene salvata in `richieste_bilanci` e non c'è endpoint per recuperarne l'esito.

### GET /api/openapi/xbrl/storico-richieste — storico richieste bilanci
**Cosa fa**: elenca le richieste bilancio salvate (default 20).
**Logica codice**: `find` su `richieste_bilanci` sort `created_at` desc.

### POST /api/openapi/visure/richiedi — richiedi visura camerale
**Cosa fa**: avvia la richiesta di visura ordinaria e restituisce il request_id.
**Logica codice**: POST `{visure}/visura-ordinaria` con `cf_piva_id`.
**Note**: nessuna persistenza e nessun endpoint di recupero → il request_id resta solo al client.

## openapi_automotive.py (prefisso `/api/openapi-automotive`)
Integrazione con il servizio Automotive di OpenAPI.com (`automotive.openapi.com`, via `app/services/openapi_automotive.py`) per visure veicoli da targa, usata per arricchire la flotta noleggio (`noleggio_veicoli`). Riusa il token env `OPENAPI_COMPANY_TOKEN`. 6 endpoint.

### GET /api/openapi-automotive/status — stato token/API
**Cosa fa**: verifica configurazione e raggiungibilità dell'API Automotive.
**Logica codice**: chiama `get_car_info("AB123CD")` (targa fittizia); considera OK anche l'errore "non trovata".
**Note**: ogni check consuma una chiamata reale al provider.

### GET /api/openapi-automotive/info/{targa} — preview dati veicolo
**Cosa fa**: recupera i dati del veicolo (auto/moto/assicurazione) senza scrivere sul DB.
**Logica codice**: normalizza la targa (upper, no spazi/trattini); switch su `tipo` → `get_car_info`/`get_bike_info`/`get_insurance_info`; dati grezzi + `campi_mappati` via `map_automotive_to_veicolo`.

### POST /api/openapi-automotive/aggiorna-veicolo — aggiorna/crea veicolo da targa
**Cosa fa**: scarica i dati del veicolo e aggiorna (o crea) la scheda in flotta.
**Logica codice**: cerca in `noleggio_veicoli` per targa (esatta o regex case-insensitive); `get_car_info`; `$set` dei campi mappati oppure insert con uuid, `stato:"attivo"`, `source:"openapi_automotive"`.
**Note**: `force_update` mai usato; la regex senza ancore può matchare targhe diverse che contengono la stringa.

### POST /api/openapi-automotive/aggiorna-bulk — aggiornamento massivo
**Cosa fa**: aggiorna in batch una lista di targhe, con riepilogo creati/aggiornati/errori.
**Logica codice**: loop sequenziale sulle targhe; `get_car_info` per ognuna; upsert su `noleggio_veicoli` con regex ancorata case-insensitive; contatori e dettagli per targa.
**Note**: i documenti creati via upsert NON ricevono `id` uuid, `created_at`, `stato`, `source` (a differenza di aggiorna-veicolo) → veicoli "orfani" incoerenti.

### GET /api/openapi-automotive/veicoli-da-aggiornare — veicoli senza dati OpenAPI
**Cosa fa**: elenca i veicoli in flotta con targa ma mai arricchiti dal provider.
**Logica codice**: `find` su `noleggio_veicoli` con `targa` esistente e `openapi_last_update` assente, projection minima.
**Note**: nel percorso di aggiornamento di QUESTO router `openapi_last_update` non viene mai impostato → i veicoli restano per sempre "da aggiornare".

### GET /api/openapi-automotive/assicurazione/{targa} — info assicurazione
**Cosa fa**: recupera lo stato assicurativo del veicolo dal provider.
**Logica codice**: `get_insurance_info(targa_normalizzata)`; 404 se non trovata; nessuna scrittura DB.

## pianificazione.py (prefisso `/api/pianificazione`)
CRUD minimale dei costi previsionali (budget planning) sulla collection `costi_previsionali`. Tutti gli endpoint richiedono `Depends(get_current_user)` + middleware. Nessun modello Pydantic (body libero). 3 endpoint in questo file (gli eventi `/api/pianificazione/events` sono definiti in `public_api.py`).

### GET /api/pianificazione/costi-previsionali — lista costi previsionali
**Cosa fa**: restituisce fino a 500 costi pianificati, più recenti prima.
**Logica codice**: `costi_previsionali` con proiezione `{_id:0}`, sort su `date` desc, `to_list(500)`.
**Note**: sort sul campo `date` senza garanzia che i documenti lo contengano.

### POST /api/pianificazione/costi-previsionali — crea costo previsionale
**Cosa fa**: inserisce un costo pianificato e ne restituisce l'id.
**Logica codice**: body arbitrario + `id` uuid4 + `created_at` UTC; `insert_one`; risponde 201.
**Note**: nessuna validazione: qualunque JSON viene salvato tal quale.

### DELETE /api/pianificazione/costi-previsionali/{costo_id} — elimina costo
**Cosa fa**: hard delete del costo con l'id indicato.
**Logica codice**: `delete_one({"id": costo_id})`; risponde sempre "Cost deleted".
**Note**: non controlla `deleted_count` — successo anche se l'id non esiste.

## whatsapp_webhook.py (legacy, non registrato nel runtime attuale)
Integrazione WhatsApp Business Cloud API (Meta) conservata come riferimento storico: il router non è più montato nel runtime attuale e non deve essere considerato canale operativo. I dettagli sotto descrivono il comportamento storico del modulo, non un endpoint attivo. Token di verifica `WHATSAPP_VERIFY_TOKEN` (fallback hardcoded `"ceraldi_erp_webhook_2026"`). 5 endpoint storici.

### GET /api/whatsapp/webhook — verifica webhook Meta (storico)
**Cosa fa**: risponde alla challenge di sottoscrizione del webhook Meta.
**Logica codice**: legge query `hub.mode`, `hub.verify_token`, `hub.challenge`; se `mode=="subscribe"` e token corrisponde restituisce la challenge in `PlainTextResponse`, altrimenti 403. Nessun DB.
**Note**: NON è in whitelist pubblica: essendo sotto `/api/`, richiede JWT — Meta riceverebbe 401 e la verifica fallirebbe (integrazione webhook di fatto rotta). Il token in chiaro viene loggato.

### POST /api/whatsapp/webhook — ricezione notifiche Meta (storico)
**Cosa fa**: riceve messaggi in arrivo e status update (sent/delivered/read) da Meta.
**Logica codice**: parsa `entry[].changes[].value`, itera `messages` e `statuses` e li LOGGA soltanto (testo troncato a 100 caratteri); eccezioni inghiottite; risponde sempre `{"status":"ok"}`. Nessuna scrittura DB.
**Note**: il docstring dice "gestisce ricezione messaggi" ma i messaggi non vengono persistiti né processati (solo log). Anche questo endpoint è bloccato dal middleware auth.

### GET /api/whatsapp/status — stato configurazione (storico)
**Cosa fa**: riporta lo stato di configurazione della Cloud API senza esporre il token.
**Logica codice**: delega a `get_whatsapp_config_status()` (import lazy). Nessun DB.

### POST /api/whatsapp/send — invio messaggio (storico)
**Cosa fa**: invia un messaggio WhatsApp a un numero, al destinatario di default o in broadcast.
**Logica codice**: valida solo `text` non vuoto (400); `broadcast` truthy → `send_whatsapp_to_all(text)`, altrimenti `send_whatsapp_message(text, to)`.
**Note**: nessun controllo ruolo: qualunque utente autenticato può inviare/broadcastare.

### POST /api/whatsapp/send-test — messaggio di test (storico)
**Cosa fa**: invia un messaggio di prova al primo destinatario configurato (`WHATSAPP_RECIPIENT_1`).
**Logica codice**: testo fisso con data/ora locale + `send_whatsapp_message(msg)`.

## erp_bridge.py (montato senza prefisso extra: prefisso interno `/api/erp/ponte`)
Ponte fire-and-forget tra l'app Tracciabilità (ceraldiapp.it) e il Gestionale: riceve le fatture importate dalla PEC e le upserta in `fatture_passive`. 2 endpoint.

### POST /api/erp/ponte/fattura-ricevuta — upsert fattura da Tracciabilità
**Cosa fa**: registra/aggiorna in `fatture_passive` una fattura ricevuta da Tracciabilità, deduplicata.
**Logica codice**: payload Pydantic `FatturaRicevutaPayload` (numero, fornitore, P.IVA, data, importi, righe); `_normalizza_data` converte DD/MM/YYYY → YYYY-MM-DD; `dedup_key = numero_fattura|partita_iva (o fornitore)`; `update_one(..., upsert=True)` con `$set` del documento (stato `importata`, source `tracciabilita`) e `$setOnInsert` di `id`/`created_at`.
**Note**: gli header `X-Source`/`X-Azienda` citati nel docstring sono solo loggati, mai validati (nessuna autenticazione propria). Essendo sotto `/api/`, il middleware richiede JWT: le chiamate server-to-server senza token vengono respinte con 401 (integrazione di fatto rotta, salvo che il chiamante possieda un JWT).

### GET /api/erp/ponte/status — health check del ponte
**Cosa fa**: verifica raggiungibilità del ponte e conta le fatture importate.
**Logica codice**: `count_documents({"source":"tracciabilita"})` su `fatture_passive`.
**Note**: anch'esso dietro JWT (middleware).

## websocket_realtime.py (montato su `/api` — route effettive `/api/ws/*` e `/api/realtime/status`)
WebSocket per dashboard e notifiche real-time più un endpoint HTTP di stato. Usa `ws_manager` (`app/services/websocket_manager`) per i canali.

### WS /api/ws/dashboard — WebSocket KPI dashboard
**Cosa fa**: alla connessione invia i KPI dell'anno (query `anno`, default 2026) e poi risponde a comandi `refresh`/`ping`.
**Logica codice**: `calculate_live_kpi()` legge intere collection in memoria: `corrispettivi` (fatturato, regex `^anno` su `data`), `prima_nota_cassa`/`prima_nota_banca`/`prima_nota_salari` (entrate/uscite per `tipo`), conta `invoices`, `dipendenti`, `f24_unificato` non pagati, scadenze ≤7gg su `scadenzario_fornitori`. Loop con timeout 300s: `refresh` ricalcola, `ping`/timeout → `pong`.
**Note**: il docstring promette "aggiornamenti ogni 30 secondi" ma il codice NON invia push periodici (solo su richiesta). Il controllo `?token=` del middleware sta in `BaseHTTPMiddleware.dispatch`, che NON intercetta lo scope ASGI `websocket`: l'endpoint è di fatto SENZA autenticazione. Query pesanti (`to_list(length=None)`); anno default hardcoded 2026.

### WS /api/ws/notifications — WebSocket notifiche
**Cosa fa**: mantiene un canale per notifiche push generali (fatture, scadenze, movimenti).
**Logica codice**: si registra sul canale `notifications` di `ws_manager`; loop timeout 25s: `pong` ai `ping`, `heartbeat` al timeout; l'invio effettivo avviene altrove via `ws_manager`.
**Note**: come sopra, nessuna autenticazione effettiva.

### GET /api/realtime/status — stato connessioni WS
**Cosa fa**: numero di connessioni WebSocket attive per canale.
**Logica codice**: `ws_manager.get_connection_count()` (totale, dashboard, notifications). Nessun DB; protetto da JWT (è HTTP).

## legal_pages.py (percorsi `/privacy`, `/terms`, `/data-deletion` + alias `/api/...`)
Pagine HTML statiche (Privacy, Termini, Eliminazione dati) per la compliance Meta/WhatsApp, con HTML inline nel modulo. Ogni pagina è registrata su due percorsi: con e senza prefisso `/api`. Nessun accesso DB. 6 route.

### GET /privacy (alias GET /api/privacy) — informativa privacy
**Cosa fa**: restituisce l'informativa GDPR HTML di Ceraldi Group S.R.L.
**Logica codice**: ritorna la costante `PRIVACY_HTML` come `HTMLResponse`.
**Note**: `/privacy` è PUBBLICO (non sotto `/api/`, il middleware lo lascia passare); l'alias `/api/privacy` invece richiede JWT — inutilizzabile da Meta/visitatori anonimi.

### GET /terms (alias GET /api/terms) — condizioni d'uso
**Cosa fa**: restituisce le condizioni d'uso HTML.
**Logica codice**: ritorna la costante `TERMS_HTML`.
**Note**: `/terms` pubblico; `/api/terms` dietro JWT (stessa asimmetria).

### GET /data-deletion (alias GET /api/data-deletion) — istruzioni eliminazione dati
**Cosa fa**: pagina con istruzioni per la cancellazione dati (art. 17 GDPR), richiesta da Meta.
**Logica codice**: HTML inline costruito nel corpo della funzione.
**Note**: `/data-deletion` pubblico; `/api/data-deletion` dietro JWT.

## public_api.py (montato su `/api` — route sparse su più namespace)
Contenitore di endpoint legacy non ancora refactorizzati (dichiarato nel docstring), montato su `/api`: definisce route sotto `/api/f24-public`, `/api/invoices`, `/api/suppliers`, `/api/warehouse`, `/api/cash`, `/api/bank`, `/api/assegni`, `/api/pianificazione`, `/api/portal`, `/api/dashboard`, `/api/fornitori`, `/api/ricerca-globale`, `/api/v1`. SOVRAPPONE ALIAS a namespace di altri moduli (pianificazione.py, suppliers, F24, dashboard). Nessun endpoint usa `get_current_user`: protezione solo dal middleware, tranne `/api/f24-public/*` che è in whitelist PUBBLICA.

### GET /api/f24-public/alerts — alert scadenze F24
**Cosa fa**: genera alert di scadenza F24 con severità (critical/high/medium/low) ordinati per giorni mancanti.
**Logica codice**: due query ENTRAMBE su `f24_unificato` (una "models": `pagato≠true`; una "commercialista": `status` non pagato/eliminato), filtro anno opzionale via regex; parse scadenze in più formati; classifica per giorni residui (scarta >30gg).
**Note**: ✔ RISOLTO (lug 2026) — richiedeva PUBBLICO senza auth (`/api/f24-public/` in `PUBLIC_PREFIXES`): esponeva importi e contribuenti a chiunque. Rimosso dalla whitelist, ora richiede JWT come il resto di `/api/*`. Il docstring parla di "tutte le collection" ma entrambe le query leggono la stessa collection `f24_unificato`: un documento che soddisfa entrambi i filtri genera alert duplicati (ancora presente, non è un problema di auth).

### GET /api/f24-public/dashboard — dashboard F24
**Cosa fa**: totali F24 pagati/da pagare e conteggio alert entro 7 giorni.
**Logica codice**: legge `f24_unificato` (fino a 10000), partiziona su `status=="paid"`, somma campo `importo`, calcola giorni su `scadenza`.
**Note**: pubblico senza auth. Usa campi (`status=="paid"`, `importo`, `scadenza`) diversi da `/alerts` (`pagato`, `saldo_finale`, `data_scadenza`): rischio conteggi/somme a zero sullo schema reale.

### GET /api/invoices — lista fatture
**Cosa fa**: lista fatture con filtro anno e paginazione.
**Logica codice**: aggregation su `invoices`: filtro anno su `invoice_date` O `data_documento` (provvisorie Aruba), `$addFields data_effettiva = ifNull(...)`, sort desc, skip/limit, senza `_id`.

### POST /api/invoices — crea fattura manuale
**Cosa fa**: inserisce una fattura minimale creata a mano.
**Logica codice**: documento con `id` uuid, `invoice_number`, `supplier_name`, `total_amount`, `invoice_date`, `status` (default `pending`), `created_at`; `insert_one` su `invoices`.
**Note**: nessuna validazione tipi/duplicati.

### DELETE /api/invoices/{invoice_id} — elimina fattura (soft-delete)
**Cosa fa**: soft-delete di una fattura con regole di business (no pagate/registrate).
**Logica codice**: `find_one` (404); `BusinessRules.can_delete_invoice` → 400 se non eliminabile; se warnings e `force=false` risponde `require_force`; altrimenti `$set entity_status=deleted, status=deleted, deleted_at`.

### POST /api/suppliers — crea fornitore + auto-associazione fatture
**Cosa fa**: crea un fornitore e collega automaticamente le fatture esistenti con la stessa P.IVA.
**Logica codice**: normalizza campi doppi ITA/ENG (`partita_iva`/`vat_number`, `denominazione`/`name`...), `insert_one` su `fornitori`; poi `update_many` su `invoices` (`cedente_piva==piva`, `supplier_id` assente) impostando `supplier_id`/`supplier_name`; ritorna il fornitore con `fatture_associate`.
**Note**: il GET /suppliers vive nel router suppliers (commento nel file). Indice unique sparse su `fornitori.partita_iva`: P.IVA duplicata → `DuplicateKeyError` non gestita (500).

### GET /api/warehouse/products — lista prodotti magazzino
**Cosa fa**: lista prodotti con filtri `category`/`source` e paginazione.
**Logica codice**: `find` su `warehouse_inventory`, skip/limit (default 5000).

### POST /api/warehouse/products — crea prodotto
**Cosa fa**: inserisce un prodotto di magazzino.
**Logica codice**: documento con `id` uuid e campi inglesi (`name`, `code`, `quantity`, `unit`, `unit_price`, `category`, `supplier_vat`); `insert_one` su `warehouse_inventory`.

### PUT /api/warehouse/products/{product_id} — aggiorna prodotto
**Cosa fa**: aggiorna i campi non-null del prodotto e lo restituisce.
**Logica codice**: `$set` con `updated_at`; 404 se `matched_count==0`; rilegge il documento.

### DELETE /api/warehouse/products/{product_id} — elimina prodotto
**Cosa fa**: hard delete del prodotto.
**Logica codice**: `delete_one({"id":...})` su `warehouse_inventory`, 404 se `deleted_count==0`.

### GET /api/warehouse/movements — lista movimenti magazzino
**Cosa fa**: lista movimenti (filtro opzionale `product_id`), più recenti prima.
**Logica codice**: `find` su `warehouse_movements`, sort `date` desc, skip/limit.

### POST /api/warehouse/movements — crea movimento carico/scarico
**Cosa fa**: registra un movimento e aggiorna la giacenza del prodotto.
**Logica codice**: documento con `type` `in`/`out`, `quantity`, `date`, `reference`; se il prodotto esiste applica delta ±quantity su `warehouse_inventory.quantity`; poi `insert_one` su `warehouse_movements`.
**Note**: aggiornamento giacenza non atomico (read-modify-write, race condition); il movimento viene salvato anche se `product_id` non esiste.

### GET /api/suppliers/{supplier_id}/inventory — inventario prodotti fornitore
**Cosa fa**: estrae il catalogo prodotti di un fornitore dalle righe delle sue fatture.
**Logica codice**: risolve il fornitore per `id` o `partita_iva` su `fornitori` (404); legge fino a 1000 fatture (`supplier_vat` o `cedente_piva`); deduplica le righe per descrizione (chiave: primi 100 caratteri lowercase) accumulando quantità, conteggio fatture, ultimo prezzo.

### GET /api/cash — lista movimenti cassa
**Cosa fa**: lista movimenti dalla prima nota cassa.
**Logica codice**: `find` su `prima_nota_cassa`, sort su `date` desc, skip/limit.
**Note**: ordina per `date` ma la prima nota usa `data`: sort probabilmente inefficace sui dati reali.

### POST /api/cash — crea movimento cassa
**Cosa fa**: inserisce un movimento cassa.
**Logica codice**: documento con campi inglesi (`date`, `type`, `amount`, `description`, `category`) su `prima_nota_cassa`.
**Note**: schema incoerente con il resto della prima nota (`data`/`tipo`/`importo`): i movimenti creati qui sono invisibili ai calcoli KPI/statistiche che usano i campi italiani.

### GET /api/bank/statements — lista movimenti banca
**Cosa fa**: lista movimenti dell'estratto conto.
**Logica codice**: `find` su `estratto_conto_movimenti`, sort su `date` desc, skip/limit.
**Note**: stessa ambiguità `date`/`data` della cassa.

### POST /api/bank/statements — crea movimento banca
**Cosa fa**: inserisce un movimento banca manuale.
**Logica codice**: documento con campi inglesi su `estratto_conto_movimenti`, struttura identica a POST /cash.

### GET /api/assegni — lista assegni
**Cosa fa**: lista assegni non eliminati, filtrabili per anno.
**Logica codice**: query `entity_status≠deleted` su `assegni`; filtro anno via regex su `data_emissione`/`created_at`/`data`/`numero_assegno`; sort su `numero_assegno` desc.

### POST /api/assegni — crea assegno
**Cosa fa**: inserisce un assegno.
**Logica codice**: documento con `numero`, `importo`, `beneficiario`, `data_emissione`, `stato` (default `emesso`) su `assegni`.
**Note**: il GET filtra/ordina su `numero_assegno` ma il POST salva `numero`: gli assegni creati qui non si ordinano/filtrano correttamente.

### GET /api/pianificazione/events — lista eventi pianificazione
**Cosa fa**: lista eventi del calendario di pianificazione.
**Logica codice**: legge tutta `planning_events`, sort IN MEMORIA su `scheduled_date` o `start_date` (schema misto vecchio/nuovo), poi slicing skip/limit.
**Note**: convive nel namespace `/api/pianificazione` con pianificazione.py (dominio spezzato su due moduli); qui senza `get_current_user`.

### POST /api/pianificazione/events — crea evento pianificazione
**Cosa fa**: crea un evento accettando sia lo schema nuovo (scheduled_date/event_type/notes) sia il vecchio (start_date/type/description).
**Logica codice**: normalizza i campi e salva il documento con ENTRAMBI i set di nomi su `planning_events` per retrocompatibilità; `status` default `scheduled`.

### POST /api/portal/upload — upload portale con routing per tipo
**Cosa fa**: upload generico; se `kind=estratto-conto` parsa il file e tenta la riconciliazione con la prima nota.
**Logica codice**: per `estratto-conto` importa da `bank_statement_import` i parser PDF/Excel/CSV e `reconcile_movement`; deduplica per `data_tipo_importo`; per ogni movimento cerca il match in prima nota e compila il report `reconciled`/`not_found`. Altri `kind`: restituisce solo nome e dimensione file ("non elaborato").
**Note**: nonostante il messaggio "Importati N movimenti", NESSUN movimento viene salvato su DB: solo parsing e riconciliazione in memoria (messaggio ingannevole).

### GET /api/dashboard/stats (definito anche qui) — statistiche dashboard
**Cosa fa**: conteggi rapidi per la dashboard.
**Logica codice**: `count_documents({})` su `invoices`, `fornitori`, `dipendenti`, `corrispettivi`.
**Note**: stesso path di `GET /api/dashboard/stats` di reports/dashboard.py — public_api è registrato PRIMA, quindi questa versione vince (l'altra è di fatto oscurata).

### GET /api/fornitori/metodi-pagamento — metodi di pagamento
**Cosa fa**: restituisce la lista statica dei metodi pagamento supportati.
**Logica codice**: array hardcoded (`contanti`, `bonifico`, `assegno`, `carta`, `riba`, `mav`, `rid`, `altro`); nessun DB.

### POST /api/fornitori/import-metodi-da-fatture — import metodi da fatture
**Cosa fa**: deduce il metodo di pagamento dei fornitori dai codici SDI (MP01/MP02...) delle fatture.
**Logica codice**: legge fino a 10000 `invoices` con `pagamento.ModalitaPagamento`; mappa MP01→contanti, MP02/03→assegno, MP05/06/07→bonifico; aggiorna in `fornitori` solo chi non ha già `metodo_pagamento`; ritorna `{updated}`.

### GET /api/ricerca-globale — ricerca globale
**Cosa fa**: ricerca unificata (min 2 caratteri) su fatture, fornitori, prodotti e dipendenti per la barra di ricerca.
**Logica codice**: regex case-insensitive su campi doppi ITA/ENG di `invoices`, `fornitori` (parole in AND), `warehouse_inventory`, `dipendenti`; per ogni fornitore trovato una aggregation su `invoices` per conteggio/totale; risultati normalizzati `{tipo, id, titolo, sottotitolo}`.
**Note**: N+1 aggregation per fornitore; il ramo `else` della query fornitori (ricerca P.IVA) è irraggiungibile perché `q` ha `min_length=2` e `words` non è mai vuoto.

### POST /api/v1/keys/generate — genera API Key
**Cosa fa**: crea una API key (`ak_...`) per integrazioni esterne.
**Logica codice**: token urlsafe; salva su `api_clients` solo hash SHA-256 + `key_prefix`, `permessi` (default `["read"]`), `active=true`; restituisce la key in chiaro una sola volta.
**Note**: nessun controllo ruolo admin: qualunque utente JWT può generare chiavi.

### GET /api/v1/keys — lista API Keys
**Cosa fa**: elenca i client API senza esporre gli hash.
**Logica codice**: `find` su `api_clients` con proiezione che esclude `_id` e `key_hash` (max 100).

### GET /api/v1/fatture — API esterna fatture (API key)
**Cosa fa**: lista fatture ricevute o emesse per integrazioni esterne.
**Logica codice**: `verify_api_key_header` (hash SHA-256 vs `api_clients` attivi, aggiorna `last_used` e `request_count`, 401 se invalida); legge `fatture_ricevute` o `fatture_emesse` con filtro anno via regex.
**Note**: la key viaggia come query param `api_key` (finisce nei log/URL); l'endpoint non è whitelistato quindi il middleware pretende ANCHE il JWT: la sola API key non basta (doppio requisito che vanifica l'uso esterno). `fatture_ricevute`/`fatture_emesse` sono collezioni diverse da `invoices`. Il campo `permessi` non viene mai verificato.

### GET /api/v1/movimenti — API esterna prima nota
**Cosa fa**: lista movimenti prima nota cassa filtrati per intervallo date.
**Logica codice**: verifica API key; `find` su `prima_nota_cassa` con range su `data`, sort desc, limit ≤500.
**Note**: stesse criticità di /v1/fatture (key in query string + JWT comunque richiesto).

### GET /api/v1/stats — API esterna statistiche
**Cosa fa**: statistiche aggregate per anno.
**Logica codice**: verifica API key; conta su `invoices` (`data_ricezione`), `fatture_emesse` (`data_fattura`), `prima_nota_cassa` (`data`), `dipendenti` attivi.
**Note**: conta le fatture ricevute su `invoices` mentre /v1/fatture le legge da `fatture_ricevute`: numeri potenzialmente incoerenti.

## warehouse/dizionario_articoli.py (prefisso `/api/dizionario-articoli`)
Mappatura degli articoli delle fatture al Piano dei Conti: estrazione articoli unici dalle righe fattura, categorizzazione automatica via ~35 gruppi di regex (`PATTERNS_ARTICOLI` → categoria merceologica + conto), fallback AI per i non classificati, CRUD sulla collezione `dizionario_articoli`. IMPORTANTE: il campo `categoria_haccp` è solo il NOME STORICO del campo — oggi rappresenta la categoria merceologica usata per il Piano dei Conti; HACCP è stato eliminato dal gestionale (la materia alimentare è dell'app separata ceraldiapp.it). 11 endpoint.

### GET /api/dizionario-articoli/estrai-articoli — estrazione e categorizzazione al volo
**Cosa fa**: estrae gli articoli unici dalle fatture e li categorizza senza salvarli.
**Logica codice**: aggregation su `invoices` (`$unwind $linee`, group per descrizione con count/fornitori/prezzi), poi `categorizza_articolo()` in Python (regex + confidenza basata su lunghezza match) e somma prezzi con `sum_prices`/`safe_parse_float` (gestisce virgole decimali). Ritorna articoli + statistiche per categoria/conto/confidenza. Sola lettura.

### GET /api/dizionario-articoli/dizionario — lettura dizionario
**Cosa fa**: lista paginata del dizionario salvato.
**Logica codice**: `find` su `dizionario_articoli` con filtri opzionali `categoria_haccp` (categoria merceologica) e `non_mappati` (`mappatura_manuale != True`); sort occorrenze desc, skip/limit, più count totale.

### POST /api/dizionario-articoli/genera-dizionario — genera/aggiorna dizionario
**Cosa fa**: rigenera il dizionario dalle fatture applicando la categorizzazione euristica.
**Logica codice**: stessa aggregation di `/estrai-articoli` (max 10000); per ogni descrizione find su `dizionario_articoli`: se esiste aggiorna (preservando categoria/conto se `mappatura_manuale=True`), altrimenti insert con uuid. Ritorna created/updated.
**Note**: N+1 (una find + una write per articolo); nel ramo "manuale" preserva categoria e conto ma SOVRASCRIVE `categoria_haccp_nome` e `confidenza` con i valori ricalcolati (nome categoria potenzialmente incoerente con la categoria preservata).

### PUT /api/dizionario-articoli/articolo/{descrizione_encoded} — mappatura manuale
**Cosa fa**: aggiorna manualmente categoria merceologica/conto/note di un articolo.
**Logica codice**: chiave = descrizione URL-encoded (decodificata con `urllib.parse.unquote`); 404 se assente; valida `categoria_haccp` contro `CATEGORIE_MERCEOLOGICHE` (400); setta `mappatura_manuale=True`; ritorna il documento aggiornato.

### GET /api/dizionario-articoli/statistiche — statistiche dizionario
**Cosa fa**: aggregati del dizionario per categoria, conto e fascia di confidenza.
**Logica codice**: count totale e manuali; due aggregation (group per `categoria_haccp` e per `conto` con importi); count per confidenza alta (≥0.5), media, zero. Sola lettura.

### POST /api/dizionario-articoli/ricategorizza-fatture — applica dizionario alle fatture
**Cosa fa**: scrive su ogni fattura il conto di costo dominante derivato dal dizionario.
**Logica codice**: carica tutto `dizionario_articoli` in memoria; scorre `invoices` con `linee` non vuote; somma gli importi riga per conto e sceglie il conto con importo maggiore; aggiorna la fattura con `conto_costo_codice`, `conto_costo_nome`, `categoria_haccp_dominante` (= categoria merceologica dominante), `dizionario_applied_at`.
**Note**: assegna un solo conto per fattura (il dominante), non una ripartizione per riga.

### GET /api/dizionario-articoli/cerca — ricerca articoli
**Cosa fa**: ricerca testuale nel dizionario.
**Logica codice**: `find` con `$regex` case-insensitive sulla descrizione (min 2 caratteri), sort occorrenze, limit.
**Note**: il termine `q` non è regex-escaped: caratteri speciali possono causare errori o match imprevisti.

### DELETE /api/dizionario-articoli/reset-dizionario — reset totale
**Cosa fa**: svuota completamente la collezione del dizionario.
**Logica codice**: `delete_many({})` su `dizionario_articoli`, ritorna il conteggio.
**Note**: distruttivo, senza conferma né backup; cancella anche tutte le mappature manuali (che `/genera-dizionario` non può ricostruire).

### POST /api/dizionario-articoli/categorizza-ai — categorizzazione AI
**Cosa fa**: fa categorizzare dall'AI gli articoli con confidenza 0 e aggiorna il dizionario.
**Logica codice**: delega a `app.services.ai_categorizzazione.aggiorna_dizionario_con_ai(db, limite)`; 500 se il servizio non è importabile o fallisce.
**Note**: IL DOCSTRING MENTE: dichiara "GPT-5.2", ma il service usa il modello `claude-haiku-4-5` e per giunta etichetta i record con `categorizzato_da: "claude-sonnet-4.5"` — tre nomi diversi tra docstring, modello reale e marcatura dati.

### GET /api/dizionario-articoli/non-classificati — articoli non classificati
**Cosa fa**: lista gli articoli con confidenza 0 ordinati per occorrenze.
**Logica codice**: `find` con `confidenza: 0`, sort occorrenze desc, limit. Sola lettura.

### POST /api/dizionario-articoli/riclassifica-completo — rigenera + AI in un colpo
**Cosa fa**: rigenera il dizionario dalle fatture e poi passa all'AI i non classificati (pulsante "Ricategorizza con AI" della pagina Piano dei Conti).
**Logica codice**: step 1 chiama direttamente `genera_dizionario()`; step 2 chiama `aggiorna_dizionario_con_ai(db, limite_ai)` con degradazione controllata se il servizio AI manca. Ritorna i risultati dei due step.
**Note**: il docstring dello step 2 dice "Claude Haiku" (coerente col service), in contraddizione con il "GPT-5.2" di `/categorizza-ai`.

---

## Anomalie principali rilevate (trasversali)

**Autenticazione / sicurezza**
- `POST /api/login` e `POST /api/logout` legacy sono irraggiungibili da non autenticati (non in whitelist middleware): funziona solo l'alias `/api/auth/login`; logica di login duplicata riga per riga in `auth.py`.
- Due stack JWT paralleli: `auth.py` (PyJWT, `sub`=email, "HS256" hardcoded) vs `pin_login.py`/middleware (jose, `settings.ALGORITHM`, `sub`=user_id): `request.state.user_id` vale un'email o un identificatore interno a seconda del login.
- ✔ RISOLTO (lug 2026) — I WebSocket `/api/ws/*` erano di fatto SENZA autenticazione (`?token=` stava in `BaseHTTPMiddleware.dispatch` che non intercetta lo scope ASGI `websocket`, codice morto). Ora `_autentica_websocket()` verifica il JWT dentro l'handler stesso, prima di `ws_manager.connect()`.
- ✔ RISOLTO (lug 2026) — `/api/f24-public/*` era completamente pubblico ed esponeva importi F24 e contribuenti (oltre a upload/modifica/delete) senza auth. Rimosso da `PUBLIC_PREFIXES`.
- ✔ RISOLTO (lug 2026) — Webhook WhatsApp (`/api/whatsapp/webhook`) e ponte ERP (`/api/erp/ponte/*`) ora in whitelist; il ponte ERP è protetto da un segreto dedicato (`ERP_BRIDGE_SECRET` via header `X-Erp-Secret`) invece di restare aperto. Gli header `X-Source`/`X-Azienda` restano solo loggati (informativi, non di sicurezza).
- ✔ RISOLTO (lug 2026) — Alias legali `/api/privacy|terms|data-deletion` ora pubblici in whitelist (erano dietro JWT, inutilizzabili per compliance Meta).
- API v1 (public_api): doppio requisito contraddittorio API key + JWT; key passata come query param; `permessi` mai verificato; `/v1/keys/generate` senza controllo ruolo admin.
- Nessun controllo di RUOLO in tutto il perimetro: qualunque utente JWT può usare endpoint distruttivi (reset collezioni/dizionario), dati riservati, invio WhatsApp, chiamate a pagamento verso OpenAPI.*.
- `gestione_riservata`: il codice `GESTIONE_RISERVATA_CODE` protegge solo `/login` (gating cosmetico lato client); il codice errato viene loggato in chiaro.
- Password in chiaro su Drive/Sheets: `email_accounts.app_password`, `settings.gmail_app_password`; `GET /api/config/email` restituisce il documento senza mascheramenti; `ADMIN_PASSWORD` in chiaro ha priorità sul bcrypt; cookie con `secure=False`; PIN hashato SHA-256 senza salt e anti brute-force solo in-memory per processo.

**Docstring che mentono**
- `admin_export.py` dichiara `/app/uploads/` ma usa `/tmp/uploads`.
- `GET /api/dashboard/summary` si dichiara "public endpoint" ma richiede JWT.
- `/api/dizionario-articoli/categorizza-ai` dichiara "GPT-5.2" ma il service usa `claude-haiku-4-5` (e marca i record `claude-sonnet-4.5`).
- `sync match-fatture-cassa` dichiara match "numero + fornitore + importo" ma il fornitore non è verificato.
- `report-pdf/mensile` promette "Scadenze" assenti; `report-pdf/dipendenti` promette buste paga mai lette; `analytics/self-repair` non ripara nulla; WS dashboard promette push ogni 30s mai implementato; webhook WhatsApp "gestisce" messaggi che in realtà solo logga; `batch_operations` docstring elenca 4 endpoint su 6; `portal/upload` risponde "Importati N movimenti" senza salvare nulla.

**Bug e rischi dati**
- `PUT /api/sync/update-fattura-everywhere/{id}`: `$set` incondizionato di `importo`/`pagato`/`data` sui movimenti prima nota → i campi non inviati vengono azzerati a `null`.
- Riconciliazioni automatiche rischiose: `/api/batch/auto-riconcilia-tutto` (`dry_run=False` default, match sul solo importo ±0,50€) e `/api/openapi/aisp/riconcilia-automatica` (±1€, prima fattura trovata) marcano fatture "pagate" senza riscontro fornitore/data.
- Regex non escapate (numero fattura/fornitore in sync_relazionale, `q` in dizionario/cerca); in `match-fatture-banca` numero vuoto → regex `""` che matcha tutto.
- `exports.py` filtra sul campo `date` inesistente nelle fatture (`invoice_date`/`data_ricezione`): export/report mensile rischiano di essere vuoti; `GET /api/exports/excel` è uno stub che restituisce un xlsx di 0 byte.
- Collezioni incoerenti per lo stesso dominio: `warehouse_products` vs `warehouse_inventory`; `employees` vs `dipendenti`; `suppliers` vs `fornitori`; `bonifici_generati` (batch/paga) vs `bonifici_transfers` (verifica-coerenza); `invoices` vs `fatture_ricevute`/`fatture_passive`; doppio archivio F24 `f24_unificato` + `f24_commercialista` con schemi diversi (`pagato`/`data_scadenza` vs `status`/`scadenza`) — il widget scadenze li somma correttamente, ma `/f24-public/dashboard` usa campi che sullo schema reale possono dare totali a zero.
- Campi ITA/ENG incoerenti: `POST /api/cash` e `POST /api/bank/statements` scrivono `date`/`type`/`amount` mentre il resto legge `data`/`tipo`/`importo`; `POST /api/assegni` salva `numero` ma il GET filtra su `numero_assegno`.
- `rapido.py`: `versamento-banca` registra solo l'uscita cassa (giroconto incompleto); `corrispettivo` non alimenta la collezione `corrispettivi` (fuori dal calcolo IVA); `paga-fattura` anti-duplicato solo sulla collezione del metodo scelto.
- IVA con aliquota fissa 10% hardcoded negli export commercialista e nel report PDF mensile (imprecisa con aliquote miste).
- `alerts.py`: doppio schema non riconciliato — `/risolvi` scrive solo i campi legacy, un alert relazionale resta "aperto" per `/summary`.
- GET con side-effect di scrittura (`/api/config/email-accounts`, `/api/config/parole-chiave`); `parole-chiave/aggiungi|rimuovi` non validano `categoria` (iniezione campi nel doc di config).
- Errori mascherati con HTTP 200: dashboard/kpi/stats/bilancio (zeri), widget verifica-coerenza (`has_discrepanze=False` su eccezione), notifications (`[]`), agenti `/run`, test IMAP/Gmail, sync helper.
- Stato job in-process (`batch_reprocessing._job_state`) e lock PIN in-memory: non affidabili con più worker.
- `openapi_it`: link download XBRL rotti (endpoint inesistente), richieste riclassificato/visure senza persistenza, `consent_status` mai portato a "valid", base URL AISP sul dominio SDI.
- `openapi_automotive`: upsert bulk crea veicoli senza `id`/`created_at`/`stato`/`source`; `openapi_last_update` mai scritto → `/veicoli-da-aggiornare` sempre pieno.
- `commercialista`: `schedula-export` legge il campo `totale` (probabilmente sempre 0) e `scheduled_exports` non ha alcun processore; email inviate "con allegato" anche senza PDF; alert invio sparisce dopo il giorno 2 anche se mai inviata.
- `public_api` definisce `GET /api/dashboard/stats` che oscura l'omonimo endpoint di reports/dashboard.py (public_api è registrato prima); duplicazioni funzionali multiple tra `/api/exports/*` (exports vs simple_exports), `/api/dashboard/*` vs `/api/analytics/*`, tre sistemi di configurazione email (config.py, configurazioni.py, settings_router.py).
- Endpoint legacy/one-shot da rimuovere: `DELETE /api/admin/cleanup-trattenute-disciplinari`, `GET /api/exports/excel` (stub), triplo alias `GET /api/scadenze|/|/tutte`, costante morta `SCADENZE_FISCALI`, modello `ParolaChiaveInput` mai usato, parametro `delete_files` di reset-collections ignorato.
