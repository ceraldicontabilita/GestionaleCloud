# GestionaleCloud - lavoro mancante o incompleto

Questo documento contiene soltanto gli esiti `PARZIALE`, `ASSENTE` o `DIVERGENTE` dell'audit del 2026-08-10.

## Bloccanti di prova

1. Ottenere una lettura amministrativa corrente, in sola lettura, delle collezioni DB e degli endpoint `/api/documenti/drive/fiscal/status` e `/api/documenti/tax-codes/status`.
2. Eseguire la discovery Drive API sulla root `1f48bounfoOyHL_kqpHAp2GAnFfEpHvVa` e registrare gli ID reali/univoci di `Avvisi bonari` e `Cartelle esattoriali`.
3. Rendere disponibile l'archivio citato dal testo `CERALDI_GROUP_04523831214_AER_2026-08-10.zip`: non e' contenuto nel pacchetto trasferito, quindi i 43 documenti AdeR e i relativi importi non possono essere seedati come prova.
4. Correggere il job CI backend rosso: le mappe endpoint committate non riflettono i test delle cinque nuove route fiscali.

## Import e riconciliazione dataset 2020-2026

- Creare un import job idempotente con dry-run, SHA-256, manifest, conteggi `insert/update/skip/conflict/error` e rollback logico.
- Importare dichiarazioni, LIPE, F24 e quietanze tramite `Documenti`; non creare una seconda pipeline o pagina.
- Confrontare i 320 PDF F24 con `f24_unificato` e `quietanze_f24`; l'ultima prova disponibile mostrava solo 48/130.
- Collegare dichiarazione/LIPE -> obbligo o credito -> F24 -> quietanza -> movimento banca e mantenere gli ambigui da confermare.
- Implementare credito fiscale, movimenti e lineage versionati; gli Excel sono staging, non fonte conclusiva.
- Integrare `company_id` in schema, indici, query e import prima di supportare piu' aziende.

## IVA, F24 e bilancio

- Integrare esplicitamente il ciclo dicembre: liquidazione 6012, acconto 6013 e saldo annuale 6099 come obblighi distinti.
- Confrontare importo interno e dato ufficiale del consulente senza sovrascrivere le versioni confermate.
- Distinguere competenza fiscale, data F24, data quietanza e data addebito banca.
- Integrare un bridge F24-bilancio che estingua debiti e non duplichi IVA, ritenute, contributi o altri costi gia' rilevati.
- Misurare e mostrare la copertura F24/quietanza/banca per riga e per delega.

## Riscossione, avvisi e cartelle

- Implementare `tax_collection_documents`, `tax_collection_claims`, `tax_collection_claim_lines`, `tax_collection_events`, `tax_notification_events`, `tax_legal_events`.
- Implementare `tax_rate_plans`, `tax_rate_installments`, `tax_rate_plan_claim_allocations`.
- Implementare `tax_settlement_programs`, `tax_settlement_applications`, `tax_settlement_claims`.
- Implementare `tax_credit_ledger`, `tax_credit_movements`, `tax_credit_lineage`.
- Implementare `collection_tax_code_registry`, `tax_code_crosswalk`, `legal_rule_versions`.
- Implementare `RavvedimentoEngine`, `FiscalControlAgent`, `AdvisorBriefGenerator`, `buildTaxReviewDossier`, `buildTaxEvidencePackage` come motori evidence-bound e revisionabili.
- Estendere `entity_relations` e il viewer con un pannello prove collegate bidirezionale, incluso numero pagina/intervallo pagina.

## Snapshot AdeR

- Implementare import generico e immutabile di snapshot AdeR con archivio sorgente, SHA-256 e merge non distruttivo.
- Separare sempre `portal_status`/bucket dal `calculated_business_status`.
- Conservare importo originario, pagato, sgravato, sospeso, rateizzato, definito, residuo ed esigibile ora.
- Implementare micro-residuo configurabile, residui accessori, sospensione totale, chiusura con causa e confronto snapshot N/N+1.
- Non caricare i 43 record specifici del testo finche' il relativo ZIP/PDF analitico non e' disponibile e verificato.

## Drive e documenti

- Verificare live che la root sia una cartella e che i due nomi attesi abbiano una sola corrispondenza; zero o duplicati devono fallire chiuso.
- Persistire gli ID Drive reali; i nomi restano solo etichette/discovery.
- Portare la deduplicazione canonica da MD5 a SHA-256, mantenendo compatibilita' con record storici.
- Testare Changes API su nuovo file, nuova versione, rename, move, delete/restore e token scaduto.
- Evitare una scansione completa di tutti i canali a ogni singola modifica rilevante.
- Collegare il comando `Sincronizza Drive ora` nella pagina `Documenti` esistente e mostrare ultimo esito/errori senza esporre ID o credenziali.

## Sicurezza e collaudo

- Aggiungere guardie esplicite e matrice RBAC alle route fiscali; usare step-up MFA per import, riconciliazioni definitive, rigenerazioni e mutazioni.
- Aggiungere scoping `company_id` e test di non-leak cross-company.
- Registrare ogni mutazione fiscale e ogni cambio relazione nell'audit log; il fallimento dell'audit non deve passare inosservato.
- Proteggere download/stream con autorizzazione sull'entita' e log accesso; non affidarsi solo alla conoscenza del `doc_id`.
- Eseguire test mirati, suite backend/frontend, build, CI verde e collaudo live autenticato desktop/mobile.
