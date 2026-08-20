# GestionaleCloud - lavoro mancante o incompleto

<!-- gestionalecloud-doc
status: historical
reviewed_at: 2026-08-20
storage_architecture: drive-only
-->

> [!NOTE]
> Snapshot storico: non descrive lo stato operativo corrente. Per l'architettura Drive-only usare `README.md`, `PRODUCT.md`, `CLAUDE.md` e `LOGICA_FUNZIONAMENTO.md`.

Questo documento contiene soltanto gli esiti `PARZIALE`, `ASSENTE` o `DIVERGENTE` dell'audit del 2026-08-10.

## Bloccanti di prova

1. Ottenere una lettura amministrativa corrente, in sola lettura, delle collezioni DB e degli endpoint `/api/documenti/drive/fiscal/status` e `/api/documenti/tax-codes/status`.
2. Eseguire la discovery Drive API sulla root `1f48bounfoOyHL_kqpHAp2GAnFfEpHvVa` e registrare gli ID reali/univoci di `Avvisi bonari` e `Cartelle esattoriali`.
3. Registrare in `Documenti` l'archivio AdeR verificato nel pacchetto MASTER prima di qualunque import reale. L'archivio e' stato trovato e validato, ma non e' stato scritto nel DB.
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

- Le collezioni di dominio, il ravvedimento, gli agenti, il dossier, il pacchetto prove e il pannello evidenze esistono gia': non duplicarli.
- Integrare nel dominio corrente la baseline AdeR per posizione e collegarla a documenti, piani ed eventi mediante prove.
- Conservare riferimenti rateali ambigui come anomalie: i numeri a 17 cifre si risolvono solo contro una e una sola posizione analitica a 20 cifre.

## Snapshot AdeR

- L'import generico e immutabile, il dry-run, la verifica SHA-256, il merge non distruttivo, la soglia micro-residuo e la separazione tra stato portale e stato gestionale sono implementati.
- Restano da eseguire l'import reale attraverso un archivio registrato in `Documenti` e il collaudo amministrativo sul database di produzione; nessun PDF viene letto direttamente dal filesystem in esercizio.
- Aggiungere il confronto temporale tra snapshot N/N+1 e generare eventi espliciti per variazioni di residuo, sospensione, sgravio e chiusura.
- Validare con l'utente le posizioni marcate `MICRO_RESIDUAL_REVIEW`, i riferimenti rateali non univoci e ogni definizione priva di quietanza prima di cambiare lo stato contabile.

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
