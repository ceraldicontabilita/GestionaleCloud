# Endpoint — Documenti, Email, AI (blocco 06)

<!-- gestionalecloud-doc
status: reference
reviewed_at: 2026-08-20
storage_architecture: drive-only
-->

> [!IMPORTANT]
> Documento di riferimento del dominio. Per persistenza e cutover vale l'architettura Drive-only descritta nei documenti correnti; eventuali nomi legacy/collection restano contesto storico. MongoDB è rimosso e non va usato.

Documentazione dei router: email_download, documenti, documenti_non_associati, documents_inbox_classify, document_ai, ai_parser, enhanced_parser, email_scanner, email_drive_sheets, import_manuale, import_templates, chat_router, learning_machine, learning_universal, learning_machine_cdc.

Contesto: l'import fatture da email è stato unificato su `fatture_upload.process_xml_bytes`; il fix del 502 sul "Vedi" documenti è la decodifica base64 a chunk in `documenti.py /documento/{id}/download`. Gli altri punti che decodificano base64 interi in RAM sono segnalati nelle Note.

---

## email_download.py (/api/email-download) — 39 endpoint

Router più grande del blocco: orchestrazione scarico completo email (PEC/Gmail via `EmailFullDownloader`), gestione allegati PDF non associati, processi AI su fatture/verbali/F24, riconciliazioni (banca, PagoPA, PayPal, POS), anagrafica mittenti attendibili e dizionario Message-ID. Tiene due stati globali in memoria di processo (`download_status`, `_batch_processing_status`): non sopravvivono al riavvio e non sono condivisi tra worker.

### GET /api/email-download/status — stato download
**Cosa fa**: restituisce lo stato del download completo in corso (in_progress, started_at, stats, error).
**Logica codice**: legge il dict globale in memoria `download_status`; nessun accesso DB.
**Note**: stato in-process, perso al riavvio; con più worker ogni processo vede il proprio stato.

### POST /api/email-download/start-full-download — avvia download completo
**Cosa fa**: avvia in background lo scarico di tutte le email con PDF degli ultimi `days_back` giorni dalla cartella IMAP indicata.
**Logica codice**: 400 se già in corso; imposta `download_status`; BackgroundTask che istanzia `EmailFullDownloader(db)` (servizio `email_full_download`) e chiama `download_all_emails(folder, days_back)`; a fine task aggiorna stats/error.

### POST /api/email-download/download-single-day — scarica un giorno
**Cosa fa**: scarica sincrono le email di una singola data (YYYY-MM-DD).
**Logica codice**: valida il formato data (400), chiama `EmailFullDownloader.download_single_day(target_date)`.
**Note**: sincrono, nessun lock: può girare in parallelo al full download.

### GET /api/email-download/documenti-non-associati — lista PDF non associati
**Cosa fa**: lista i PDF scaricati non ancora associati, filtrabili per categoria (max 500).
**Logica codice**: delega a `get_documenti_non_associati(db, category, limit)` del servizio email_full_download (legge le collezioni di `CATEGORY_COLLECTIONS`).

### POST /api/email-download/associa-documento — associazione manuale
**Cosa fa**: associa manualmente un PDF (per id+collezione sorgente) a un documento esistente in una collezione target.
**Logica codice**: delega a `associate_pdf_to_document(...)`; 400 se l'associazione fallisce.
**Note**: parametri passati come query string (non body), inusuale per un POST.

### POST /api/email-download/auto-associa — auto-associazione v1
**Cosa fa**: tenta l'associazione automatica dei PDF ai documenti esistenti.
**Logica codice**: delega a `smart_auto_associate(db)`; ritorna le stats del servizio.

### POST /api/email-download/auto-associa-v2 — auto-associazione v2
**Cosa fa**: versione migliorata: popola pdf_data nei payslips dal filesystem, associa documents_inbox, gestisce fatture/F24/buste paga.
**Logica codice**: delega a `smart_auto_associate_v2(db)`.
**Note**: v1 e v2 coesistono; duplicazione funzionale.

### POST /api/email-download/processa-fatture-email — fatture email con AI (sincrono)
**Cosa fa**: processa fino a `limit` allegati fattura da email: estrae dati con AI e inserisce in `invoices`.
**Logica codice**: legge `fatture_email_attachments` (processed≠true, pdf_data presente); salta estensioni non-PDF (.p7s/.p7m/.xml/...) e file senza magic `%PDF`; `parse_fattura_ai` (servizio `ai_document_parser`) → `convert_ai_fattura_to_db_format`; anti-duplicato su invoice_number/numero_fattura in `invoices`; insert in `invoices` (con pdf_data base64 e metadati email) e marca l'allegato `processed`.
**Note**: NON usa il percorso unificato `fatture_upload.process_xml_bytes`: inserisce direttamente in `invoices` con schema proprio (rischio divergenza/duplicati con l'import unificato). Decodifica base64 dell'intero PDF in RAM e ricopia l'intero base64 dentro `invoices` (duplicazione dati pesante).

### GET /api/email-download/processa-fatture-email/status — stato batch fatture
**Cosa fa**: restituisce lo stato del processo batch fatture email.
**Logica codice**: legge il dict globale `_batch_processing_status`.

### POST /api/email-download/processa-fatture-email/batch — fatture email in batch
**Cosa fa**: avvia in background il processing fatture email a lotti (batch_size≤20, total_limit≤200) per evitare timeout.
**Logica codice**: se già running ritorna lo stato; reset di `_batch_processing_status`; BackgroundTask `_run_batch_processing`: stessa pipeline del sincrono (skip non-PDF, `parse_fattura_ai`, anti-duplicato, insert `invoices`, marca `processed`), pausa 0.5s tra batch.
**Note**: stessa duplicazione del sincrono (bypassa il percorso unificato, copia pdf_data base64 in `invoices`); codice quasi identico duplicato tra i due endpoint. In caso di errore AI marca comunque `processed:true` con campo `error` (il documento non verrà ritentato).

### POST /api/email-download/popola-pdf-payslips — popola pdf_data payslips
**Cosa fa**: popola `pdf_data` nei payslips che hanno solo filepath.
**Logica codice**: delega a `populate_payslips_pdf_data(db)`.

### GET /api/email-download/documents-inbox-stats — stats documents_inbox
**Cosa fa**: statistiche dettagliate su `documents_inbox`.
**Logica codice**: delega a `get_documents_inbox_stats(db)`.

### POST /api/email-download/sync-filesystem — sync filesystem→DB
**Cosa fa**: scansiona /app/documents e allinea i record di `documents_inbox`.
**Logica codice**: delega a `sync_filesystem_pdfs_to_db(db)`.
**Note**: presuppone filesystem persistente; in architettura "Drive/Sheets" è un residuo legacy.

### POST /api/email-download/associa-f24-filesystem — associa F24 da filesystem
**Cosa fa**: associa i PDF F24 su disco ai record `f24_commercialista`.
**Logica codice**: delega a `associate_f24_from_filesystem(db)`.

### POST /api/email-download/processa-cedolini — cedolini → prima nota
**Cosa fa**: estrae dai cedolini scaricati nomi/netto/lordo e crea record in `prima_nota_salari`.
**Logica codice**: delega a `process_cedolini_to_prima_nota(db)`.

### POST /api/email-download/processa-pipeline — pipeline post-download
**Cosa fa**: esegue la pipeline completa post-download: F24, cedolini, verbali, quietanze; collega verbali a veicoli/dipendenti e crea trattenute busta paga.
**Logica codice**: import lazy di `post_download_pipeline.esegui_pipeline_completa(db)`.

### POST /api/email-download/parse-verbali-llm — parsing LLM verbali
**Cosa fa**: parsing LLM dei verbali senza targa (estrae targa, importo, data, ente) e li collega a veicolo/driver.
**Logica codice**: `llm_document_parser.batch_parse_verbali(db, limit)`.

### POST /api/email-download/parse-f24-llm — parsing LLM F24
**Cosa fa**: parsing LLM degli F24 PDF (codici tributo, periodi, importi, sezioni) e salva in `f24_commercialista`.
**Logica codice**: `llm_document_parser.batch_parse_f24(db, limit)`.

### POST /api/email-download/riconcilia-verbali — riconciliazione verbali/banca
**Cosa fa**: riconcilia verbali con estratto conto, PagoPA e PayPal; crea trattenute busta paga per verbali pagati con driver assegnato.
**Logica codice**: `post_download_pipeline.riconcilia_verbali_con_banca(db)`.

### POST /api/email-download/scarica-pdf-verbali-mancanti — recupero PDF verbali
**Cosa fa**: scarica i PDF dei verbali che hanno la cartella Gmail ma non il pdf_data.
**Logica codice**: `post_download_pipeline.scarica_pdf_verbali_mancanti(db)`.

### POST /api/email-download/riconcilia-verbali-avanzato — riconciliazione a 5 strategie
**Cosa fa**: riconciliazione avanzata verbali/banca (numero in descrizione, importo+beneficiario, importo+data ±90gg, quietanze PagoPA/PayPal, importi multipli).
**Logica codice**: `post_download_pipeline.riconcilia_verbali_avanzato(db)`.
**Note**: si sovrappone a /riconcilia-verbali; due varianti dello stesso processo.

### POST /api/email-download/riconcilia-paypal — riconciliazione PayPal
**Cosa fa**: scarica transazioni PayPal e le matcha con verbali non pagati (importo + riferimento).
**Logica codice**: `paypal_integration.riconcilia_verbali_con_paypal(db)`.

### GET /api/email-download/paypal-transazioni — lista transazioni PayPal
**Cosa fa**: lista transazioni PayPal degli ultimi `days_back` giorni.
**Logica codice**: `paypal_integration.cerca_transazioni_paypal(days_back)`; nessun accesso al DB locale.

### POST /api/email-download/riconciliazione-completa — riconciliazione globale
**Cosa fa**: riconciliazione completa per anno: PagoPA, Agenzia Entrate, ADER, TARI + confronto POS.
**Logica codice**: `riconciliazione_completa.riconciliazione_completa(db, anno)`.
**Note**: default `anno=2026` cablato nel codice.

### GET /api/email-download/confronto-pos — confronto POS vs corrispettivi
**Cosa fa**: confronta pagato elettronico dei corrispettivi vs inserimenti manuali serali, per evidenziare discrepanze fiscali.
**Logica codice**: `riconciliazione_completa.confronta_pos_corrispettivi(db, anno)`.

### POST /api/email-download/estrai-importi-verbali — importi mancanti verbali
**Cosa fa**: estrae con regex+LLM l'importo sanzione dai verbali PDF privi di importo.
**Logica codice**: `llm_document_parser.batch_extract_importi_verbali(db, limit)`.
**Note**: default `limit=76`, valore "magico" legato allo stato dati del momento.

### POST /api/email-download/fix-numeri-verbali — correzione numeri verbale
**Cosa fa**: sostituisce numeri fittizi PEC-xxx/DOC-xxx con il numero reale estratto dal PDF (regex+LLM).
**Logica codice**: `llm_document_parser.batch_fix_numeri_verbali(db, limit)`.
**Note**: default `limit=102`, altro valore magico.

### GET /api/email-download/statistiche — stats PDF per categoria
**Cosa fa**: per ogni categoria di `CATEGORY_COLLECTIONS`: totale, associati, non associati, % associati.
**Logica codice**: tre `count_documents` per collezione (`{}`, `associato:true`, `associato:false`).
**Note**: i documenti senza campo `associato` non rientrano né tra associati né tra non associati (i conteggi possono non tornare).

### GET /api/email-download/pdf/{collection}/{pdf_id} — download PDF
**Cosa fa**: restituisce il contenuto binario di un PDF salvato in una delle collezioni categoria o in documents_inbox.
**Logica codice**: whitelist collezioni (CATEGORY_COLLECTIONS + documents_inbox); find_one per id; `base64.b64decode(pdf_data)` e Response inline.
**Note**: decodifica base64 dell'INTERO file in RAM in un colpo solo — stesso pattern che causava il 502 su Documenti; candidato al fix streaming a chunk.

### GET /api/email-download/inbox-documents — lista documents_inbox con PDF
**Cosa fa**: lista documenti di `documents_inbox` che hanno pdf_data (esclude il payload dalla risposta), filtri category/status.
**Logica codice**: find con projection `pdf_data:0`, sort per downloaded_at desc, + count totale con pdf_data.

### DELETE /api/email-download/pulisci-duplicati — dedup per hash
**Cosa fa**: elimina i PDF duplicati (stesso `pdf_hash`) in tutte le collezioni categoria, tenendo il primo.
**Logica codice**: aggregate `$group` per pdf_hash con count>1, `delete_many` sugli id successivi al primo.

### GET /api/email-download/mittenti — lista mittenti
**Cosa fa**: lista i mittenti email configurati, con split pec/gmail.
**Logica codice**: find su `mittenti_email` (max 200).

### GET /api/email-download/mittenti/check — verifica mittente attendibile
**Cosa fa**: dice se un indirizzo è attendibile per il canale (pec/gmail) e con quale tipo_documento.
**Logica codice**: carica i mittenti attivi del canale e fa match per contenimento stringa (`pattern in from_addr.lower()`).

### POST /api/email-download/mittenti — nuovo mittente
**Cosa fa**: aggiunge un mittente custom (pattern, canale, tipo_documento).
**Logica codice**: valida pattern obbligatorio e canale ∈ {pec, gmail}; 409 se pattern già presente per il canale; insert in `mittenti_email` con builtin=false.

### DELETE /api/email-download/mittenti/{mittente_id} — elimina mittente
**Cosa fa**: elimina un mittente non-builtin (lookup per id o per pattern).
**Logica codice**: find_one su id|pattern; 403 se builtin; delete_one.

### PUT /api/email-download/mittenti/{mittente_id} — aggiorna mittente
**Cosa fa**: aggiorna un mittente: attivo/descrizione sempre; pattern/canale/tipo solo se non builtin.
**Logica codice**: find_one su id|pattern, costruisce `$set` selettivo, update_one.

### GET /api/email-download/dizionario-email — indice Message-ID
**Cosa fa**: mostra il dizionario delle email già scaricate (anti re-download).
**Logica codice**: count + ultimi N record di `email_message_index` per seen_at desc.

### DELETE /api/email-download/dizionario-email/reset — reset dizionario
**Cosa fa**: svuota `email_message_index` forzando il re-download di tutte le email.
**Logica codice**: `delete_many({})`.
**Note**: operazione distruttiva senza conferma; al sync successivo tutte le email vengono ritrattate.

### POST /api/email-download/sync-email-now — trigger sync manuale
**Cosa fa**: avvia in background un sync email di 30 giorni.
**Logica codice**: BackgroundTask su `email_monitor_service.sync_email_documents(db, giorni=30)`.
**Note**: si affianca a `/api/documenti/monitor/sync-now` che usa lo stesso servizio (duplicazione di trigger).

---

## documenti.py (/api/documenti) — 32 endpoint

Pagina "Documenti Email": monitor IMAP periodico (`email_monitor_service`), download allegati (`email_document_downloader`) in `documents_inbox`, visualizzazione/gestione documenti (architettura Drive/Sheets con pdf_data base64), pipeline di processamento per tipo (F24, buste paga, estratti Nexi/BNL) e upload manuale con autodetect. Contiene il fix streaming del 502 sul download.

### POST /api/documenti/monitor/start — avvia monitor email
**Cosa fa**: avvia il polling automatico della posta ogni `intervallo_minuti` (default 10).
**Logica codice**: `email_monitor_service.start_monitor(db, secondi)`; ritorna stato monitor.

### POST /api/documenti/monitor/stop — ferma monitor
**Cosa fa**: ferma il monitoraggio automatico.
**Logica codice**: `stop_monitor()` + `get_monitor_status()`.

### GET /api/documenti/monitor/status — stato monitor
**Cosa fa**: stato del monitor + conteggi documents_inbox (totali/processati/da processare).
**Logica codice**: `get_monitor_status()` + due `count_documents` su `documents_inbox`.

### POST /api/documenti/monitor/sync-now — sync immediato
**Cosa fa**: esegue subito un ciclo completo: scarica nuovi documenti, ricategorizza, processa.
**Logica codice**: `email_monitor_service.run_full_sync(db)` (sincrono).

### GET /api/documenti/telegram/status — config Telegram
**Cosa fa**: verifica se le notifiche Telegram sono configurate (token e chat id in .env).
**Logica codice**: `telegram_notifications.is_configured()` + flag presenza variabili.

### POST /api/documenti/telegram/test — test Telegram
**Cosa fa**: invia un messaggio di prova su Telegram.
**Logica codice**: `telegram_notifications.test_connection()`; 400 se non configurato.

### GET /api/documenti/lista — lista documents_inbox
**Cosa fa**: lista paginata dei documenti scaricati con filtri categoria/status + conteggi per categoria e status.
**Logica codice**: find su `documents_inbox` sort downloaded_at desc; due aggregate `$group` (category, status); count totale con filtro.

### GET /api/documenti/lock-status — stato lock operazioni
**Cosa fa**: dice se c'è un'operazione email/DB in corso e quale.
**Logica codice**: legge `asyncio.Lock` globale `_email_operation_lock` + `_current_operation` (in-process).

### POST /api/documenti/scarica-da-email — download allegati email
**Cosa fa**: scarica gli allegati dalle email degli ultimi N giorni (filtro parole chiave opzionale); con `background=true` ritorna un task_id da pollare.
**Logica codice**: 423 se lock già preso; credenziali da env (EMAIL_USER/EMAIL_APP_PASSWORD, 400 se mancanti); sincrono chiama `download_documents_from_email(...)`; in background crea task in `_download_tasks` e `asyncio.create_task(_execute_email_download)` che prende il lock, esegue e aggiorna lo stato del task.
**Note**: registro task in memoria (perso al riavvio, non multi-worker).

### GET /api/documenti/task/{task_id} — stato task download
**Cosa fa**: ritorna lo stato di un task di download in background.
**Logica codice**: legge `_download_tasks`; come side-effect elimina i task completati da >1h.

### GET /api/documenti/categorie — elenco categorie
**Cosa fa**: ritorna `CATEGORIES` (f24, fattura, busta_paga, estratto_conto, quietanza, bonifico, altro) con descrizioni.
**Logica codice**: statico, nessun DB.

### GET /api/documenti/documento/{doc_id} — dettaglio documento
**Cosa fa**: dettaglio singolo documento di documents_inbox.
**Logica codice**: find_one per id, 404 se assente.
**Note**: la risposta include anche `pdf_data` intero (nessuna projection): payload potenzialmente enorme in JSON.

### GET /api/documenti/documento/{doc_id}/download — download file (fix 502)
**Cosa fa**: scarica il file del documento come attachment PDF.
**Logica codice**: find_one su documents_inbox; 404 se manca pdf_data; **decodifica base64 a chunk da 1MB (multipli di 4) via generatore + StreamingResponse** — è il fix del 502/OOM documentato nel commento.
**Note**: unico endpoint del blocco con lo streaming; gli analoghi endpoint /pdf altrove decodificano ancora tutto in RAM.

### POST /api/documenti/documento/{doc_id}/processa — marca processato
**Cosa fa**: marca il documento come processato verso una destinazione (f24, fatture, buste_paga, estratto_conto, quietanze).
**Logica codice**: valida destinazione contro mappa fissa; update di status/processed/processed_to su documents_inbox.
**Note**: NON carica davvero nulla nella destinazione (la risposta lo ammette: "usa l'endpoint di upload specifico"); il nome inganna.

### POST /api/documenti/documento/{doc_id}/cambia-categoria — ricategorizza
**Cosa fa**: cambia la categoria di un documento (solo metadati).
**Logica codice**: valida contro CATEGORIES; update di category/category_label.

### DELETE /api/documenti/documento/{doc_id} — elimina documento
**Cosa fa**: elimina un documento da documents_inbox.
**Logica codice**: find_one + delete_one; 404 se assente.

### POST /api/documenti/elimina-processati — pulizia processati
**Cosa fa**: elimina tutti i documenti con processed=true.
**Logica codice**: count + `delete_many({"processed": True})`.

### GET /api/documenti/statistiche — statistiche documenti
**Cosa fa**: totali, nuovi, processati, breakdown per categoria, ultimo download, spazio disco.
**Logica codice**: count + aggregate su documents_inbox; scandisce `DOCUMENTS_DIR` su filesystem per calcolare i MB.
**Note**: "ultimo_download" usa `find_one` senza sort → NON è realmente l'ultimo. Il calcolo spazio disco è legacy rispetto all'architettura Drive/Sheets.

### GET /api/documenti/cartelle-email — lista cartelle IMAP
**Cosa fa**: elenca le cartelle IMAP dell'account Gmail configurato.
**Logica codice**: connessione imaplib sincrona a imap.gmail.com con credenziali env, `conn.list()`, parse dei nomi; fallback ["INBOX"] su errore.
**Note**: I/O bloccante dentro handler async (blocca l'event loop durante la connessione IMAP).

### POST /api/documenti/sync-f24-automatico — sync F24 da email
**Cosa fa**: scarica dalle email solo gli F24 (max 30 email), li parsa e li carica; segna le quietanze come pronte.
**Logica codice**: `download_documents_from_email` → filtra category f24/quietanza; per ogni F24: b64decode pdf_data, `parser_f24.parse_f24_commercialista(pdf_content)`; costruisce DUE record (formato "commercialista" e formato "f24_models" con tributi rimappati per sezione + pdf_data) e li inserisce ENTRAMBI in `f24_unificato`; aggiorna documents_inbox; le quietanze vengono solo marcate `ready_for: quietanze_f24`.
**Note**: il docstring/campi parlano di f24_commercialista/f24_models ma la collection reale è `f24_unificato`, che riceve due schemi diversi per lo stesso F24 (doppio inserimento, anti-duplicato con chiavi diverse: `file_name` vs `filename`). Questa coesistenza di schemi è confermata dal commento in chat_router (`_f24_anno`).

### POST /api/documenti/processa-f24-scaricati — riprocessa F24 in inbox
**Cosa fa**: processa gli F24 già in documents_inbox non ancora processati.
**Logica codice**: find f24 non processati (max 100); b64decode; `parse_f24_commercialista`; controlla `parsed.get("success")` e `parsed["f24_data"]`; anti-duplicato su file_name; insert in `f24_unificato`; aggiorna documents_inbox.
**Note**: BUG probabile: il parser restituisce il risultato direttamente (come gestito in sync-f24-automatico, che controlla `parsed.get("error")`), non un wrapper `{success, f24_data}` — qui il ramo di successo non scatta quasi mai e tutto finisce in "Parsing fallito".

### GET /api/documenti/ultimo-sync — info ultimo sync F24
**Cosa fa**: ultimo documento F24 scaricato, F24 da processare, ultimo F24 auto-importato.
**Logica codice**: find_one su documents_inbox (category f24), count non processati, find_one su f24_unificato auto_imported.
**Note**: entrambi i `find_one` sono senza sort: "ultimo" non è garantito.

### POST /api/documenti/sync-estratti-conto — processa estratti Nexi
**Cosa fa**: processa gli estratti conto non processati della inbox col parser Nexi; salva estratto + transazioni singole.
**Logica codice**: find estratti non processati (100); b64decode; `EstrattoContoNexiParser.parse_pdf`; insert in `estratto_conto_nexi` (con pdf_data) + una riga per transazione in `estratto_conto_movimenti` (riconciliato=false); aggiorna documents_inbox; gestisce il caso "solo riepilogo".
**Note**: anti-duplicato solo sul record estratto (filename), non sulle transazioni.

### POST /api/documenti/sync-buste-paga — processa buste paga
**Cosa fa**: parsa le buste paga PDF della inbox (una pagina = un cedolino), salva in `cedolini` e crea movimenti in `prima_nota_salari`.
**Logica codice**: find busta_paga non processate (500); cache dipendenti (match per CF o COGNOME NOME); `PayslipPDFParser(pdf_content).parse()`; per pagina: anti-duplicato (cf, mese, anno) in `cedolini`, insert cedolino con pdf_data; se netto>0 e dipendente trovato crea movimento `prima_nota_salari` (anti-duplicato dipendente+mese+anno); aggiorna documents_inbox.
**Note**: il pdf_data base64 dell'INTERO file viene duplicato dentro ogni cedolino estratto (un LUL multi-pagina moltiplica il payload). Se tutti i cedolini sono duplicati marca `processed_to: "payslips"` (incoerente con la collection reale `cedolini`).

### POST /api/documenti/riepilogo-cedolini — genera riepilogo cedolini
**Cosa fa**: (ri)genera la collezione `riepilogo_cedolini` (dipendente, periodo, netto, lordo, trattenute, IBAN) parsando tutte le buste paga.
**Logica codice**: find su documents_inbox busta_paga con pdf_data (fino a 5000, projection con pdf_data incluso); b64decode; `payslip_parser_v2.parse_payslip_pdf`; upsert per (cf, mese, anno) con pdf_data nel record; aggregate finale per dipendente.
**Note**: RISCHIO MEMORIA: `to_list(5000)` carica in RAM fino a 5000 documenti COMPLETI di base64 — stesso profilo dell'OOM/502 già fixato sul download. Inoltre pdf_data viene duplicato in ogni record di riepilogo. Il parametro `riprocessa` è dichiarato ma mai usato.

### GET /api/documenti/riepilogo-cedolini — lista riepilogo cedolini
**Cosa fa**: lista il riepilogo cedolini con filtri dipendente/anno + totali (netto, lordo, trattenute).
**Logica codice**: find su `riepilogo_cedolini` sort anno/mese desc + aggregate dei totali con lo stesso filtro.
**Note**: la projection esclude solo `_id`: gli oggetti restituiti includono anche il pdf_data salvato nel riepilogo (payload pesante in lista).

### GET /api/documenti/confronto-cedolini-prima-nota — confronto cedolini/prima nota
**Cosa fa**: confronta riepilogo_cedolini con prima_nota_salari: cedolini senza movimento, differenze importo (>1€).
**Logica codice**: carica entrambe le collezioni (10000), indicizza, match per nome dipendente+mese+anno (loop annidato O(n·m)).
**Note**: il match è per nome (non CF/id) e "movimenti senza cedolino" dichiarato in docstring non viene in realtà calcolato.

### POST /api/documenti/sync-estratti-bnl — processa estratti BNL
**Cosa fa**: processa estratti conto BNL (anche se archiviati in categoria "altro" con "BNL" nel filename); salva estratto e transazioni.
**Logica codice**: find non processati in estratto_conto o altro+regex BNL (200); filtro filename BNL; b64decode; `parse_estratto_conto_bnl`; insert `estratto_conto_bnl` (con pdf_data) + righe in `estratto_conto_movimenti`; ricategorizza il documento se era "altro".
**Note**: come per Nexi, anti-duplicato solo sull'estratto, non sulle singole transazioni.

### POST /api/documenti/ricategorizza-documenti — ricategorizzazione euristica
**Cosa fa**: sposta i documenti da "altro" a estratto_conto/busta_paga/f24 in base a keyword nel filename (bnl, estratto, paga, f24, paypal...).
**Logica codice**: find altro non processati (500); regole if/elif sul filename; update category/category_label.

### POST /api/documenti/processa-tutti — pipeline combinata
**Cosa fa**: esegue in sequenza: ricategorizza → buste paga → estratti Nexi → estratti BNL, con sommario.
**Logica codice**: chiama direttamente le quattro funzioni endpoint interne, ognuna in try/except separato.

### POST /api/documenti/reimporta-da-filesystem — migrazione legacy da disco
**Cosa fa**: scansiona le cartelle categoria su disco e reimporta i file in documents_inbox come base64 (flag `force` per sovrascrivere).
**Logica codice**: itera `/tmp/documents/<Categoria>`; legge il file, hash MD5, b64encode; anti-duplicato per file_hash; ricategorizzazione euristica dal filename; insert/update in documents_inbox.
**Note**: DEPRECATO (dichiarato nel codice). Il docstring dice `/app/documents` ma il codice usa `/tmp/documents` (docstring mente). Carica ogni file intero in RAM (accettabile per migrazione una tantum).

### POST /api/documenti/upload-auto — upload con autodetect tipo
**Cosa fa**: upload manuale di un file con riconoscimento automatico del tipo e smistamento al workflow giusto (corrispettivo XML, fattura XML, F24, quietanza, cedolino/LUL, distinte BPM, estratto conto CSV, bonifici); se non riconosciuto salva in documents_inbox.
**Logica codice**: `detect_document_type` (estensione, keyword filename, primi 5KB del contenuto); dispatch: corrispettivo→`corrispettivi_helpers.ingest_corrispettivo_parsed` (anti-duplicato + Prima Nota); fattura→`fatture_upload.parse_fattura_xml`+`process_fattura_to_db` (percorso unificato); f24→`f24_parser.import_f24` (workflow completo); quietanza→`parser_f24.parse_f24_pdf_bytes`→insert `quietanze_f24`; cedolino→`libro_unico_parser.import_libro_unico`; distinte→`distinte_bpm.import_distinte_bpm`; estratto→`bank.estratto_conto.import_estratto_conto` (via classe FakeUpload); bonifici e non riconosciuti→documents_inbox base64 + evento `DOCUMENTO_ACQUISITO` su event bus.
**Note**: `await file.read()` carica l'intero file in RAM (nessun limite dimensione qui, a differenza di document-ai/enhanced-parser che limitano a 20MB). Il ramo fattura usa correttamente il percorso unificato fatture_upload.

---

## documenti_non_associati.py (/api/documenti-non-associati) — 7 endpoint

Gestione della collezione `documenti_non_associati`: lista con proposta intelligente di associazione (regex su filename/subject), associazione manuale a collezioni target, statistiche per categoria mittente, visualizzazione file (con estrazione PDF da P7S/P7M firmati).

### GET /api/documenti-non-associati/categorie-mittente — stats per mittente
**Cosa fa**: conteggi dei documenti non associati raggruppati per categoria mittente (INPS, Agenzia Entrate, ecc.) con icone e anteprima.
**Logica codice**: filtro mittenti attendibili da `mittenti_email` (regex email_from) + categorie note; aggregate `$group` su categoria_mittente in `documenti_non_associati`.
**Note**: il `$push` di documenti_recenti nel group accumula TUTTI i documenti del gruppo in memoria aggregation (poi tronca a 3 in Python) — inefficiente su volumi alti.

### GET /api/documenti-non-associati/lista — lista con proposta
**Cosa fa**: lista paginata dei documenti non associati da mittenti attendibili, con filtri categoria/search e una "proposta" di associazione per ciascuno.
**Logica codice**: filtro base associato≠true + regex mittenti attivi (o categoria già classificata); aggregation con `$project pdf_data:0` e allowDiskUse; per ogni doc `genera_proposta_associazione` (regex su filename/subject: anno, mese, targa, importo, tipo→collezione; lookup fino a 5 match esistenti nella collezione suggerita).

### POST /api/documenti-non-associati/associa — associazione manuale
**Cosa fa**: associa un documento a una collezione target: crea un nuovo record (crea_nuovo=true) o attacca il PDF a un record esistente.
**Logica codice**: find su `documenti_non_associati` (400 se senza pdf_data); insert nuovo record con pdf_data+campi_associazione, oppure update_one del record esistente con pdf_data; marca il documento `associato:true` con riferimenti.
**Note**: la whitelist TARGET_COLLECTIONS non è vincolante: se la collezione non è in lista viene comunque usata (solo log "Creazione nuova collezione") — si può scrivere in una collezione arbitraria via API. Il pdf_data viene copiato (non spostato): dato duplicato.

### GET /api/documenti-non-associati/statistiche — statistiche
**Cosa fa**: totale/associati/da associare, per categoria.
**Logica codice**: aggregate `$group` per category con `$cond` su associato.

### GET /api/documenti-non-associati/collezioni-disponibili — collezioni target
**Cosa fa**: elenco value/label delle collezioni disponibili per l'associazione.
**Logica codice**: statico da TARGET_COLLECTIONS.

### GET /api/documenti-non-associati/pdf/{documento_id} — visualizza file
**Cosa fa**: restituisce il file per la visualizzazione: PDF, immagini, XML/CSV/TXT; estrae il PDF interno dai P7S/P7M firmati.
**Logica codice**: find_one con projection; b64decode (fallback encode se non base64); sanitizzazione filename per header; media type da estensione o magic bytes; `extract_pdf_from_p7s` (ricerca marker %PDF-...%%EOF nel binario) per file firmati; 422 se PDF non valido.
**Note**: decodifica base64 dell'intero file in RAM (Response non streaming) — stesso pattern del 502; da valutare il fix a chunk come in documenti.py.

### DELETE /api/documenti-non-associati/{documento_id} — elimina
**Cosa fa**: elimina un documento non associato.
**Logica codice**: delete_one per id; 404 se non trovato.

---

## documents_inbox_classify.py (/api/documenti-inbox) — 5 endpoint

Auto-classificazione dei documenti in `documents_inbox` (Gmail/PEC) tramite regex su filename/subject/mittente (17 pattern: f24, cu, cedolino, verbale, xml_sdi, ...), con auto-associazione a dipendenti e creazione tributi F24; include import anagrafica dipendenti dai filename delle CU e cross-check F24 vs `f24_tributi`.

### POST /api/documenti-inbox/auto-classify — classifica inbox
**Cosa fa**: scansiona documents_inbox, assegna `categoria` in base ai pattern e auto-associa: cedolini/CU al dipendente (CF o cognome), F24 con importo+scadenza creano record in `f24_tributi`. Supporta dry_run.
**Logica codice**: find fino a 10000 doc (filtro senza categoria se solo_non_classificati); preload `dipendenti` (5000); `classify_by_text` sui PATTERNS; estrazione testo PDF con pypdf (prime 3 pagine) e regex importo/scadenza/CF; update documents_inbox; insert condizionale in `f24_tributi` (anti-duplicato su scadenza+importo).
**Note**: l'estrazione testo scatta solo se `pdf_data` è `bytes`, ma nel resto del sistema pdf_data è salvato come STRINGA base64 → il ramo di lettura contenuto PDF di fatto non viene quasi mai eseguito (classificazione basata quasi solo su filename/subject). Il campo qui è `categoria`, mentre il resto del blocco usa `category`: due tassonomie parallele sulla stessa collection.

### GET /api/documenti-inbox/statistics — statistiche classificazione
**Cosa fa**: totali, non classificati, breakdown per `categoria`, cedolini/CU con dipendente associato.
**Logica codice**: count + aggregate `$group` su categoria.

### POST /api/documenti-inbox/import-dipendenti-from-cu — anagrafica da CU
**Cosa fa**: crea i dipendenti mancanti in `dipendenti` estraendo CF/cognome/nome dal filename delle Certificazioni Uniche (pattern "CF - anno - COGNOME NOME (...)"). Supporta dry_run.
**Logica codice**: find CU in documents_inbox; regex sul filename; dedup per CF contro `dipendenti` esistenti; euristica split cognome/nome (metà/metà se >3 parole); insert_many.
**Note**: l'euristica sui nomi composti è dichiaratamente approssimativa (da correggere a mano).

### GET /api/documenti-inbox/cross-check-f24 — confronto inbox vs f24_tributi
**Cosa fa**: confronta gli F24 classificati in inbox con `f24_tributi`: matched / solo inbox (da importare) / solo tributi (senza PDF).
**Logica codice**: carica entrambe le collezioni (5000); chiave di confronto (data, importo) con doppio schema (scadenza+importo vs data_pagamento+totale_versato); set intersection/difference.

### POST /api/documenti-inbox/import-f24-from-inbox — importa tributi F24
**Cosa fa**: crea in `f24_tributi` un record per OGNI riga tributo degli F24 in inbox con dati AI (totale_versato>0), evitando i già presenti. Supporta dry_run.
**Logica codice**: find F24 con totale_versato>0; chiave anti-duplicato (data, importo netto debito-credito, codice_tributo) contro l'esistente; insert_many con origine documents_inbox_import e stato "da_verificare".

---

## document_ai.py (/api/document-ai) — 10 endpoint

Estrazione dati strutturati da documenti via LLM (servizio `document_ai_extractor`, prompt per tipo: f24, busta_paga, estratto_conto, bonifico, verbale, cartella, delibera INPS, fattura, generico). Archivio risultati in `extracted_documents`; integrazione con la pipeline dei documenti classificati (`documents_classified`, servizio `email_classifier_service`) e salvataggio nelle collection del gestionale (`document_data_saver`).

### POST /api/document-ai/extract — estrai da file
**Cosa fa**: upload di PDF/immagine, estrazione dati strutturati con LLM (tipo auto-rilevato o forzato); opzionale salvataggio in `extracted_documents` + collection gestionale.
**Logica codice**: valida vuoto/20MB; `process_document(file_data, filename, document_type, model)`; se save_to_db: anti-duplicato per filename in `extracted_documents`, insert con `file_base64` intero, poi `save_extracted_data_to_gestionale` (document_data_saver).
**Note**: il docstring dice "default: gpt-4o" ma il default reale è `claude-sonnet-4-5-20250929` (docstring mente). Salva il file intero base64 in `extracted_documents` (payload pesante). Anti-duplicato solo per filename (file diversi con stesso nome vengono scartati).

### POST /api/document-ai/extract-base64 — estrai da base64
**Cosa fa**: come /extract ma con input base64 (per documenti già in DB).
**Logica codice**: `process_document_from_base64(...)`; se save_to_db insert in `extracted_documents` (senza file_base64 e SENZA controllo duplicati, a differenza di /extract).

### POST /api/document-ai/extract-text-only — solo testo (debug)
**Cosa fa**: estrae il solo testo da un PDF (con eventuale OCR) e il tipo rilevato, senza LLM.
**Logica codice**: `extract_text_from_pdf(content)` + `detect_document_type(text)`; solo .pdf (400 altrimenti).

### GET /api/document-ai/document-types — tipi supportati
**Cosa fa**: elenco dei tipi documento supportati (chiavi di PROMPTS) con descrizioni.
**Logica codice**: statico.

### GET /api/document-ai/extracted-documents — archivio estrazioni
**Cosa fa**: lista paginata dei documenti estratti (filtro tipo); `include_file=true` include il base64.
**Logica codice**: find su `extracted_documents` con projection, sort created_at desc; converte `_id` identificatore interno in stringa `id`.

### DELETE /api/document-ai/extracted-documents/{doc_id} — elimina estrazione
**Cosa fa**: elimina un documento estratto per identificatore interno.
**Logica codice**: `delete_one({"_id": identificatore interno(doc_id)})`; 404 se non trovato.
**Note**: il try/except esterno intercetta anche l'HTTPException 404 e la ritrasforma in 500 (status code sbagliato per "non trovato" e per identificatore interno invalido).

### POST /api/document-ai/process-classified-email — processa singolo classificato
**Cosa fa**: estrae i dati (LLM) da un documento della pipeline email `documents_classified` e aggiorna il record con extracted_data.
**Logica codice**: lookup per identificatore interno o msg_id; richiede `pdf_base64`; mappa tipo email→tipo documento; `process_document_from_base64`; update con extracted_data/processed.

### POST /api/document-ai/process-all-classified — processa tutti i classificati
**Cosa fa**: processa in massa i documenti classificati con AI e salva nelle collection del gestionale (filtri per tipo, flag riprocessa).
**Logica codice**: delega a `email_classifier_service.process_documents_with_ai(db, process_all, types, save_to_gestionale, model)`.
**Note**: sincrono, senza BackgroundTasks: su molti documenti rischia timeout HTTP.

### GET /api/document-ai/classified-documents-stats — stats classificati
**Cosa fa**: statistiche per tipo su `documents_classified`: totale, con PDF, AI processati/da processare, salvati nel gestionale.
**Logica codice**: aggregate `$group` per tipo con `$cond` sui flag.

### POST /api/document-ai/reprocess-and-save — riprocessa tutto
**Cosa fa**: riprocessa TUTTI i documenti classificati e risalva nel gestionale (dopo aggiornamenti ai prompt).
**Logica codice**: `process_documents_with_ai(process_all=True, save_to_gestionale=True)`.
**Note**: wrapper ridondante di /process-all-classified con parametri fissi; stesso rischio timeout.

---

## ai_parser.py (/api/ai-parser) — 11 endpoint

Parser AI (servizio `ai_document_parser`, Anthropic) per fatture/F24/buste paga con upload diretto; integrazione Learning Machine (keywords fornitori → centro di costo, mappatura codici tributo → CDC); sezione "da rivedere" per revisione manuale (`ai_integration_service`).

### POST /api/ai-parser/parse — parse generico
**Cosa fa**: parsa un PDF/immagine col tipo indicato o auto-rilevato; opzionale salvataggio nella collezione per tipo.
**Logica codice**: `parse_document_with_ai(file_bytes, document_type, mime_type)`; se save_to_db: fattura→`convert_ai_fattura_to_db_format`+insert `invoices`; f24→insert `f24_unificato`; busta_paga→insert `cedolini_parsed`; sempre con pdf_data base64 intero nel record.
**Note**: la fattura salvata bypassa il percorso unificato fatture_upload e non ha controllo duplicati. Incoerenza: qui l'F24 va in `f24_unificato`, in /parse-f24 va in `f24_parsed`.

### POST /api/ai-parser/parse-fattura — parse fattura + learning CDC
**Cosa fa**: parsa una fattura e, se il fornitore è configurato in `fornitori_keywords`, suggerisce il centro di costo; opzionale insert in `invoices`.
**Logica codice**: `parse_fattura_ai`; lookup regex su `fornitori_keywords` per denominazione fornitore; se save_to_db insert in `invoices` con pdf_data e CDC suggerito.
**Note**: il nome fornitore è interpolato direttamente in una `$regex` (caratteri speciali nel nome rompono/alterano il match); nessun controllo duplicati.

### POST /api/ai-parser/parse-f24 — parse F24 + mappatura tributi
**Cosa fa**: parsa un F24 e assegna ai tributi il centro di costo tramite mappa statica codice→CDC (1001, DM10, 6001..., 3801...).
**Logica codice**: `parse_f24_ai`; loop sulle sezioni (erario/inps/regioni/imu) applicando la mappa hardcoded; se save_to_db insert in `f24_parsed` con pdf_data.
**Note**: `f24_parsed` è un'ULTERIORE collezione F24 (oltre f24_unificato, f24_commercialista, f24_tributi, f24_quietanze): frammentazione dati F24 su 5 collezioni.

### POST /api/ai-parser/parse-busta-paga — parse cedolino + update dipendente
**Cosa fa**: parsa una busta paga; individua il dipendente (id passato o CF estratto) e ne aggiorna i progressivi (TFR, retribuzione, ultimo cedolino); opzionale insert in `cedolini_parsed`.
**Logica codice**: `parse_busta_paga_ai`; lookup `dipendenti` per codice_fiscale; `convert_ai_busta_paga_to_dipendente_update` → update_one dipendenti; insert cedolino con pdf_data se save_to_db.

### POST /api/ai-parser/batch-parse — parse multiplo
**Cosa fa**: parsa più file in sequenza col tipo indicato; ritorna risultati aggregati.
**Logica codice**: loop su files, `parse_document_with_ai` per ciascuno, contatori success/error.
**Note**: il parametro save_to_db è accettato ma IGNORATO: non salva mai nulla (docstring/firma ingannevoli). Sequenziale e sincrono: molti file = richiesta lunga.

### GET /api/ai-parser/test — check configurazione
**Cosa fa**: verifica che ANTHROPIC_API_KEY sia configurata ed elenca gli endpoint disponibili.
**Logica codice**: load_dotenv + lettura env; risposta statica.

### GET /api/ai-parser/da-rivedere — documenti da revisionare
**Cosa fa**: lista i documenti che richiedono revisione manuale (needs_review, non classificati, confidence bassa, errori parsing), filtro per tipo.
**Logica codice**: find su `documents_inbox` con $or sui flag AI, projection senza pdf_data, sort ai_parsed_at desc; conteggio per tipo in Python.
**Note**: importa `get_documents_for_review` da ai_integration_service ma non lo usa (query duplicata inline).

### POST /api/ai-parser/da-rivedere/process-batch — "riprocessa" batch
**Cosa fa** (reale): marca fino a 200 record di `extracted_documents` con status da_rivedere/needs_review/low_confidence come `status: "reprocessed"`.
**Logica codice**: find + update_one per ciascuno; nessuna chiamata AI.
**Note**: il docstring dice "riprocessa con il parser AI" ma NON esegue alcun parsing: cambia solo lo status (docstring mente). Opera su `extracted_documents` mentre la GET /da-rivedere legge `documents_inbox`: le due viste non sono coerenti.

### PUT /api/ai-parser/da-rivedere/{document_id}/classifica — classificazione manuale
**Cosa fa**: assegna manualmente centro di costo (e note) a un documento in revisione.
**Logica codice**: risolve il nome CDC da `centri_costo` se mancante; `ai_integration_service.mark_document_reviewed(...)`.

### POST /api/ai-parser/process-email-batch — parse batch documenti email
**Cosa fa**: esegue il parsing AI su un batch (max 100) di documenti email non ancora processati.
**Logica codice**: `ai_integration_service.process_email_documents_batch(db, limit)`.

### GET /api/ai-parser/statistiche — stats parsing AI
**Cosa fa**: totale parsati, da rivedere, auto-classificati, errori, pending, breakdown per tipo, classification_rate.
**Logica codice**: count_documents multipli + aggregate su `documents_inbox` (flag ai_parsed / ai_parsed_type / ai_parsing_error).

---

## enhanced_parser.py (/api/enhanced-parser) — 4 endpoint

Parser "v2" LLM (servizio `enhanced_document_parser`, Claude Sonnet 4.5) specializzato su F24 (tutte le sezioni/tributi con validazione incrociata) e cedolini multi-formato (Zucchetti, TeamSystem, ADP...). Solo parsing: non scrive mai sul DB. Montato con prefix `/api` + prefix interno `/enhanced-parser`.

### POST /api/enhanced-parser/f24 — parse F24 completo
**Cosa fa**: estrae da un F24 tutti i tributi di ogni sezione (Erario, INPS, Regioni, IMU, INAIL), totali e saldi con validazione.
**Logica codice**: valida vuoto/20MB; mime type da estensione; `parse_f24_enhanced(content, mime_type)`; nessuna scrittura DB.

### POST /api/enhanced-parser/cedolino — parse cedolino multi-formato
**Cosa fa**: estrae dati dipendente, competenze/trattenute, netto validato, TFR/ferie da cedolini in vari formati gestionali.
**Logica codice**: valida vuoto/20MB; `parse_cedolino_enhanced(content, mime_type)`; nessuna scrittura DB.

### POST /api/enhanced-parser/auto — parse con autodetect
**Cosa fa**: parsa F24 o cedolino rilevando automaticamente il tipo (o forzandolo).
**Logica codice**: `parse_document_enhanced(content, document_type, mime_type)`.
**Note**: manca il check 20MB presente negli altri due endpoint (incoerenza minore).

### GET /api/enhanced-parser/info — info parser
**Cosa fa**: metadati statici del parser (versione, feature, formati, modello).
**Logica codice**: risposta statica.
**Note**: coesiste con ai_parser (/parse-f24, /parse-busta-paga) e document_ai (/extract): TRE parser LLM paralleli per gli stessi tipi documento.

---

## email_scanner.py (/api/email-scanner) — 5 endpoint

Scanner "completo" della posta per cartelle Gmail tematiche (servizio `email_scanner_completo`): classifica le cartelle per tipo (verbali, esattoriali, F24...), scarica i documenti e li associa ai verbali/fatture.

### GET /api/email-scanner/cartelle — cartelle classificate
**Cosa fa**: elenca le cartelle email raggruppate per tipo (prime 20 per tipo) con conteggi.
**Logica codice**: `get_cartelle_da_scansionare()`.

### POST /api/email-scanner/scansiona — scansione cartelle
**Cosa fa**: scansiona le cartelle (per tipo, con limiti cartelle/email) e salva i nuovi documenti.
**Logica codice**: `scansiona_tutte_cartelle(tipi, max_cartelle, max_email_per_cartella)`.
**Note**: parametri presi dal body come tipi semplici senza modello Pydantic; sincrono (rischio timeout su scansioni ampie).

### POST /api/email-scanner/associa — associazione documenti
**Cosa fa**: associa i documenti scaricati ai verbali/fatture esistenti.
**Logica codice**: `associa_documenti_a_verbali()`.

### GET /api/email-scanner/statistiche — statistiche scanner
**Cosa fa**: statistiche complete dei documenti scaricati dallo scanner.
**Logica codice**: `get_statistiche_documenti()`.

### POST /api/email-scanner/scansiona-e-associa — scansione + associazione
**Cosa fa**: endpoint principale: scansiona (default tipi verbale_noleggio, esattoriale, esattoriale_regionale, f24_tributi) e poi associa, in un'unica chiamata.
**Logica codice**: `scansiona_tutte_cartelle` + `associa_documenti_a_verbali` in sequenza; risposta riepilogativa.

---

## email_drive_sheets.py (/api/email-drive_sheets) — 4 endpoint

Variante "tutto su Google Drive/Sheets, niente filesystem" dello scarico email (servizio `email_to_drive_sheets`, collezione `email_documents`). Montato con prefix `/api` + prefix interno `/email-drive_sheets`.

### POST /api/email-drive_sheets/sync — scarica email su Drive/Sheets
**Cosa fa**: scarica le email con PDF degli ultimi `days_back` giorni e salva tutto in `email_documents`.
**Logica codice**: `download_and_save_emails(db, days_back, folder)`.
**Note**: riceve `BackgroundTasks` ma NON lo usa: esecuzione sincrona (rischio timeout su periodi lunghi, il parametro inganna).

### GET /api/email-drive_sheets/stats — statistiche
**Cosa fa**: statistiche sui documenti email in Drive/Sheets.
**Logica codice**: `get_email_documents_stats(db)`.

### GET /api/email-drive_sheets/documents — lista documenti
**Cosa fa**: lista `email_documents` con filtri category/processed, senza payload PDF.
**Logica codice**: find con projection `pdf_data:0`, sort created_at desc.

### GET /api/email-drive_sheets/pdf/{doc_id} — download PDF
**Cosa fa**: restituisce il PDF dal record Drive/Sheets.
**Logica codice**: find_one per id; `base64.b64decode(pdf_data)` + Response inline.
**Note**: decodifica base64 dell'intero file in RAM (no streaming) — stesso pattern del 502; da fixare a chunk. Il file duplica funzionalità di email_download (quarta pipeline di scarico email nel sistema: email_download, documenti, email_scanner, email_drive_sheets).

---

## import_manuale.py (/api/import-manuale) — 6 endpoint

Import manuale Excel/CSV con pandas: chiusure POS da registratore di cassa (collection dedicata `chiusure_pos_manuali`, esplicitamente distinta dagli accrediti bancari), versamenti e finanziamento soci in `prima_nota_banca`.

### POST /api/import-manuale/import-pos — chiusure POS Excel
**Cosa fa**: importa il file pos.xlsx (colonne DATA, IMPORTO) come chiusure giornaliere in `chiusure_pos_manuali` (NON prima_nota_banca).
**Logica codice**: pandas read_excel; conversione date Excel serial; skip importi ≤0; anti-duplicato (data, importo); insert con source_file/tipo.

### GET /api/import-manuale/chiusure-pos — lista chiusure
**Cosa fa**: lista le chiusure POS con filtri anno/data_da/data_a e totale.
**Logica codice**: find su `chiusure_pos_manuali` sort data desc (max 1000); somma in Python.
**Note**: se si passa sia `anno` che `data_da/data_a`, il filtro anno viene sovrascritto parzialmente da setdefault (comportamento sottile ma accettabile).

### DELETE /api/import-manuale/chiusure-pos/pulisci — svuota chiusure
**Cosa fa**: elimina TUTTE le chiusure POS manuali per reimportazione.
**Logica codice**: `delete_many({})`.

### POST /api/import-manuale/import-versamenti — versamenti CSV
**Cosa fa**: importa un CSV (sep ;) di versamenti in `prima_nota_banca` con rilevamento colonne per nome (data contabile, importo, descrizione, categoria, banca).
**Logica codice**: read_csv con tentativi di encoding; parse date DD/MM/YYYY; anti-duplicato (data, importo, regex sui primi 20 char della descrizione); insert con source `import_manuale_versamenti`.
**Note**: la descrizione è interpolata cruda in `$regex` per l'anti-duplicato: caratteri regex nella descrizione possono far fallire il check.

### POST /api/import-manuale/import-finanziamento-soci — finanziamento soci Excel
**Cosa fa**: importa un Excel entrate/uscite di finanziamento soci in `prima_nota_banca`.
**Logica codice**: read_excel, colonne per keyword (data/entrat/uscit/descr); scarta valori >40000 (interpretati come date Excel per errore); insert con source `import_manuale_fin_soci`.
**Note**: NESSUN controllo duplicati: reimportare lo stesso file raddoppia i movimenti (a differenza degli altri due import).

### GET /api/import-manuale/preview-import — statistiche import
**Cosa fa**: conteggia i movimenti in prima_nota_banca per ciascuna source di import manuale.
**Logica codice**: tre count_documents su source ∈ {import_manuale_pos, import_manuale_versamenti, import_manuale_fin_soci}.
**Note**: BUG: conta `import_manuale_pos` in `prima_nota_banca`, ma /import-pos salva in `chiusure_pos_manuali` senza campo `source` → quella statistica è sempre 0.

---

## import_templates.py (/api/import-templates) — 4 endpoint

Generazione template scaricabili (XLSX con openpyxl stilizzato, CSV) con le intestazioni ESATTE dei file reali della banca/registratore. Nessun accesso al DB, tutto in memoria via StreamingResponse.

### GET /api/import-templates/corrispettivi — template corrispettivi XLSX
**Cosa fa**: scarica template_corrispettivi.xlsx con le 9 intestazioni del tracciato RT (Id invio, Matricola, date, ammontare/imponibile/imposta, inattività) + riga esempio.
**Logica codice**: openpyxl workbook in BytesIO, header stilizzati, StreamingResponse con Content-Disposition.

### GET /api/import-templates/pos — template POS XLSX
**Cosa fa**: scarica template_pos.xlsx (DATA, CONTO, IMPORTO) con esempi.
**Logica codice**: come sopra.

### GET /api/import-templates/versamenti — template versamenti CSV
**Cosa fa**: scarica template_versamenti.csv (sep ;) con le 10 intestazioni Banco BPM e 2 righe esempio.
**Logica codice**: stringa CSV statica encodata utf-8-sig in BytesIO.

### GET /api/import-templates/estratto-conto — template estratto conto CSV
**Cosa fa**: scarica template_estratto_conto.csv, stesse intestazioni dei versamenti con esempi POS/bonifico.
**Logica codice**: come sopra.

---

## chat_router.py (/api/chat) — 2 endpoint

Chat "intelligente" senza LLM: interpretazione della domanda per parole chiave (`_INTENTI`), risposte calcolate SEMPRE da query dirette sul DB o da endpoint di analisi esistenti (bilancio, controllo gestione); cronologia persistente per utente/sessione in `chat_history`. Montato con prefix `/api` + prefix interno `/chat`.

### GET /api/chat/history — cronologia chat
**Cosa fa**: restituisce le ultime 20 voci di cronologia per l'utente autenticato (o session_id client, o "default").
**Logica codice**: `_session_id` (request.state.user_id da AuthenticationMiddleware → session_id → default); find su `chat_history` sort created_at desc, restituito in ordine cronologico.

### POST /api/chat/ask — domanda in linguaggio naturale
**Cosa fa**: risponde a domande su corrispettivi, fatture, F24, dipendenti, fornitori, bilancio, panoramica e trend/consigli flusso di cassa; salva ogni scambio in `chat_history`.
**Logica codice**: match keyword ordinato su `_INTENTI` → handler dedicato: fatture (invoices per anno), corrispettivi (totale/contanti/elettronico), F24 (carica f24_unificato e normalizza in Python i molteplici schemi con `_f24_anno`/`_f24_importo`), dipendenti/fornitori (count), bilancio (riusa `accounting.bilancio.get_riepilogo_bilancio`), strategia (riusa `controllo_gestione.get_trend_mensile`, confronto margini ultimi 3 mesi vs precedenti); fallback per domande non riconosciute; risposta con `response`+alias `risposta`.
**Note**: `_risposta_fatture` fa `to_list(200000)` e somma in Python; `_risposta_f24` carica TUTTI gli F24 (`to_list(50000)`) per filtrare l'anno in Python — necessario per gli schemi misti di f24_unificato (il commento nel codice documenta esplicitamente il problema degli schemi coesistenti), ma è un carico RAM evitabile con aggregation una volta sanata la collection.

---

## learning_machine.py (/api/learning-machine) — 7 endpoint

Classificatore email a 23 categorie basato su keyword pesate (CATEGORIE_BASE) con apprendimento da feedback utente: le correzioni aggiungono keywords a `learning_rules` che pesano di più nelle scansioni successive. Collezioni: `documenti_classificati`, `learning_feedback`, `learning_rules`. Fa IMAP direttamente nel router.

### GET /api/learning-machine/dashboard — dashboard
**Cosa fa**: totali documenti/PDF/processati/non classificati, feedback, regole apprese, distribuzione categorie, ultimi 10 documenti.
**Logica codice**: aggregate per categoria + count multipli su documenti_classificati/learning_feedback/learning_rules.

### GET /api/learning-machine/documenti — lista classificati
**Cosa fa**: lista documenti classificati con filtri categoria/has_pdf/processato, paginata.
**Logica codice**: find su `documenti_classificati` sort created_at desc + count.

### POST /api/learning-machine/feedback — correzione con apprendimento
**Cosa fa**: corregge la categoria di un documento; il sistema apprende: le keywords indicate (e fino a 3 parole >4 lettere estratte dal subject) vengono aggiunte alle regole della categoria corretta.
**Logica codice**: lookup per `_key` (fallback regex sul subject); insert in `learning_feedback`; update categoria sul documento; `$addToSet` keywords_extra/keywords_auto su `learning_rules` (upsert).
**Note**: l'estrazione automatica di keywords dal subject può inquinare le regole con parole generiche; il fallback di lookup usa i primi 30 caratteri del document_id come regex (fragile).

### POST /api/learning-machine/scan — scansione IMAP con classificazione
**Cosa fa**: scansiona le cartelle IMAP indicate (default INBOX, ultimi N giorni, limite per cartella), classifica ogni email con keyword base + apprese e salva i nuovi documenti (solo metadati + preview body + lista allegati, senza scaricare i PDF).
**Logica codice**: imaplib sincrono (login con env EMAIL_ADDRESS/EMAIL_PASSWORD); per email: decode subject, estrazione body text/plain (1000 char), `classify_document` (score keyword, bonus subject, peso 1.5 per keywords apprese, confidence = quota dello score), rilevazione allegati PDF; anti-duplicato su `_key` = folder+subject[:50]+date; insert in `documenti_classificati`.
**Note**: riceve `BackgroundTasks` ma NON lo usa: la scansione è sincrona dentro la richiesta (timeout probabile su molte cartelle) e blocca l'event loop (imaplib sincrono in handler async). La `_key` basata su subject troncato può collassare email diverse con stesso oggetto/data.

### GET /api/learning-machine/regole-apprese — regole
**Cosa fa**: mostra le regole apprese (keywords extra/auto per categoria).
**Logica codice**: find su `learning_rules` (max 100).

### GET /api/learning-machine/statistiche-feedback — stats feedback
**Cosa fa**: conteggio feedback per categoria corretta + ultimi 20 feedback.
**Logica codice**: aggregate + find su `learning_feedback`.

### DELETE /api/learning-machine/reset-learning — reset apprendimento
**Cosa fa**: elimina tutte le regole apprese e i feedback; rimuove feedback_utente dai documenti.
**Logica codice**: delete_many su learning_rules e learning_feedback; update_many `$unset` su documenti_classificati.
**Note**: docstring "solo per admin" ma NON c'è alcun controllo ruolo nel codice: chiunque può azzerare l'apprendimento.

---

## learning_universal.py (/api/learning-universal) — 5 endpoint

"Learning" statistico senza ML reale: analizza in batch fatture, fornitori, movimenti banca, corrispettivi e assegni per estrarre pattern (frequenze keyword, ritardi medi di pagamento, stagionalità); risultati salvati in `learning_results` (singolo documento `_id: "latest"`), da cui derivano suggerimenti applicabili.

### GET /api/learning-universal/status — stato apprendimento
**Cosa fa**: conteggi per 8 collezioni (invoices, fornitori, cedolini, f24_payments, corrispettivi, assegni, movimenti_banca, bonifici) e "learning_progress" (%).
**Logica codice**: count_documents multipli; progress = min(100, totale/1000*100).
**Note**: metrica di progresso arbitraria (1000 doc = 100%).

### POST /api/learning-universal/train/all — training completo
**Cosa fa**: esegue i 5 moduli di analisi: pattern fornitori (metodi pagamento, keyword ragione sociale), pattern pagamenti (ritardo medio per fornitore da fatture pagate), categorizzazione movimenti (keyword→categoria da movimenti già categorizzati), stagionalità corrispettivi (medie mensili, picchi), associazioni assegni (tasso associazione, pattern beneficiari); salva tutto in `learning_results._id=latest`.
**Logica codice**: 5 funzioni interne con `to_list(1000..5000)` e conteggi in Python (defaultdict); sanitizzazione chiavi None/tuple per JSON; upsert del risultato.
**Note**: sincrono (nessun background) su decine di migliaia di documenti in RAM; usa `datetime.utcnow()` (naive, deprecato) a differenza del resto del blocco.

### GET /api/learning-universal/results — ultimi risultati
**Cosa fa**: restituisce il documento `learning_results` "latest" (o no_results).
**Logica codice**: find_one, pop di _id.

### GET /api/learning-universal/suggestions/{module} — suggerimenti
**Cosa fa**: deriva suggerimenti dai risultati per modulo: fatture (giorni medi pagamento per fornitore), movimenti (regole keyword→categoria), corrispettivi (mesi picco/deboli), assegni (pattern beneficiario).
**Logica codice**: legge `learning_results.latest` e formatta le prime 10 voci del modulo.

### POST /api/learning-universal/apply-suggestions — applica regole
**Cosa fa**: applica le regole di categorizzazione ai movimenti bancari non categorizzati (regex sulle keyword apprese).
**Logica codice**: per ogni regola/keyword: `update_many` su `movimenti_banca` senza categoria con `$set categoria + auto_categorized`.
**Note**: il parametro `suggestion_ids` è accettato ma IGNORATO: applica sempre TUTTE le regole del modulo movimenti (nessuna selezione possibile); gli altri moduli non sono implementati in apply.

---

## learning_machine_cdc.py (/api/learning-cdc) — 5 endpoint

Riclassificazione automatica dei costi per centro di costo (servizio `learning_machine_cdc`): classifica fatture per CDC con deducibilità IRES/IRAP e detraibilità IVA, processa quietanze F24 con mappatura tributi→CDC e riconciliazione bancaria, calcola il costo del personale (B9). Montato con prefix `/api` + prefix interno `/learning-cdc`.

### GET /api/learning-cdc/centri-costo — elenco CDC
**Cosa fa**: restituisce tutti i centri di costo configurati.
**Logica codice**: `get_tutti_centri_costo()` (configurazione nel servizio, non su DB).

### POST /api/learning-cdc/riclassifica-fatture — riclassificazione fatture
**Cosa fa**: riclassifica tutte le fatture dell'anno (o solo quelle senza CDC se forza=false): assegna centro di costo, categoria bilancio, percentuali e importi deducibili/detraibili.
**Logica codice**: find `invoices` per anno (regex su invoice_date/data_ricezione, max 5000); per fattura: `classifica_fattura_per_centro_costo(supplier, descrizione, linee)` + `calcola_importi_fiscali(imponibile, iva, cdc)`; update_one per `_id` con ~15 campi; report per CDC.
**Note**: sincrono su 5000 fatture con un update ciascuna: lento; nessun uso di bulk_write.

### POST /api/learning-cdc/processa-quietanza-f24 — quietanza F24 → CDC + banca
**Cosa fa**: registra i tributi di una quietanza F24 in `f24_quietanze` (ciascuno con CDC da `classifica_f24_per_tributo`) e prova a riconciliare il movimento bancario corrispondente in `prima_nota_banca` (stessa data, importo negativo, descrizione/causale F24-like).
**Logica codice**: loop tributi → insert `f24_quietanze`; find_one su prima_nota_banca con regex f24|delega|agenzia entrate; se trovato marca `riconciliato:true`.
**Note**: input come query/body ibrido (lista tributi nel body, resto come parametri); nessun anti-duplicato: ripostare la stessa quietanza duplica i tributi. Le due condizioni `$or` sull'importo sono identiche (`-importo_totale` e `importo_totale * -1`) — ridondanza inutile.

### GET /api/learning-cdc/costo-personale-completo/{anno} — costo personale B9
**Cosa fa**: quadro completo del costo del personale per anno da 3 fonti: cedolini (lordo/oneri/TFR), quietanze F24 tributi personale (1001,1002,1012,DM10), bonifici stipendi; con riconciliazione netto vs pagato (soglia 100€).
**Logica codice**: tre aggregate ($group) su `cedolini`, `f24_quietanze`, `bonifici_stipendi`; se mancano oneri li STIMA (INPS azienda = 30% lordo, TFR = 6.91% lordo).
**Note**: le stime sostitutive non sono flaggate nella risposta come tali se applicate (il campo vale la stima come se fosse un dato reale).

### GET /api/learning-cdc/riepilogo-centri-costo/{anno} — riepilogo CDC
**Cosa fa**: aggrega le fatture classificate per centro di costo: imponibile, IVA, deducibile/indeducibile IRES, IVA detraibile/indetraibile, con totali generali.
**Logica codice**: aggregate su `invoices` (match centro_costo_id + anno, $group per CDC con $ifNull sui campi calcolati), somme finali in Python.

---

## Anomalie trasversali (riepilogo)

1. **Base64 interi in RAM (pattern del 502)**: oltre al punto già fixato in `documenti.py /documento/{id}/download` (streaming a chunk), decodificano ancora l'intero file in un colpo solo: `email_download GET /pdf/{collection}/{pdf_id}`, `email_drive_sheets GET /pdf/{doc_id}`, `documenti_non_associati GET /pdf/{documento_id}`. Inoltre `documenti.py POST /riepilogo-cedolini` carica fino a 5000 documenti COMPLETI di pdf_data in una lista (`to_list(5000)`) e `chat_router` fa `to_list(200000)`/`to_list(50000)` su invoices/f24_unificato.
2. **Fatture email fuori dal percorso unificato**: `email_download /processa-fatture-email` (+ variante /batch) inserisce direttamente in `invoices` via `ai_document_parser`, bypassando `fatture_upload.process_xml_bytes`; idem `ai_parser /parse` e `/parse-fattura` (senza anti-duplicato). Solo `documenti /upload-auto` usa il percorso unificato.
3. **F24 frammentati su 5 collezioni con schemi misti**: f24_unificato (con DUE schemi diversi inseriti da `documenti /sync-f24-automatico`), f24_commercialista, f24_tributi, f24_parsed, f24_quietanze. Il problema è documentato nel codice stesso (`chat_router._f24_anno`).
4. **Docstring che mentono**: `documenti /processa-f24-scaricati` (controlla un wrapper `{success, f24_data}` che il parser non restituisce → probabilmente non importa mai nulla); `documenti /reimporta-da-filesystem` (dice /app/documents, usa /tmp/documents); `documenti /documento/{id}/processa` (non carica nella destinazione, marca solo lo stato); `ai_parser /da-rivedere/process-batch` (dice "riprocessa con AI", cambia solo uno status); `ai_parser /batch-parse` e `learning_universal /apply-suggestions` (parametri save_to_db / suggestion_ids ignorati); `document_ai /extract` (dice default gpt-4o, è claude-sonnet-4-5); `email_drive_sheets /sync` e `learning_machine /scan` (ricevono BackgroundTasks ma eseguono sincroni).
5. **Duplicazione di pdf_data**: il base64 viene ricopiato nei record derivati (invoices da email, cedolini da sync-buste-paga, riepilogo_cedolini, record target di documenti-non-associati/associa, extracted_documents con file_base64): stesso file salvato N volte nel DB.
6. **Stato in memoria di processo**: download_status, _batch_processing_status (email_download), _download_tasks e _email_operation_lock (documenti): persi al riavvio e non condivisi tra worker.
7. **Bug puntuali**: `import_manuale /preview-import` conta una source mai scritta (stat POS sempre 0); `import-finanziamento-soci` senza anti-duplicato; `documenti /ultimo-sync` e `/statistiche` usano find_one senza sort ("ultimo" non garantito); `documents_inbox_classify /auto-classify` legge il testo PDF solo se pdf_data è bytes ma il dato è base64 string (estrazione contenuto di fatto disattivata) e usa il campo `categoria` mentre il resto usa `category`; `documenti_non_associati /associa` permette di scrivere in collezioni arbitrarie (whitelist non applicata); `learning_machine /reset-learning` "solo admin" senza alcun controllo; `document_ai DELETE` restituisce 500 invece di 404.
8. **Pipeline email quadruplicata**: email_download (EmailFullDownloader), documenti (email_document_downloader + monitor), email_scanner (email_scanner_completo), email_drive_sheets (email_to_drive_sheets), più learning_machine che fa IMAP in proprio: cinque vie diverse per scaricare/classificare la stessa posta, con collezioni destinazione diverse (documents_inbox, email_documents, documenti_classificati, documenti_non_associati, fatture_email_attachments).
