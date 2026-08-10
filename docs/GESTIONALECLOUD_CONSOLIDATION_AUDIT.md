# GestionaleCloud - audit di consolidamento

Data audit: 2026-08-10

Repository autorevole: `ceraldicontabilita/GestionaleCloud`

Branch audit: `codex/master-implementation-fiscale-drive`
Commit verificato: `9b674934d06a7312eb0036d528c46e534d2135e2`

## Metodo e confini

- Il clone locale era pulito e allineato a `origin/main`; il connettore GitHub e la produzione hanno confermato lo stesso commit (`deploy_commit=9b674934`).
- I 15 ZIP del pacchetto sono stati inventariati senza sovrascrivere il repository. I tre snapshot codice richiesti contengono rispettivamente 1.427, 1.409 e 1.387 voci.
- I due archivi fiscali contengono entrambi 436 PDF. Condividono 446 hash complessivi; il V2 aggiunge 4 hash e l'archivio precedente ne conserva 7 non presenti nel V2.
- I sette Excel sono stati letti per fogli, righe, formule e riferimenti documentali. La loro esistenza non e' stata trattata come import DB.
- I 25 PDF diretti sono stati verificati per SHA-256, numero pagine, estraibilita' del testo e campione visuale. Sono fixture private e non vanno committati.
- La produzione corrente risponde `200` su `/api/health` con DB connesso. Gli endpoint fiscali amministrativi rispondono `401` senza sessione: la presenza della rotta e' verificata, il contenuto corrente del DB no.
- L'ultima evidenza DB leggibile e' una verifica privata del 2026-08-05: 2.464 `documents_inbox`, 48 `f24_unificato`, 130 `quietanze_f24`. E' indicata come storica, non come dato corrente.
- La precedente inventory Drive del 2026-08-04 conteneva 13.702 file/10.326 PDF. Tutti i 25 PDF diretti coincidono per SHA-256 con `CARTELLE ESATTORIALI`; nessuno dei 436 PDF del nuovo archivio fiscale coincideva allora con Drive.
- Nessun dato reale e nessun documento e' stato scritto, spostato, cancellato o importato durante l'audit.

## Legenda

- `PRESENTE`: codice, registrazione e test coerenti disponibili.
- `PARZIALE`: esiste una base utilizzabile ma manca almeno un gate richiesto.
- `ASSENTE`: nessuna implementazione equivalente nel runtime corrente.
- `DIVERGENTE`: esiste ma la semantica non coincide con il requisito o con la prova.
- `SUPERATO_DA_VERSIONE_PIU_RECENTE`: proposta ZIP non va copiata perche' il main ha una soluzione piu' recente/robusta.

## Matrice di consolidamento

| FUNZIONE | STATO | FILE/TABELLA | TEST | DATI REALI | AZIONE NECESSARIA |
|---|---|---|---|---|---|
| Repository/source of truth | PRESENTE | Git `main`, `app/`, `frontend/src/`, `tests/` | fetch e confronto SHA | produzione sullo stesso commit | Continuare solo sul branch audit/implementazione. |
| `operational_learning_engine` | PRESENTE | `app/services/operational_learning_engine.py` | `tests/test_operational_learning_engine.py` (nel gruppo audit 29/29) | conteggi live collezioni non leggibili oggi | Conservare i confini fail-closed. |
| Assistente Ceraldi UI | PRESENTE | `frontend/src/pages/AssistenteCeraldi.jsx`, rotta `/assistente` | catalogo e test motore | collaudo UI live non eseguito | Collaudo autenticato desktop/mobile. |
| Router API Assistente | PRESENTE | `app/routers/assistente_operativo.py`, `app/router_registry.py` | test motore/router | API live protetta; contenuti non letti | Conservare admin + MFA sulle azioni. |
| Facts/patterns/events/anomalies/questions/cases/sources | PRESENTE | `operational_facts`, `learned_patterns`, `expected_events`, `administrative_anomalies`, `decision_questions`, `case_memory`, `knowledge_sources` | test idempotenza e casi avversariali | conteggi live non verificati | Aggiungere solo eventuali dimensioni fiscali mancanti, senza scrivere nei domini contabili. |
| Learning engine storico degli ZIP | SUPERATO_DA_VERSIONE_PIU_RECENTE | ZIP v3/UNICO vs servizio corrente | test corrente piu' recente | n/d | Non copiare i moduli ZIP. |
| Banca, estratti conto e prova bancaria | PRESENTE | `app/routers/bank/`, `payment_document_links.py`, `f24_bank_reconciliation.py` | suite banca/F24 e relazioni | produzione con DB connesso; contenuto non letto | Nessuna regressione: movimento bancario resta prova distinta. |
| Nexi carta | PRESENTE | `app/services/nexi_carta.py`, parser e router | `test_nexi_carta.py`, parser, esclusione riconciliazione | non letto oggi | Conservare dedup e distinzione carta/conto. |
| POS/Numia/SumUp | PRESENTE | servizi POS/corrispettivi/SumUp | suite POS; commit recente deduplica prima dei totali | non letto oggi | Nessuna importazione automatica dai file allegati. |
| `association_orchestrator` ZIP | SUPERATO_DA_VERSIONE_PIU_RECENTE | ZIP: `association_orchestrator.py`; main: `entity_relations.py`, writer di dominio | 29 test mirati superati | copertura live relazioni non letta | Non copiare l'orchestratore semplificato. |
| Relazioni contabili bidirezionali core | PRESENTE | `entity_relations`, `accounting_relation_writers.py` | entity relations/audit/F24 bank | collezione live non letta | Estendere ai nuovi oggetti fiscali mantenendo `relation_key` idempotente. |
| Sincronizzazione relazionale completa/UI unica | PARZIALE | `entity_relations_audit.py`; manca il `CentroAssociazioni` dello ZIP | test backend presenti | coda live non verificata | Collegare nuovi domini e fornire navigazione unica senza duplicare `Documenti`. |
| F24 unificato | PRESENTE | `f24_unificato`, router `app/routers/f24/`, `f24_canonico.py` | numerosi test F24 | 48 record al 05/08; corrente non letto | Importare il dataset solo con dry-run/hash e riconciliazione. |
| Quietanze F24 | PARZIALE | `quietanze_f24`, `quietanze_import.py` | test import/scadenze/relazioni | 130 record al 05/08 contro 320 PDF nel nuovo archivio | Job idempotente, manifest, conteggi e collegamenti reali. |
| Catena F24 -> quietanza -> banca | PARZIALE | `f24_payment_evidence.py`, `f24_bank_reconciliation.py`, `entity_relations` | test presenti | completezza live non leggibile | Misurare copertura, ambigui pendenti, collegamenti inversi. |
| IVA mensile | PRESENTE | `/iva`, motori IVA, `iva_f24_verifica.py` | suite IVA/liquidazioni | ultimo audit storico: 7 liquidazioni | Mantenere classificazione detraibilita' fail-closed. |
| IVA dicembre / codice 6012 | PARZIALE | `codice_iva_mensile(12)` produce 6012 | test mensili; manca il test ciclo ZIP | corrente non letto | Integrare esplicitamente ciclo dicembre e confronto consulente/interno. |
| Acconto IVA 6013 | PARZIALE | codice noto in mapping, non nel verificatore mensile | nessun test equivalente allo ZIP nel main | corrente non letto | Rappresentare obbligo separato da 6012 e pagamento. |
| Saldo annuale IVA 6099 | PARZIALE | mapping/config e test saldo F24 | manca bridge annuale completo | corrente non letto | Collegare dichiarazione annuale, credito/riporto, F24 e banca. |
| Crediti annuali e riporto IVA | PARZIALE | motori IVA + dati Excel | test credito fail-closed | Excel presenti; import DB non provato | Registro versionato/lineage e confronto consulente vs interno. |
| F24 consulente fiscale/lavoro | PARZIALE | F24 canonico registra fonte; ZIP propone bridge | test F24 esistenti | import massivo nuovo non provato | Distinguere fonte consulente e riconciliare i debiti senza duplicare costi. |
| Chiusura debiti senza duplicare costi | PARZIALE | regole contabili e test bilancio esistenti | test anti-doppio conteggio generali | non validato sul dataset allegato | Integrare il bridge F24-bilancio dello ZIP con i servizi correnti. |
| PagoPA | PRESENTE | `app/routers/pagopa.py`, scanner, pagina | `test_pagopa_strict_match.py` | non letto oggi | Estendere alle nuove cartelle senza inferire pagamento dal solo documento. |
| Prima Nota | PRESENTE | `app/routers/prima_nota_module/`, pagina unica | ampia suite | produzione attiva, contenuto non letto | Conservare Banca solo con movimento reale e anno globale. |
| Bilancio | PRESENTE | `app/routers/accounting/bilancio.py`, UI | test bilancio/anti-doppio conteggio | non letto oggi | Integrare nuovi eventi fiscali come estinzione debiti, non costi duplicati. |
| Document viewer generico | PRESENTE | `DocumentViewerModal.jsx`, download Mongo protetto globalmente | workflow viewer e test dedicati | PDF disponibili in Mongo solo se importati | Non duplicare il viewer. |
| Apertura PDF alla pagina esatta | PARZIALE | pagine sorgente solo in domini specifici (es. cedolini) | nessun test trasversale fiscale | 25 PDF locali leggibili; uno richiede OCR | Aggiungere `document_id`, pagina/e e anchor a ogni evidence link. |
| Navigazione inversa PDF -> oggetti | PARZIALE | `entity_relations` esiste, viewer non espone pannello completo | test backend, non E2E fiscale | non verificata live | Implementare `LinkedEvidencePanel` equivalente riusando le relazioni correnti. |
| Dataset dichiarazioni 2020-2026 | PARZIALE | 61 indici dichiarazioni; 436 PDF totali nei pacchetti | hash/manifest verificati | zero hash del nuovo archivio nel Drive del 04/08; DB corrente non letto | Import controllato e idempotente; nessuna conclusione da Excel. |
| Dataset 302 operazioni/320 PDF F24 | PARZIALE | manifest e indice unificato | coerenza file/hash verificata | DB storico 48 F24/130 quietanze | Dry-run e report differenze prima di ogni scrittura reale. |
| Excel fiscali allegati | PRESENTE | 7 file, 2-13 fogli ciascuno | struttura/righe/formule lette | non provano DB | Trattarli come staging e confronto, non fonte di pagamento. |
| Avvisi bonari - modello dominio | ASSENTE | nessuna `tax_collection_*` equivalente completa | nessun test | Drive storico root separato con 0 PDF | Implementare schema/import/parser/evidence. |
| Cartelle esattoriali - modello dominio | ASSENTE | solo PDF/document inbox e servizi generici | nessun test di claim/eventi | 25/25 fixture gia' su Drive storico; DB dominio non provato | Implementare dominio strutturato senza dedurre stato dal nome. |
| `tax_collection_documents/claims/claim_lines/events` | ASSENTE | collezioni non presenti | assenti | non verificati | Implementare. |
| `tax_notification_events` / `tax_legal_events` | ASSENTE | non presenti | assenti | non verificati | Implementare. |
| Piani rateali, rate e allocazioni | ASSENTE | `tax_rate_*` non presenti | assenti | alcuni PDF/RAV locali esistono | Implementare con ID cartella normalizzato e prove. |
| Definizioni/rottamazioni | ASSENTE | `tax_settlement_*` non presenti | assenti | PDF locali parziali; archivio AdeR completo non allegato | Implementare, senza chiudere l'importo originario pieno. |
| Crediti fiscali/lineage | ASSENTE | `tax_credit_ledger`, movements, lineage assenti | assenti | Excel contiene crediti, DB non provato | Implementare separando origine, utilizzo, residuo e prova. |
| Registro codici tributo AdE | PRESENTE | `tax_code_registry`, versioni e sync ufficiale | test parser/sync | endpoint live protetto; stato non letto | Correggere CI mappe e verificare una sincronizzazione reale. |
| `collection_tax_code_registry` / crosswalk | ASSENTE | non presenti | assenti | n/d | Implementare registro riscossione e crosswalk versionati. |
| `legal_rule_versions` | ASSENTE | non presente | assenti | n/d | Implementare regole con validita' temporale e fonte ufficiale. |
| `RavvedimentoEngine` completo | ASSENTE | esistono controlli IVA/ravvedimento, non il motore richiesto | test parziali | Excel contiene analisi preparate | Implementare come proposta verificabile, non consulenza automatica definitiva. |
| `FiscalControlAgent` / `AdvisorBriefGenerator` | ASSENTE | non presenti | assenti | n/d | Implementare sopra evidenze, senza scritture contabili automatiche. |
| Dossier/evidence package fiscale | ASSENTE | `buildTaxReviewDossier`, `buildTaxEvidencePackage` assenti | assenti | n/d | Implementare export tracciato e protetto. |
| Root Drive fiscale configurata per ID | PARZIALE | `DRIVE_FISCAL_ROOT_FOLDER_ID` corretto nel config | test discovery | API reale non verificabile senza sessione/credenziali | Eseguire discovery live e persistere gli ID reali. |
| Discovery `Avvisi bonari` / `Cartelle esattoriali` | PARZIALE | `drive_fiscal_registry.py`, ricerca ricorsiva fail-closed | test unicita' superati | storico: erano root separate; situazione 10/08 non letta | Verifica Drive API corrente obbligatoria. |
| Drive Changes API | PARZIALE | page token e change log presenti | test unitari parziali | nessuna esecuzione live letta | Testare rename/move/delete/versione e retry; evitare full scan non necessarie. |
| Dedup Drive SHA-256 | DIVERGENTE | salva SHA-256 ma deduplica primaria su MD5 `file_hash` | test generici dedup | hash locali disponibili | Migrare a chiave SHA-256 senza rompere compatibilita' storica. |
| Stesso pipeline `Documenti` | PRESENTE | `drive_documenti_ingest.sync_tutti` | test route/ingest | esecuzione live non letta | Conservare `Documenti` come unica entrata. |
| Pulsante `Sincronizza Drive ora` fiscale | ASSENTE | endpoint backend presenti; nessun chiamante frontend fiscale | test route solo backend | non verificato | Collegare il comando nella pagina `Documenti`, senza nuova pagina parallela. |
| Snapshot AdeR 10/08/2026 (43 documenti) | ASSENTE | solo testo requisiti 68-89 | nessun test | `CERALDI_GROUP_04523831214_AER_2026-08-10.zip` non e' nel pacchetto | Non seedare numeri/valori senza archivio e hash; implementare schema/import generico. |
| Stati AdeR portal vs business | ASSENTE | nessun `ader_position_snapshots` | assenti | esempi solo nel testo allegato | Implementare snapshot immutabili e calcolo separato. |
| Micro-residui/sospensioni/net payable | ASSENTE | nessun motore AdeR | assenti | esempi non verificabili senza ZIP AdeR | Implementare soglia configurabile e stati fail-closed. |
| Sicurezza: PDF fiscali fuori Git | PRESENTE | `git ls-files '*.pdf'` mostra solo report audit documentale | controllo Git | fixture solo fuori repo | Mantenere `.private/`/ignore e controllo CI. |
| Sicurezza: segreti fuori Git | PRESENTE | nessun `.env`, PEM/key/credential tracciato | controllo Git | n/d | Aggiungere secret scan CI se non gia' coperto. |
| Autenticazione/RBAC | PRESENTE | middleware globale + dipendenze admin | test guardie | 401 live confermato | Aggiungere guardia esplicita sui router sensibili dove manca. |
| MFA azioni sensibili | PARZIALE | Assistente usa MFA; Drive fiscale usa solo admin | test MFA | sessione non disponibile | Definire e testare matrice delle azioni fiscali che richiedono step-up. |
| Streaming/signed URL protetti | PARZIALE | streaming Mongo dietro middleware; nessun URL firmato/scoped | workflow viewer | live non collaudato | Aggiungere autorizzazione per entita'/company e audit download. |
| Audit log | PARZIALE | `audit_log`, logger best-effort | test non trasversali | copertura live non misurata | Rendere obbligatorio per mutazioni fiscali e relazioni. |
| Isolamento `company_id` | ASSENTE | nessun uso runtime/test trovato | assenti | sistema attuale apparentemente monoazienda | Introdurre scoping in schema, indici, query, token e test cross-company. |
| CI commit corrente | DIVERGENTE | 6 workflow verdi, `Backend tests` rosso | run `31375169551` | deploy comunque sul commit | Rigenerare mappe endpoint; poi ripetere suite completa. |

## Conclusione audit

Il main e' piu' recente degli ZIP per Assistente, relazioni contabili, banca/POS e Drive fiscale. Non va sostituito. Le parti realmente mancanti sono il dominio fiscale/riscossione strutturato, lo snapshot AdeR, il registro obblighi/crediti con lineage, il bridge IVA/F24/bilancio completo, la prova documentale a pagina e i gate live di Drive/DB. I dataset sono preparati e in parte gia' presenti come documenti, ma non risultano dimostrati come importati e riconciliati integralmente.
