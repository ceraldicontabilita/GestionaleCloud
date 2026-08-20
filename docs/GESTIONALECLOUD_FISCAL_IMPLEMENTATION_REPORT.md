# Rapporto implementazione fiscale AdeR

<!-- gestionalecloud-doc
status: historical
reviewed_at: 2026-08-20
storage_architecture: drive-only
-->

> [!NOTE]
> Snapshot storico: non descrive lo stato operativo corrente. Per l'architettura Drive-only usare `README.md`, `PRODUCT.md`, `CLAUDE.md` e `LOGICA_FUNZIONAMENTO.md`.

Data verifica: 2026-08-10
Ambito: baseline documentale AdeR del pacchetto MASTER, senza scritture su database o Drive di produzione.

## Risultato

E' stato aggiunto al dominio fiscale esistente un importatore AdeR idempotente e fail-closed. Il flusso operativo accetta esclusivamente l'ID di un archivio ZIP gia' registrato in `Documenti`, verifica SHA-256 e struttura, offre un dry-run e richiede MFA per l'applicazione.

La baseline verificata contiene:

- 47 PDF complessivi;
- 43 analitiche di posizione;
- 2 accoglimenti di rateizzazione;
- 1 modulo di pagamento rateale;
- 1 comunicazione di definizione agevolata.

Esiti gestionali calcolati sulle 43 analitiche:

- 36 `PORTAL_CLOSED_PENDING_EVIDENCE`;
- 3 `MICRO_RESIDUAL_REVIEW`;
- 2 `PAYABLE`;
- 1 `SUSPENDED_NO_CURRENT_PAYMENT`;
- 1 `PARTIALLY_PAID_SUSPENDED`.

## Regole contabili applicate

- `portal_status` e `portal_bucket` non determinano lo stato contabile.
- Una comunicazione, un piano rateale o un modulo di pagamento non costituiscono prova del pagamento.
- Gli importi mancanti nei PDF storici restano `null`, non vengono trasformati in zero.
- I residui minimi restano memorizzati; la soglia configurabile cambia soltanto la coda di revisione.
- Una posizione interamente sospesa ha esigibile corrente zero, ma non diventa pagata.
- I riferimenti abbreviati dei piani vengono risolti solo se corrispondono a una sola analitica completa.
- Ogni snapshot, piano e definizione mantiene il collegamento bidirezionale al PDF sorgente mediante il registro prove esistente.

## Componenti implementati

- collezioni `ader_position_snapshots` e `ader_archive_imports` con indici azienda/snapshot/documento;
- parser versionato per i due layout AdeR osservati;
- parser di piani rateali, modulo rate e definizione agevolata;
- endpoint lettura, dry-run e import protetto da MFA;
- pagina `Snapshot AdeR` con posizioni, importi, piani, rate e definizioni;
- apertura della prova PDF sorgente dalla pagina fiscale;
- test unitari per residui, sospensioni, riferimenti rateali, definizioni senza prova e ZIP non sicuri.

## Operazioni non eseguite

Non sono stati modificati dati contabili, documenti aziendali, MongoDB Atlas o Google Drive. Il pacchetto locale e' stato usato soltanto come fixture di verifica. L'import reale resta subordinato alla registrazione dell'archivio in `Documenti`, al dry-run amministrativo e alla conferma esplicita.

## Verifiche automatiche

- backend completo: `1707 passed`, `2 skipped`;
- frontend: `28` file di test, `161` test superati;
- build frontend di produzione: completata;
- controllo whitespace/diff: superato;
- correzione pre-pubblicazione verificata: l'identificativo AdeR spezzato nel PDF (`AR071 - 812706`) viene ricomposto in `AR071812706`; le rate 13-18 restano elementi distinti del modulo.

## Lavoro residuo

- import reale controllato e confronto dei conteggi nel database;
- confronto snapshot N/N+1;
- validazione live dei permessi di apertura PDF;
- collaudo autenticato desktop/mobile;
- validazione delle eccezioni con il consulente fiscale.
