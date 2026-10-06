# GestionaleCloud — Ceraldi ERP

Gestionale su misura di **Ceraldi Group S.r.l.** per la gestione integrata di contabilità, fatture, banca, F24, personale, HACCP, magazzino, Menu digitale e servizi B&B.

Produzione:

**https://gestionalecloud.onrender.com**

## Fonte normativa

Le regole applicative, l'architettura, lo stato effettivamente verificato e il lavoro ancora aperto sono mantenuti in:

**`CLAUDE.md`**

`CLAUDE.md` è la fonte normativa del repository.

Questo `README.md` è esclusivamente una guida tecnica d'ingresso al progetto.

In caso di divergenza:

1. il **codice e la configurazione realmente in produzione** hanno precedenza;
2. `CLAUDE.md` deve essere corretto nello stesso intervento quando descrive uno stato non più vero;
3. il README deve essere riallineato quando cambia l'architettura generale.

Non creare documenti paralleli permanenti per piani, audit, changelog o stato del progetto.

La cronologia delle modifiche resta in Git.

---

# Architettura generale

GestionaleCloud viene distribuito come **un unico servizio FastAPI**.

Il processo principale è:

```text
app/main.py
```

e serve dallo stesso host ERP, HR, Menu, Lotti e l'area Colazioni/B&B.

## Applicazioni servite

| Area | Rotte principali | Backend | Frontend | Accesso |
| --- | --- | --- | --- | --- |
| ERP / Contabilità | `/`, `/api/*` | `app/` | `frontend/` | sessione amministratore ERP |
| HR / AppDipendenti | `/hr`, `/hr/portale`, `/hr/api/*` | `app/hr/` | `frontend_hr/` | dipendente: nome + PIN personale; admin: sessione ERP |
| Menu | `/menu`, `/menu/admin`, `/menu/api/*` | `app/menu/` | `frontend_menu/` | admin: sessione ERP |
| Lotti / HACCP | `/lotti`, `/lotti/api/*` | `app/lotti/` | `frontend_lotti/` | operatore: PIN personale; admin: sessione ERP; eccezioni autorizzate definite in `CLAUDE.md` |
| Colazioni / B&B | `/convenzioni/` | API ERP/Menu + RPC Supabase | `frontend_colazioni/` | titolare, albergatore e ospite con flussi distinti |

Il vecchio percorso `/colazioni` reindirizza a `/convenzioni`.

`frontend_colazioni` è una pagina statica e non segue la stessa build React degli altri frontend.

---

# Routing

Le sotto-app devono essere montate in `app/main.py` **prima del catch-all della SPA ERP**.

Il `Mount` di Starlette richiede particolare attenzione ai prefissi senza slash finale.

Per esempio:

```text
/lotti
```

deve essere correttamente reindirizzato verso:

```text
/lotti/
```

prima che intervenga il catch-all ERP.

Una route tecnica o un prefisso non documentato qui, come eventuali alias o mount aggiuntivi, deve essere verificato nel codice prima di essere considerato parte dell'architettura pubblica.

Non aggiungere nuovi alias senza una reale necessità di compatibilità.

---

# Repository canonico

Repository:

```text
https://github.com/ceraldicontabilita/GestionaleCloud
```

Il repository GestionaleCloud è il repository operativo canonico.

Vecchi repository o progetti separati non devono diventare nuovamente fonti indipendenti della logica applicativa.

Prima di lavorare:

```bash
git fetch origin
git status
git log --oneline --decorate -n 10
```

Confrontare sempre il branch corrente con `origin/main`.

Non cancellare o sovrascrivere modifiche locali non proprie.

Non usare:

```bash
git add -A
```

Aggiungere solo i file pertinenti alla modifica.

---

# Dati e persistenza

## Supabase

**Supabase è l'archivio strutturato principale del gestionale.**

Il backend supportato è:

```text
DATA_BACKEND=supabase
```

Schemi principali:

```text
gestionale
hr
lotti
menu
```

È presente anche:

```text
legacy_staging
```

ma deve essere considerato **transitorio**.

Contiene dati ancora da migrare o verificare attraverso i flussi applicativi normali.

Non deve diventare un secondo archivio permanente.

---

# Google Drive

Google Drive conserva gli **originali documentali**.

Non è il database applicativo.

Il flusso documentale principale usa la cartella unica con:

```text
DA ELABORARE
ELABORATE
ERRORI
```

Eventuali aree come `ARRETRATO` o gestione dei doppioni seguono le regole definite in `CLAUDE.md`.

Principio fondamentale:

```text
Supabase = dati strutturati, stato applicativo e relazioni
Drive = originali documentali
```

La presenza di un file in Drive non dimostra da sola che sia stato correttamente importato.

La prova dell'acquisizione è il relativo record applicativo/protocollo.

---

# Regole documentali fondamentali

## Riconoscimento

Un documento deve essere identificato principalmente dal **contenuto**.

Nome file, cartella e data del file possono aiutare:

- a ordinare il lavoro;
- a trovare un candidato;
- a spiegare il contesto.

Non devono diventare prova definitiva di:

- tipo documento;
- periodo fiscale;
- soggetto;
- pagamento;
- riconciliazione.

Esistono ancora percorsi da migrare che utilizzano nome o percorso come parte della classificazione: sono debito tecnico e non il comportamento finale desiderato.

---

# Duplicati

Un duplicato documentale certo richiede:

```text
SHA-256 uguale
+
contenuto byte-identico
```

Nome, dimensione, data o importo non sono sufficienti a dichiarare due documenti identici.

L'identità business può servire per individuare **possibili duplicati**, che devono essere verificati secondo il dominio:

- fattura;
- F24;
- quietanza;
- cedolino;
- bonifico;
- verbale;
- altro documento.

I duplicati non si eliminano alla cieca.

---

# Modello logico dei dati

L'obiettivo architetturale è che ogni flusso segua questa catena:

```text
DOCUMENTO
   ↓
FATTO CANONICO
   ↓
OBBLIGO / CREDITO
   ↓
PAGAMENTO
   ↓
PROVA
   ↓
SCRITTURA CONTABILE
   ↓
RICONCILIAZIONE
   ↓
PROIEZIONE / INTERFACCIA
```

Ogni passaggio deve mantenere identificatori e relazioni verificabili.

Non affidarsi a booleani isolati o campi duplicati quando il fatto può essere derivato dalle relazioni canoniche.

---

# Prova documentale e prova bancaria

Fattura, disposizione di bonifico, quietanza, ricevuta e movimento bancario sono **fatti distinti**.

Per esempio:

```text
PDF bonifico
```

prova che esiste una disposizione/documentazione.

Non prova necessariamente che l'addebito sia avvenuto sul conto.

La prova bancaria definitiva è il movimento compatibile presente nell'estratto ufficiale, secondo le regole del dominio.

Lo stesso principio vale per F24, stipendi, PagoPA, mutui e pagamenti fornitori.

---

# Contabilità

Il gestionale usa:

- Prima Nota;
- libro giornale in partita doppia;
- Piano dei Conti CEE;
- riconciliazioni;
- bilancio e viste finanziarie.

La regola contabile fondamentale è:

```text
DARE = AVERE
```

al centesimo.

Una scrittura che non quadra non deve essere considerata valida.

---

# Competenza e pagamento

La competenza economica e il pagamento sono due fatti differenti.

Il costo segue la competenza.

Il pagamento chiude il relativo debito.

Esempio:

```text
FATTURA

DARE   costo
DARE   IVA
AVERE  debiti fornitori
```

Successivamente:

```text
PAGAMENTO

DARE   debiti fornitori
AVERE  banca
```

La stessa separazione vale per:

- stipendi;
- F24;
- ritenute;
- contributi;
- altri debiti.

Non trasformare un pagamento in un nuovo costo.

---

# Stato contabile attuale

Alcuni flussi storici non rispettano ancora completamente il modello sopra.

In particolare sono ancora oggetto di bonifica o completamento:

- chiusura contabile dei debiti al pagamento;
- competenza usata dal bilancio;
- relazioni banca ↔ fatture;
- partite aperte mancanti;
- pagamenti HR e cedolini orfani;
- dati storici di note di credito;
- alcune scritture contabili precedenti non quadrate;
- relazioni documentali non ancora completamente ricostruite.

Per valori, quantità e stato puntuale aggiornato consultare esclusivamente la sezione **Stato attuale** e **Aperto** di `CLAUDE.md`.

Non copiare nel README conteggi destinati a diventare rapidamente obsoleti.

---

# Fatture

Le fatture ricevute appartengono al dominio ERP.

Le fatture devono avere:

- identità stabile;
- fornitore canonico;
- righe;
- importi;
- originale;
- stato finanziario derivabile;
- eventuali pagamenti;
- eventuale partita aperta;
- scrittura contabile.

Non dedurre il pagamento dal solo metodo del fornitore.

Il metodo di pagamento previsto e il pagamento realmente provato sono concetti differenti.

## Identificatori

Il sistema contiene ancora fatture storiche con identificatori di tipo diverso.

Il codice esistente deve usare gli helper canonici per leggere queste righe.

Il target è una sola identità stabile per le relazioni future.

Non introdurre nuovo codice che presuma che tutti gli ID storici abbiano lo stesso tipo.

---

# Banca

I movimenti dell'estratto conto sono la principale prova reale dei pagamenti bancari.

Un movimento bancario non deve essere assegnato automaticamente soltanto per importo.

Il matching deve considerare, quando disponibili:

- identità;
- soggetto;
- IBAN;
- riferimento;
- causale;
- importo;
- data;
- documento collegato.

Un caso ambiguo resta:

```text
DA_VERIFICARE
```

e presenta i candidati all'operatore.

---

# F24

Modello F24, righe tributo, quietanza e movimento bancario sono entità distinte.

La quietanza documenta il versamento.

Il movimento dell'estratto conto fornisce il riscontro bancario.

Usare stati espliciti che distinguano almeno semanticamente:

```text
DA_PAGARE
VERSAMENTO_DOCUMENTATO
DA_VERIFICARE
RISCONTRATO_IN_BANCA
```

Non usare un unico concetto generico di «pagato» per prove di forza differente.

---

# Personale e cedolini

L'anagrafica HR è la fonte canonica delle persone e dei dipendenti.

Il gestionale ERP collega i pagamenti, ma non deve mantenere una seconda anagrafica indipendente.

I cedolini devono essere identificati per:

- dipendente;
- periodo;
- tipo;
- versione.

Il netto verificato viene letto dal documento.

Un valore assente non è zero.

Bonifici e cedolini si riconciliano attraverso il motore canonico dedicato, non con confronti locali creati da singole pagine.

---

# Lotti e HACCP

Lotti è il dominio operativo per:

- ricette;
- ingredienti;
- produzioni;
- lotti;
- giacenze;
- HACCP;
- attrezzature;
- firme operative.

Non possiede fatture o contabilità.

Riceve i riferimenti necessari dall'ERP.

Una fattura importata nell'ERP può alimentare Lotti tramite il flusso previsto, senza duplicare il fatto contabile.

---

# Menu

Il Menu usa il catalogo `menu`.

Lotti pubblica verso Menu i dati delle ricette.

Il Menu non deve mantenere una seconda copia indipendente della ricetta tecnica.

Il target è un prodotto condiviso tra:

- Menu;
- Lotti;
- B&B;
- Cassa.

## Attenzione

L'unificazione completa del prodotto e il codice `PRD-xxxxxx` dipendono dalle relative migrazioni Supabase.

Finché tali migrazioni non risultano applicate e verificate sul database di produzione, non assumere che l'architettura del prodotto unico sia già completamente operativa.

Controllare `CLAUDE.md` prima di modificare questi flussi.

---

# Colazioni e B&B

L'area B&B è servita da:

```text
/convenzioni/
```

e usa:

```text
frontend_colazioni/
```

Il frontend è statico e utilizza RPC Supabase e API backend autorizzate.

I principali soggetti sono:

- titolare;
- struttura/albergatore;
- ospite.

Menu e B&B devono convergere sul catalogo prodotto canonico quando la relativa migrazione risulta effettivamente applicata.

---

# Autenticazione

## Amministratore

ERP fornisce la sessione amministratore comune alle applicazioni.

HR, Menu e normalmente Lotti riutilizzano questa sessione.

Lotti possiede eccezioni specifiche per il PIN personale del titolare definite nelle regole applicative.

Non creare un secondo login amministratore indipendente.

L'MFA deve essere applicata dove prevista dalle operazioni protette e dalle policy effettivamente implementate.

Non dichiarare un requisito MFA più ampio di quello realmente verificato nel codice.

---

# Dipendenti

Il login ordinario del dipendente usa:

```text
nome/persona + PIN personale
```

Il PIN personale appartiene all'identità HR.

Non creare PIN paralleli per le diverse applicazioni.

---

# Segreti

Credenziali, token, password, PIN e chiavi private non devono essere salvati nel repository.

I valori reali vivono nelle variabili d'ambiente di Render o nei sistemi sicuri espressamente previsti.

`render.yaml` descrive le variabili attese con configurazioni sicure.

Attenzione: una parte della configurazione operativa Render può essere impostata anche nella dashboard.

Quindi la configurazione effettivamente pubblicata deve essere verificata anche sul servizio Render prima di considerare `render.yaml` l'unica fonte dell'ambiente runtime.

La cronologia Git contiene vecchi segreti che devono essere gestiti secondo la procedura descritta in `CLAUDE.md`.

---

# Struttura del repository

```text
app/
    backend Python
    routers/
    services/
    hr/
    lotti/
    menu/

frontend/
    ERP React + Vite

frontend_hr/
    HR React

frontend_lotti/
    Lotti

frontend_menu/
    Menu

frontend_shared/
    componenti condivisi dove previsti

frontend_colazioni/
    area B&B / Colazioni statica

backend/
    dipendenze di produzione

scripts/
    build
    manutenzione
    audit
    strumenti locali

supabase/
    migrazioni SQL

tests/
    test backend e frontend per area

page_catalog.json

CLAUDE.md

README.md
```

---

# Toolchain frontend

Attualmente le applicazioni non utilizzano tutte la stessa toolchain:

```text
ERP        Vite
HR         Vite
Menu       CRA
Lotti      CRA
B&B        frontend statico
```

Questa è la situazione da considerare nel lavoro quotidiano.

L'eventuale unificazione della toolchain è un obiettivo di ristrutturazione e non deve essere data per già completata.

---

# Installazione locale

Il frontend ERP usa `yarn.lock`.

Usare Yarn secondo le stesse versioni e modalità adottate dalla CI.

Installazione backend:

```bash
pip install -r backend/requirements.txt
```

Installazione frontend ERP:

```bash
yarn --cwd frontend install --frozen-lockfile
```

Build:

```bash
yarn --cwd frontend build
```

Il processo di build richiama gli script previsti per le altre applicazioni.

Avvio backend:

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Una build frontend mancante può rendere indisponibili le SPA pur lasciando raggiungibili le API.

---

# Test

Suite backend isolata:

```bash
python scripts/collaudo_isolato.py -q
```

Frontend ERP:

```bash
yarn --cwd frontend test
```

Lotti:

```bash
python scripts/collaudo_isolato.py tests/lotti
```

HR:

```bash
python scripts/collaudo_isolato.py tests/hr
```

Le suite sono organizzate principalmente in:

```text
tests/banca
tests/contabilita
tests/documenti
tests/fatture
tests/fiscale
tests/frontend
tests/hr
tests/lotti
tests/menu
tests/noleggio
tests/runtime
```

Il runner di test deve isolare le credenziali reali e impedire connessioni involontarie ai servizi di produzione.

Un test verde su fixture locali non dimostra che:

- i dati reali siano coerenti;
- le relazioni di produzione siano integre;
- una migrazione sia stata applicata;
- un flusso live riconcili realmente i documenti.

---

# Modifiche ai dati

Prima di una modifica che tocca dati reali:

1. individuare il proprietario canonico del dato;
2. individuare il writer canonico;
3. verificare eventuali relazioni;
4. verificare eventuali scritture contabili;
5. verificare se esiste già un motore per quella funzione;
6. usare `dry_run` quando disponibile;
7. evitare SQL manuale se esiste un percorso applicativo che produce anche audit, eventi o scritture correlate.

Non creare un secondo motore per aggirare un problema del primo.

Correggere il motore canonico.

---

# Migrazioni Supabase

Ogni modifica strutturale applicata al database deve avere la corrispondente migrazione versionata nel repository.

Percorso:

```text
supabase/migrations/
```

La versione deve corrispondere al registro reale delle migrazioni.

Non inventare numeri di versione.

Il repository deve poter spiegare come ricostruire il database.

Sono presenti migrazioni o strutture storiche che devono ancora essere riallineate al repository: verificare `CLAUDE.md` prima di modificare schemi come Cassa, Catalogo, Menu/B&B e relative viste.

---

# Eliminazioni

Non eliminare dati soltanto perché sembrano vecchi.

Prima verificare:

- lettori;
- writer;
- route;
- job;
- import dinamici;
- dati persistiti;
- relazioni.

Per documenti e fatti contabili preferire:

```text
storno
quarantena
rimosso
sostituito
revocato
```

quando il dominio richiede conservazione della storia.

---

# Regola “un sistema per funzione”

Il target architetturale è:

```text
un writer canonico
un motore per regola
una fonte autorevole
proiezioni rigenerabili
```

Esistono ancora eccezioni e duplicazioni note, soprattutto in:

- HR;
- lettori documentali AI;
- vecchie logiche legacy;
- ricerca web Lotti;
- alcuni flussi fiscali;
- alcuni endpoint originali HR.

Non aggiungere ulteriori duplicazioni.

Quando si modifica una di queste aree, verificare `CLAUDE.md` per il percorso di consolidamento previsto.

---

# Frontend

Le nuove pagine devono essere semplici e operative.

Per ERP:

- `PageHeader`;
- una riga filtri;
- tabella;
- caricamento progressivo;
- card automatiche su mobile.

Per HR, Menu e Lotti valgono i rispettivi token e componenti descritti in `CLAUDE.md`.

Non introdurre un design system parallelo.

Non duplicare componenti quando esiste già il componente canonico.

---

# Originali documentali

Per l'ERP l'apertura degli originali passa dal servizio e componente canonici definiti in `CLAUDE.md`.

Alcuni endpoint HR mantengono ancora percorsi propri per rispettare i permessi del dipendente.

Questi sono eccezioni ancora da consolidare.

Non creare nuovi endpoint alternativi per aprire documenti.

---

# Verifica prima del merge

Per ogni modifica pertinente:

```text
1. test mirati
2. suite backend se necessaria
3. test frontend interessati
4. build frontend interessati
5. git diff --check
6. revisione avversariale del diff
7. commit dei soli file pertinenti
8. PR finale
9. merge su main
10. verifica deploy
11. verifica health
12. controllo live del flusso
```

La presenza di:

```text
HTTP 200
```

non dimostra che un flusso sia corretto.

Verificare:

- dato creato;
- dato aggiornato;
- relazione;
- deduplica;
- stato finale;
- eventuale scrittura contabile;
- risultato nell'interfaccia.

---

# Branch e CI

La strategia operativa definitiva è descritta in `CLAUDE.md`.

In generale:

- il lavoro si sviluppa fuori da `main`;
- la PR viene aperta quando il lavoro è completo;
- `main` è il ramo che Render pubblica;
- i branch di salvataggio non devono produrre inutilmente workflow costosi se la configurazione CI li esclude.

La configurazione effettiva dei trigger è quella presente in:

```text
.github/workflows/ci.yml
.github/workflows/produzione.yml
```

Se il README, `CLAUDE.md` e i file YAML non concordano, correggere la documentazione sulla base dei workflow reali.

---

# Deploy

Render pubblica da:

```text
main
```

Health check:

```text
/api/health
```

La pubblicazione non è considerata completata soltanto perché la build è terminata.

Bisogna verificare:

- commit effettivamente servito;
- health;
- API interessate;
- frontend;
- risultato sui dati reali quando la verifica è sicura e non distruttiva.

Produzione:

**https://gestionalecloud.onrender.com**

---

# Principio finale

Prima di aggiungere una nuova soluzione, chiedersi:

```text
Esiste già un motore che dovrebbe fare questa cosa?
```

Se sì:

**correggere quello.**

Non aggiungere:

- un secondo archivio;
- un secondo stato;
- un secondo parser;
- un secondo writer;
- una seconda riconciliazione;
- una seconda fonte della verità.

L'obiettivo di GestionaleCloud è avere un solo fatto canonico per ogni evento reale e collegare correttamente documenti, obblighi, pagamenti, prove e contabilità.
