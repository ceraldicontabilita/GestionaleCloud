# Matrice semantica ZIP / main — 10 agosto 2026

## Scopo e metodo

Questa verifica tratta gli ZIP come **specifica funzionale, patch candidate e raccolta di casi di test**, non come sorgente da copiare sopra il repository.

Repository autorevole:

- repository: `ceraldicontabilita/GestionaleCloud`;
- checkout: `C:\Users\ceral\Documents\GESTIONALE CLOUD 2`;
- ramo: `main`;
- commit di partenza: `10fe2ec08ac944afeb35425d7d129183e16036b9`.

Archivi esaminati integralmente:

| Archivio | Elementi | SHA-256 |
|---|---:|---|
| `GestionaleCloud_Codex_Assistente_Ceraldi.zip` | 1.401 | `6CA2F5D91F0026F76B0FEA531F16D5361A3EBD2A5A6F939D8B909F510431FEC1` |
| `Documenti_audit_GestionaleCloud.zip` | 2 | `CEC015FACE5DC226CC5126D3DB50282A419E6B184766A6F8E359066E1FFF1A49` |

La classificazione non confronta soltanto i nomi dei file. Per ogni area sono stati confrontati funzioni, endpoint, collezioni, regole contabili, autenticazione, registrazione router, navigazione, scheduler, test, provenienza e comportamento fail-closed.

## Legenda

- **PRESENTE IDENTICA**: nessuna modifica necessaria.
- **PRESENTE MIGLIORE NEL MAIN**: mantenuta l'implementazione corrente.
- **PRESENTE MA INCOMPLETA**: completata senza sostituire le parti valide.
- **ASSENTE**: funzione adattata e integrata.
- **CONFLITTUALE**: implementazioni divergenti; adottata quella più robusta o composta una soluzione senza regressioni.

## Matrice ragionata

| Area | Stato rispetto al main | Evidenza semantica | Azione |
|---|---|---|---|
| Collezioni operative (`operational_facts`, `learned_patterns`, `expected_events`, `administrative_anomalies`, `decision_questions`, `case_memory`, `knowledge_sources`) | **ASSENTE** | Nel main non esisteva uno strato persistente dedicato esclusivamente alla memoria operativa. | Aggiunte collezioni e indici; le scritture sono limitate alle collezioni dell'Assistente. |
| Operational Learning | **PRESENTE MA INCOMPLETA** | Il main contiene motori contabili e servizi specialistici, ma non un servizio unico che memorizzi fatti, pattern, eventi attesi, domande e casi confermati. | Integrato un motore operativo idempotente che osserva i motori di dominio senza riscriverne i dati. |
| Association Engine fatture/pagamenti/assegni | **PRESENTE MIGLIORE NEL MAIN** | Il main dispone già di `payment_invoice_matching.py`, `payment_document_links.py` e `reconciliation_orchestrator.py`, con controlli più ricchi dello ZIP. | Nessuna sostituzione. L'Assistente usa gli esiti e mantiene ambigui i casi senza identità univoca. |
| Tax Obligation Engine | **ASSENTE** | Mancava la rappresentazione persistente di un tributo atteso per codice, anno, mese e importo esatto. | Integrata la creazione validata di obbligazioni fiscali attese, con importo positivo e periodo fiscale coerente. |
| Expected vs Actual | **PRESENTE MA INCOMPLETA** | Esistevano riconciliazioni di dominio, ma non un confronto uniforme e tracciato fra eventi attesi ed eventi effettivi. | Integrato confronto a centesimi, con stato soddisfatto/parziale/mancante e prova dell'evento effettivo. |
| Administrative Sentinel | **CONFLITTUALE** | Il main ha già una sentinella fiscale specializzata; lo ZIP propone una sentinella amministrativa generale. | Mantenuta la sentinella fiscale del main; aggiunto un controllo operativo giornaliero in sola osservazione, protetto da lease distribuito. |
| Adversarial Reasoning | **CONFLITTUALE** | La proposta ZIP poteva mantenere una conclusione troppo forte anche quando esisteva una contro-ipotesi compatibile. | Adattato il modello: la presenza di un altro debito compatibile nell'anno dichiarato riduce la confidenza e impedisce una conclusione automatica. |
| Cedolini parzialmente pagati | **PRESENTE MA INCOMPLETA** | Il main possiede motori paghe e riconciliazione più robusti; mancava la domanda operativa sul residuo al centesimo. | Preservati i motori paghe. Aggiunta soltanto la rilevazione del residuo e la domanda decisionale, senza alterare cedolini o movimenti. |
| Scadenze contratti e documenti di identità | **ASSENTE** | Mancava una coda operativa uniforme delle scadenze amministrative imminenti/scadute. | Aggiunta scansione osservativa dei dipendenti con domande verificabili e provenienza del record. |
| Targa → conducente temporale | **PRESENTE MA INCOMPLETA** | Il main contiene logica noleggio/veicoli più forte, ma non memorizzava il fatto operativo con intervallo temporale e fonte. | Integrata la memoria del fatto temporale; nessuna sostituzione dei dati noleggio. |
| F24 periodici attesi | **PRESENTE MA INCOMPLETA** | Il main riconcilia F24 e banca, ma non conservava in modo generale l'evento periodico atteso. | Aggiunti pattern ed eventi attesi, riconciliati contro le righe F24 reali. |
| F24 con annualità errata | **PRESENTE MA INCOMPLETA** | Il main ha servizi F24; lo ZIP aggiungeva casi di test, ma la conclusione proposta era troppo certa. | Integrato controllo anno dichiarato/anno compatibile con importo e codice tributo, sempre fail-closed e con contro-ipotesi. |
| Secondo pagamento con possibile errata imputazione | **PRESENTE MIGLIORE NEL MAIN** | I motori del main distinguono già prova bancaria, documento e strumento; lo ZIP rischiava di duplicare la scrittura. | Nessun nuovo pagamento automatico. L'Assistente segnala il rischio e lascia il blocco ai motori di dominio esistenti. |
| Osservazioni da email attendibili | **ASSENTE** | Non esisteva una memoria operativa versionata delle osservazioni provenienti da mittenti autorizzati. | Integrata registrazione solo da regole mittente attive, con hash del payload, provenienza e idempotenza. |
| Pagina `/assistente` | **ASSENTE** | Nessuna pagina operativa dedicata nel router frontend. | Aggiunta pagina amministrativa con anomalie, eventi attesi, domande, fonti e aggiornamento controllato. |
| API `/api/assistente` | **ASSENTE** | Il router ZIP non applicava le stesse garanzie di accesso del main. | API adattata con autenticazione amministrativa/MFA, payload rigorosi e nessuna scrittura sulle collezioni contabili. |
| Router, navigazione e catalogo | **PRESENTE MA INCOMPLETA** | Mancavano registrazione backend, rotta frontend, voce di navigazione e catalogazione della pagina. | Registrati endpoint e pagina, navigazione solo amministratori e catalogo aggiornato da 62 a 63 pagine funzionali. |
| Scheduler | **CONFLITTUALE** | Lo ZIP introduceva esecuzioni locali generiche; il main usa un'infrastruttura scheduler condivisa. | Integrato job giornaliero nel meccanismo del main con lease distribuito, evitando esecuzioni concorrenti. |
| React Query e sincronizzazione frontend | **PRESENTE MIGLIORE NEL MAIN** | Il main usa già React Query; il suggerimento ZIP basato su evento globale del browser avrebbe moltiplicato richieste e stato implicito. | Mantenuta React Query. Nessun `GLOBAL_REFRESH` introdotto. |
| Implementazioni ZIP semplificate di relazioni, paghe e associazioni | **CONFLITTUALE** | Alcuni moduli ZIP duplicano servizi di dominio più completi già presenti nel main. | Non importati. Riutilizzati i servizi esistenti come fonte autorevole. |
| Audit 63 pagine | **PRESENTE MA INCOMPLETA** | La documentazione ZIP riporta controlli statici ma dichiara l'E2E non eseguito. | Catalogo aggiornato; la pagina Assistente resta `in_review` finché non termina il collaudo runtime/live. |

## Confini di sicurezza applicati

1. L'Assistente può scrivere solo nelle sette collezioni operative dedicate.
2. Non modifica fatture, F24, cedolini, movimenti bancari, prima nota, Drive o documenti aziendali.
3. Un collegamento strumento-documento non viene trattato come prova di pagamento.
4. Gli importi sono confrontati con `Decimal` al centesimo; niente confronti float.
5. Se identità, periodo o importo sono ambigui, il caso resta da verificare.
6. Le risposte alle domande sono accettate solo fra le opzioni generate.
7. I casi entrano nella memoria soltanto dopo conferma esplicita.

## Verifiche eseguite

- test mirati del motore operativo: **12/12 superati**;
- test catalogo/router/guardie/contratti frontend: **20/20 superati**;
- suite backend completa: **1.660 superati, 2 saltati**;
- suite frontend completa: **159/159 superati** in 27 file;
- build frontend di produzione: **completata** con Vite 5.4.21;
- mappe router rigenerate: **1.087 endpoint**, **113 prefissi**, **113 tag**;
- artefatti generati dalla build esclusi dal commit.

Il collaudo live resta l'ultimo gate successivo al push e al completamento del deploy.
