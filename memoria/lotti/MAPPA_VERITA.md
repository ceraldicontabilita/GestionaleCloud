# MAPPA DI VERITÀ — App Tracciabilità HACCP (Lotti)

<!-- gestionalecloud-doc
status: historical
reviewed_at: 2026-09-17
storage_architecture: supabase
-->

> [!NOTE]
> Snapshot storico: non descrive lo stato operativo corrente. Per l'architettura Drive-only usare `README.md`, `PRODUCT.md`, `CLAUDE.md` e `LOGICA_FUNZIONAMENTO.md`.

> Documento generato automaticamente il 29/05/2026 incrociando codice e database live.
> Scopo: prima di modificare una pagina, sapere con CERTEZZA quali endpoint e collezioni usa.
> Rigenerabile con `python3 scripts/genera_mappa_verita.py`.

## Riferimenti infrastruttura

- **Backend live**: https://lotti-backend-f2fg.onrender.com
- **Frontend live**: https://lotti-frontend.onrender.com
- **Database**: Supabase/PostgreSQL `Lotti-HACCP`, indipendente da GestionaleCloud; `DB_NAME=Gestionale`
  resta solo il nome logico per compatibilità con il codice e i backup storici.
- **Endpoint backend totali**: 540
- **Collezioni reali sul DB**: 157
- **Pagine (tab) mappate**: 21

---

## 1. Pagine → Componente → Endpoint chiamati

Per ogni pagina dell'app: il componente React che la renderizza e gli endpoint che chiama
(inclusi quelli dei sotto-componenti importati). Tutti verificati esistenti nel backend.

### `analytics` → AnalyticsView
- `/analytics/food-cost-report`
- `/analytics/margine-prodotto`
- `/analytics/scadenzario-pagamenti`
- `/analytics/spesa-fornitori`
- `/analytics/storico-prezzo`
- `/whatsapp/notifica-scadenze`

### `backoffice` → BackofficeView
- `/fornitori`
- `/fornitori/:p`
- `/fornitori/esclusi`
- `/magazzino-bar/prodotti`
- `/ordini-fornitori`
- `/ricette`
- `/ricette/:p`
- `/shelf-life/calcola`

### `catalogo` → CatalogoUnificatoView
- `/prodotti-master`
- `/prodotti-master/rebuild`
- `/prodotti-master/stats`

### `colazione` → ColazioneAcquavivaView
- `/colazione-acquaviva`
- `/colazione-acquaviva/prodotti-disponibili`
- `/colazione-acquaviva/registra`
- `/produzione-mattina/registra`
- `/produzione-mattina/template`

### `comparatore` → ComparatorePrezziView
- `/prodotti-canonici`
- `/prodotti-canonici/:p`
- `/prodotti-canonici/classifica`
- `/prodotti-canonici/da-classificare`
- `/prodotti-canonici/migra-da-listino`
- `/prodotti-canonici/suggerisci-canonico`

### `dashboard` → DashboardView
- `/acquaviva/magazzino-congelatore`
- `/chiusure/giorno-non-produttivo`
- `/diagnostic/salute-sistema`
- `/lotti/:p`
- `/ordini-fornitori/task-produzione-oggi`
- `/produzioni/per-oggi`
- `/supervisor/lotti-in-scadenza`
- `/vendita-banco/oggi`

### `fatture` → ImportaFatture
- *(nessun endpoint diretto rilevato — usa fetch nativo o dati da props)*

### `fornitori` → FornitoriList
- `/fornitori-anagrafica/:p`
- `/fornitori/:p`
- `/fornitori/approva`
- `/fornitori/auto-classifica-horeca`
- `/fornitori/duplicati-per-piva`
- `/fornitori/merge`
- `/fornitori/qualifica`
- `/fornitori/schede-ricevimento`
- `/haccp-auto-manuale/qualifica-fornitore`
- `/haccp-auto-manuale/schede-qualifica`
- `/note-ricevimento/:p`

### `giacenze` → GiacenzeView
- `/lotti-fornitori`
- `/magazzino-bar/prodotti`
- `/magazzino-bar/riordina`
- `/magazzino-bar/soglie-suggest`

### `listino` → ListinoView
- `/fornitori`
- `/listino/alias`
- `/listino/categorie`
- `/listino/prodotti`
- `/listino/sync-da-fatture`
- `/ordini-fornitori`

### `lotti` → LottiList
- `/attrezzature`
- `/lotti/:p`
- `/lotti/cerca-universale`
- `/lotti/recall`
- `/lotti/ricalcola-tracciabilita`
- `/lotti/smalti-batch`
- `/vendita-banco/registro-tracciabilita`

### `materie` → MateriePrimeList
- `/materie-prime/da-fatture`

### `ordini` → OrdiniSmartView
- `/analisi-ordini/verifica-carrello`
- `/ordini-fornitori`
- `/ordini-fornitori/:p`
- `/prodotti-master`
- `/prodotti-master/rebuild`
- `/prodotti-master/stats`

### `pec_import` → SyncGestionaleView
- `/fatture`
- `/fornitori`
- `/fornitori/escludi`
- `/pipeline/esegui`
- `/pipeline/stato`
- `/sync-gestionale/import`
- `/sync-gestionale/status`

### `prodotti` → ProdottiConTabFornitore
- *(nessun endpoint diretto rilevato — usa fetch nativo o dati da props)*

### `produzione_pasticceria` → ProduzionePasticceriaView
- `/produzione-pasticceria`
- `/produzione-pasticceria/genera`
- `/produzione-pasticceria/ricette-disponibili`

### `ricette` → SchedaProdottoView
- `/food-cost/aggiorna-allergeni-ricetta`
- `/food-cost/aggiorna-ingredienti-ricetta`
- `/food-cost/auto-rileva-allergeni-ricetta`
- `/food-cost/calcola`
- `/food-cost/dizionario`
- `/food-cost/semilavorati-acquaviva`
- `/food-cost/storico-prezzi`
- `/lotti`
- `/lotti/recall`
- `/produzioni`
- `/registra-produzione-lotto`
- `/ricette`
- `/ricette-prezzi`
- `/ricette/:p`

### `rosticceria_prod` → RosticceriaView
- `/produzione/genera`
- `/produzione/genera-singolo`
- `/produzione/ricette-disponibili`
- `/produzione/ricette-disponibili${reparto `
- `/produzione/template`

### `schede_tecniche` → SchedeTecnicheView
- `/schede-tecniche/da-proporre`
- `/schede-tecniche/elimina`
- `/schede-tecniche/prodotti`
- `/schede-tecniche/query-ricerca`
- `/schede-tecniche/salva`

### `sconti_merce` → ScontiMerceView
- `/fornitori`
- `/sconti-merce`
- `/sconti-merce/:p`
- `/sconti-merce/importa-da-fatture`
- `/sconti-merce/prodotti-fornitore`
- `/sconti-merce/riepilogo`
- `/sconti-merce/valorizza-da-fatture`

### `storico_produzioni` → StoricoProduzioniView
- `/produzioni`
- `/produzioni/:p`
- `/produzioni/trend`

---

## 2. Collezioni database — stato di verità

### 2a. Collezioni USATE dal codice E presenti sul DB (sicure)

- `acquaviva_prodotti` — 381 documenti
- `alert_prezzi` — 51 documenti
- `allergeni_custom` — 19 documenti
- `anomalie` — 18 documenti
- `anomalie_registro` — 0 documenti
- `attrezzature_config` — 26 documenti
- `colazione_log` — 13 documenti
- `colazione_template` — 1 documenti
- `contatori_lotti` — 37 documenti
- `disinfestazione_annuale` — 9 documenti
- `dizionario_ingredienti` — 4689 documenti
- `dizionario_prodotti` — 932 documenti
- `email_fornitori` — 7 documenti
- `fatture` — 1297 documenti
- `fornitori` — 256 documenti
- `fornitori_anagrafica` — 195 documenti
- `invoices` — 2078 documenti
- `listino_prodotti` — 144 documenti
- `log_scraping` — 6 documenti
- `lotti` — 141 documenti
- `lotti_fornitori` — 17279 documenti
- `magazzino_bar_movimenti` — 16 documenti
- `magazzino_bar_prodotti` — 32 documenti
- `magazzino_movimenti_fornitori` — 3 documenti
- `manuale_haccp_dinamico` — 1 documenti
- `mappature` — 507 documenti
- `mappature_ingredienti` — 249 documenti
- `nome_mapping` — 197 documenti
- `ordini_fornitori` — 71 documenti
- `pipeline_logs` — 120 documenti
- `prodotti_alias` — 5 documenti
- `prodotti_canonici` — 236 documenti
- `prodotti_da_classificare` — 84 documenti
- `prodotti_master` — 2890 documenti
- `prodotti_vendita` — 428 documenti
- `produzione_mattina_template` — 2 documenti
- `produzioni` — 178 documenti
- `ricette` — 91 documenti
- `ricette_libro` — 24 documenti
- `sanificazione` — 7354 documenti
- `sanificazione_apparecchi` — 5 documenti
- `sanificazione_schede` — 60 documenti
- `schede_tecniche` — 3 documenti
- `scheduler_logs` — 1014 documenti
- `sconti_merce` — 882 documenti
- `storico_prezzi` — 679 documenti
- `tablet_operatori` — 15 documenti
- `task_dipendenti` — 57 documenti
- `temperature_negative` — 4998 documenti
- `temperature_positive` — 4968 documenti
- `vendite_banco` — 209 documenti

### 2b. Collezioni usate dal codice ma VUOTE/assenti sul DB (attenzione)

Il codice le referenzia ma sul DB live non hanno documenti: o sono nuove (mai popolate),
o sono rimaste da codice vecchio. Verificare prima di farci affidamento.

- `chiusure_custom`
- `controllo_olio`
- `costi_giornalieri`
- `fornitori_config`
- `fornitori_qualifica`
- `giorni_non_produttivi`
- `materie_prime`
- `note_ricevimento`
- `prodotti_blacklist`
- `produzione_pasticceria_template`
- `produzione_template`
- `reclami_fornitori`
- `ricezioni_merce`
- `saima_ricettari`
- `temperature_cottura`

### 2c. Collezioni sul DB ma NON usate da questo codice

Sono 106 collezioni, in gran parte di **Gestionale2** (stesso cluster Atlas):
contabilità, dipendenti, fatture ERP, movimenti bancari, ecc. **Non toccarle da questo progetto.**

```
  acconti_dipendenti, acquisti_prodotti, agenti_segnalazioni, agenti_stato, 
  agevolazioni_fiscali, alert_definitions, alert_scadenze_f24, alerts, assegni, 
  assegni_learning, attendance_assenze, attendance_presenze_calendario, 
  attendance_timbrature, audit_log, azienda, bonifici_email_attachments, 
  calendario_fiscale, cartelle_email_attachments, cartelle_esattoriali, cash, cedolini, 
  cedolini_email_attachments, centri_costo, ceraldi_erp_clean_state, cespiti, 
  commercialista_log, comparatore_cart, corrispettivi, corrispettivi_manuali, 
  dati_provvisori, dipendenti, disinfestazione, disinfestazione_schede, dizionario_prezzi, 
  documenti_non_associati, documents_inbox, email_accounts, email_message_index, employees, 
  estratti_email_attachments, estratto_conto, estratto_conto_movimenti, 
  extracted_documents, f24, f24_commercialista, f24_email_attachments, f24_email_settings, 
  f24_tributi, f24_unificato, fatture_emesse, fatture_passive, fornitori_keywords, 
  fornitori_metodi, giustificativi, haccp_lotti, job_runs, log_operatori, 
  mittenti_attendibili, mittenti_email, movimenti_bancari, movimenti_contabili, 
  notifications, notifiche_scadenze, operazioni_da_confermare, pagamenti, 
  pagamenti_dipendenti, partite_aperte, paypal_transactions, pec_email_settings, 
  piano_conti, presenze, presenze_giornaliere, prima_nota, prima_nota_banca, 
  prima_nota_cassa, prima_nota_provvisori, prima_nota_salari, quadratura_verifica, 
  quietanze_email_attachments, quietanze_f24, recon_assigns, recon_edits, recon_paid, 
  regole_categorizzazione, riconciliazioni, riconciliazioni_match, riepilogo_cedolini, 
  scadenziario_fornitori, schede_tecniche_jobs, schede_tecniche_prodotti, suppliers, 
  sync_log, system_config, tfr_accantonamenti, tracciabilita, trattenute_dipendenti, 
  user_preferences, user_sessions, users, veicoli_noleggio, verbali_email_attachments, 
  verbali_noleggio, verbali_noleggio_archivio, warehouse_inventory, warehouse_movements, 
  warehouse_stocks
```

---

## 3. Regola d'oro per le modifiche

Prima di modificare o eliminare qualcosa in una pagina:
1. Cerca la pagina nella sezione 1 → vedi quali endpoint usa davvero.
2. Se vuoi togliere un endpoint, verifica che NESSUN'altra pagina lo elenchi.
3. Se tocchi una collezione, controlla la sezione 2: se è in 2c è di Gestionale2, non tua.
4. Le collezioni in 2b sono vuote: non assumere che contengano dati.
