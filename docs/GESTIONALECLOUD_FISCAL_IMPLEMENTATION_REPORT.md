# GestionaleCloud — report implementazione fiscale e Drive

Data: 2026-08-10

Branch di lavoro: `codex/master-implementation-fiscale-drive`
Base verificata prima delle modifiche: `9b674934d06a7312eb0036d528c46e534d2135e2`

## Esito

E' stato completato e verificato il primo strato verticale utilizzabile delle
aree classificate `PARZIALE`, `ASSENTE` o `DIVERGENTE`: modello company-scoped,
pipeline documentale unica, regole evidence-bound, API, Drive incrementale,
viewer e UI di consultazione. Non sono stati copiati file dagli snapshot
storici e nessun PDF fiscale reale e' stato aggiunto a Git.

La Definition of Done estesa del master prompt non e' dichiarata integralmente
raggiunta: mancano ancora i parser specialistici completi per ogni tipologia,
il popolamento verificato di tutti i registri, il collaudo autenticato su dati
reali e le prove end-to-end Import/Drive -> riconciliazione -> dossier. Il codice
non inventa tali risultati e lascia gli oggetti senza prova in `TO_VERIFY`.

Restano due blocchi esterni, esplicitamente non trasformati in dati fittizi:

1. l'archivio AdeR da 43 posizioni citato nei requisiti non e' presente nel
   pacchetto trasferito, quindi le 43 posizioni non sono state inserite nel DB;
2. questa sessione non dispone di una sessione amministrativa/MFA e delle
   credenziali Drive operative, quindi non ha potuto confermare dal vivo gli ID
   delle sottocartelle ne' eseguire la sincronizzazione sul database reale.

## Componenti implementati

- `FiscalDocumentIngestionService`: unico ingresso fiscale da Documenti e Drive,
  SHA-256, versioni, pagine, classificazione deterministica, prova con pagina e
  conservazione del payload soltanto nell'archivio Documenti.
- Drive fiscale: scoperta fail-closed dalla root configurata, scansione ricorsiva,
  Changes API incrementale, marcatura delle rimozioni alla fonte senza cancellare
  lo storico e uso persistente degli ID Drive verificati.
- Modello dati company-scoped: documenti/versioni/pagine/evidence/link, obblighi,
  pagamenti, allocazioni, cartelle/righe/eventi/snapshot, rateazioni, definizioni,
  crediti e lineage, crosswalk e regole legali versionate.
- Semantica di pagamento: residuo zero, F24 predisposto e PDF bonifico non sono
  prova sufficiente; quietanza e identita' forte restano separate dallo stato
  sostanziale e procedurale della pretesa.
- Riscossione: snapshot idempotente e vincolato a un documento sorgente,
  timeline append-only, cause di chiusura, matching AdeR prudenziale, sospensione,
  sgravio, rateazione e definizione come dimensioni distinte.
- F24/IVA: righe di regolamento senza duplicazione del costo; distinzione 6012,
  6013 e 6099; catena credito IVA con rilevazione di lineage interrotta, doppio
  utilizzo e compensazione incoerente.
- Ravvedimento: nessun calcolo definitivo senza una regola legale versionata e
  la relativa fonte; in assenza della regola il risultato e' `NOT_DETERMINABLE`.
- Controllo e consulente: controlli deterministici, advisor brief, dossier PDF e
  pacchetto ZIP con originali invariati, hash e bozza non inviata.
- Sicurezza: perimetro aziendale su query e indici; letture autenticate; import,
  eventi, sincronizzazioni, ricostruzioni e pacchetti prova protetti da admin+MFA.
- UI: una pagina amministrativa `Situazione fiscale` con Tributi, pagati, codici,
  crosswalk e riscossione; `LinkedEvidencePanel`, deep-link di pagina nel viewer e
  comando Drive fiscale dentro il punto di ingresso esistente `Documenti`.

## File e migrazioni

- Configurazione/schema: `app/config.py`, `app/db_collections.py`,
  `app/database.py`.
- Ingestion e Drive: `app/services/fiscal_document_ingestion.py`,
  `app/services/fiscal_evidence.py`, `app/services/drive_fiscal_registry.py`,
  `app/services/drive_documenti_ingest.py`, `app/routers/documenti.py`,
  `app/routers/documenti_fiscali.py`.
- Dominio e controlli: `app/services/fiscal_domain.py`,
  `app/services/tax_collection_service.py`,
  `app/services/tax_obligation_service.py`,
  `app/services/ravvedimento_engine.py`, `app/services/fiscal_agents.py`.
- API: `app/routers/fiscal_control.py`, `app/router_registry.py`.
- UI: `frontend/src/pages/SituazioneFiscale.jsx`,
  `frontend/src/components/LinkedEvidencePanel.jsx`,
  `frontend/src/components/DocumentViewerModal.jsx`, navigazione e pagina
  `Documenti`.
- Test: `tests/test_fiscal_domain.py`,
  `tests/test_fiscal_evidence_bound_rules.py`, route e test Documenti aggiornati.

Non e' stata eseguita una migrazione automatica in produzione. Gli indici
idempotenti sono stati aggiunti al provisioning esplicito
`Database._create_indexes`; restano disattivati allo startup salvo
`RUN_STARTUP_INDEX_MIGRATIONS=True`.

## Importazione dati

Nessun Excel o ZIP e' stato assunto come gia' importato. Gli archivi sono stati
usati soltanto per inventario e confronto. La pipeline rifiuta un import AdeR
definitivo se il documento sorgente non e' prima registrato e verificato.

La prossima esecuzione operativa, con credenziali e MFA, deve:

1. verificare la root Drive `1f48bounfoOyHL_kqpHAp2GAnFfEpHvVa`;
2. registrare gli ID reali univoci di `Avvisi bonari` e `Cartelle esattoriali`;
3. eseguire prima il dry-run e poi la sincronizzazione;
4. confrontare conteggi e hash col DB reale;
5. importare il prospetto AdeR soltanto dopo aver ricevuto l'archivio mancante;
6. validare i casi reali con documenti privati fuori da Git.

## Verifiche eseguite

- test fiscali mirati: superati;
- suite backend completa: `1695 passed, 2 skipped`;
- suite frontend completa: `159 passed` in 27 file;
- build Vite di produzione: completata;
- preview HTTP: `/` e `/situazione-fiscale/riscossione` rispondono `200` con fallback SPA;
- mappe route e classificazione endpoint: rigenerate, `1108 endpoint`;
- `git diff --check`: senza errori;
- artifact di build: rimossi dal worktree dopo la verifica.

## Stato finale

Il primo strato e' pronto per revisione e collaudo operativo read-only. La
conferma degli ID Drive, l'importazione reale delle 43 posizioni, il collaudo
E2E autenticato, i parser specialistici completi e qualsiasi deploy non sono
dichiarati completati: richiedono le fonti, le autorizzazioni e ulteriori gate
di implementazione/verifica.
