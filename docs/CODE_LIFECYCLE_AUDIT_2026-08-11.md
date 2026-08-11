# Audit del ciclo di vita del codice — 2026-08-11

## Perimetro e regola di sicurezza

Audit eseguito sul checkout canonico `C:\Users\ceral\Documents\GESTIONALE CLOUD 2`
del repository `ceraldicontabilita/GestionaleCloud`.

Non sono stati importati documenti fiscali, modificati dati reali, eseguiti
deploy o pubblicati commit. Il ramo analizzato e'
`codex/p0-f24-parser-audit-fix`; `origin/main` e' una linea diversa e va
integrata solo con autorizzazione esplicita.

Il codice non viene spostato in base a parole come `legacy` o a un file non
montato come router: in questo progetto molti moduli smontati espongono ancora
funzioni importate dai parser, dagli scheduler o dai test. La quarantena e'
quindi reversibile e basata su prove di riferimento.

## Risultati misurabili

| Area | Risultato |
|---|---|
| Python applicativo | 518 file; 0 errori di parsing nell'audit architetturale |
| Router/endpoint | 161 moduli router; 1.117 route rilevate |
| Frontend | 181 moduli analizzati dal grafo reale |
| Frontend orfani eliminabili | 0 |
| Frontend dinamici da verificare | 23 |
| Audit statico | 411 finding (prevalentemente contratti P1, non prove di codice morto) |
| Test AI/chat mirati dopo correzioni | 38 passati |

## Codice non attivo come router ma ancora usato

Questi moduli non sono registrati in `app/router_registry.py`, ma non sono
eliminabili o spostabili:

| Modulo | Prova di uso |
|---|---|
| `app/routers/distinte_bpm.py` | `documenti.upload_auto` importa `import_distinte_bpm` |
| `app/routers/libro_unico_parser.py` | `documenti.upload_auto` importa `import_libro_unico` |
| `app/routers/f24_parser.py` | bridge/test e servizi importano il parser; il router HTTP e' smontato |
| `app/routers/bank/pos_accredito.py` | il router e' smontato, ma il calcolo canonico e' in `app/utils/pos_accredito.py` |
| `app/routers/reports/report_pdf.py` | importato da test e package reports; non e' una prova di codice morto |
| `app/routers/reports/simple_exports.py` | mantenuto come compatibilita' di package; verificare chiamanti prima di muoverlo |
| `app/routers/trattenute_verbali.py` | il servizio omonimo e' usato da scheduler, verbali e cedolini |

Conclusione: nessuno di questi file e' stato spostato. Spostarlo senza prima
separare router e helper romperebbe l'import della pipeline Documenti o i test.

## Frontend e pagine

Il grafo generato da `scripts/audit_frontend_dead_code.py` non ha orfani
eliminabili. I 23 elementi `DINAMICO_DA_VERIFICARE` sono componenti Radix,
store/hook o riferimenti a runtime e restano in revisione manuale; non sono
stati archiviati perché il nome compare nel codice o l'import è dinamico.

È stato corretto un errore funzionale verificato dal collaudo: `AnnoProvider`
veniva montato anche sulla pagina pubblica `/login` e chiamava l'endpoint
protetto `/api/config-import/anno`, producendo un 401 e un errore console a ogni
pagina. Ora il provider viene montato solo dentro `RequireAuth`.

## Chat AI e memoria

La configurazione canonica aveva `OPENAI_API_KEY`, mentre la chat usava solo
Anthropic. La chat ora:

1. seleziona OpenAI come provider preferenziale (`OPENAI_API_KEY` o chiave
   cifrata in `settings`, `chiave=openai`);
2. mantiene Anthropic come fallback compatibile;
3. riusa lo stesso schema di strumenti read-only e registra i tool call;
4. mantiene cronologia per sessione e non consente scritture contabili dal
   modello;
5. espone modello/provider nella diagnostica senza restituire segreti;
6. offre le impostazioni `/api/settings/openai` e `/api/settings/openai/test`.

La lettura, il salvataggio e il test delle chiavi OpenAI/Anthropic sono protetti
da `get_current_admin_user`; la chiave non viene mai restituita al frontend o
scritta nei log. Il modello configurato in database viene rispettato anche
quando la chiave proviene dal database.

La presenza di una chiave in ambiente o database non e' stata verificata in
questo checkout e nessuna chiave e' stata stampata o committata.

## Quarantena proposta (non ancora applicata)

La cartella `archive/legacy-audit/` contiene la policy, non copie operative.
Un file potra' essere spostato solo quando:

- non e' raggiunto da import statici o dinamici;
- non e' un helper chiamato da parser/scheduler;
- non e' richiesto da test o migrazioni supportate;
- il catalogo endpoint non lo considera pubblico;
- suite backend/frontend e build restano verdi dopo `git mv`;
- esiste un manifest con percorso originale, hash e motivo.

Finché uno di questi gate manca, la classificazione corretta e'
`DA_VERIFICARE`, non `CODICE_MORTO`.

## Collaudo E2E e limiti

`scripts/collaudo_ui.mjs` ha aperto le 62 route del catalogo contro il frontend
locale. Prima della correzione tutte mostravano lo stesso 401 di
`/api/config-import/anno`, causato dal provider globale non autenticato; non
sono stati cliccati comandi mutativi.

Il backend locale non ha potuto avviarsi perché MongoDB non e' in esecuzione su
`localhost:27017`. Di conseguenza non e' stata dichiarata una verifica
autenticata delle pagine, dei dati reali o delle relazioni bidirezionali.
Servono un database di test e un token di sola lettura per il collaudo E2E
completo.

## Prossimi gate

1. Eseguire il collaudo UI nuovamente dopo la correzione con sessione
   autenticata.
2. Configurare un MongoDB di test e verificare `/api/chat/health` e
   `/api/chat/ask` con client OpenAI mockato o chiave autorizzata.
3. Completare la verifica dei 23 moduli dinamici e produrre manifest SHA-256.
4. Solo dopo approvazione esplicita, spostare piccoli gruppi in quarantena e
   pubblicare esclusivamente i file pertinenti.
