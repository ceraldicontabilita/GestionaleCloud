# MiniHR: integrazione parallela, fase 1

La nuova voce HR `Fascicolo mensile · MiniHR` è una vista GET-only, solo admin.
Non sostituisce Anagrafica, Archivio paghe, Posizione dipendente o TFR.
Il Site privato resta operativo e non viene incorporato nel repository pubblico.

## Fonti e limiti

- Il nucleo generico `frontend_shared/minihr` è identico a `shared/minihr` del Site (manifest SHA256).
- L'adattatore ERP legge il motore Posizione dipendente esistente. Non importa i saldi, le esclusioni o le associazioni del Site.
- Ordinari, 13ª, 14ª e documenti finali restano distinti. Bonus e TFR autonomi mantengono il trattamento del motore esistente.
- I mesi senza date sufficienti non vengono dichiarati automaticamente in forza. Le date finali legacy restano da confermare: non sono convertite ciecamente in decorrenza dimissioni.
- PDF privati aperti via endpoint autenticati; nessuna credenziale viene trasmessa a Drive. I documenti senza competenza non usano la data di caricamento come mese paga.
- F24 dal registro fiscale principale, filtrati per codice fiscale aziendale esplicito. Nessuna copia HR e nessuna attribuzione al singolo dipendente. Quietanza, addebito e semplice modello sono evidenze distinte. Nessun costruttore di fascicoli con effetti di scrittura viene chiamato.

## Aggiornamenti futuri: procedura abbinata

1. Aggiornare il nucleo comune nel Site. Per cambiamenti specifici aggiornare anche l'adattatore ERP, oppure dichiarare la funzione ancora da trasferire.
2. Dal progetto Site: `python scripts/sync_minihr_to_gestionale.py /path/to/GestionaleCloud`, poi lo stesso con `--check`.
3. Eseguire `node --test frontend_shared/minihr/core.test.mjs`, test Python e build HR; verificare le regressioni contabili del Site.
4. Rilasciare il Site e aprire PR ERP abbinata. Il Site non si spegne durante revisione o rollback del gestionale. Non promettere aggiornamenti automatici in produzione.

Non copiare mai nel repository pubblico JSON paghe, PDF, codici fiscali reali, snapshot Site, esportazioni Supabase o credenziali.

## Checkpoint successivi, non eseguiti da questa fase

- Confronto autorizzato tra gli archivi reali, riga per riga, con identità, competenza, tipo e ID (mai solo importo).
- Migrazione controllata di esclusioni e associazioni con ID stabili, backup, conteggi prima/dopo e approvazione.
- Importazione documentale e scritture operative soltanto dopo tale verifica.
- Validazione visuale autenticata e approvazione della PR prima dell'attivazione nell'ERP.

Nessuna migrazione DB, modifica Auth, fusione di archivi o attivazione in produzione è inclusa nella fase 1.

## Aggiornamento v46 — scheda unificata

La proposta parallela offre una sola scheda dipendente con Cedolini/documenti, Pagamenti, Partitario mensile e Apertura 2023. Filtri di periodo e somme in centesimi passano dallo stesso core; il widget mensile non ripete i filtri esterni. Il link al minisito porta alla scheda canonica MiniHR_v37. Anche il miglioramento visivo v45 è incluso nel componente condiviso.

Rimane tutto in sola lettura nel Gestionale. Le conferme/esclusioni del minisito, le nuove quietanze, i link privati a ricevute Drive e gli Elenchi netti NON sono stati importati. Funzioni di scrittura/riconciliazione e migrazione dei dati restano pendenti per un checkpoint separato con revisione dei permessi. Nessuna attivazione/migrazione/merge di produzione. Il repository pubblico contiene soltanto codice generico e nessun PDF, codice fiscale reale o snapshot privato del minisito.
