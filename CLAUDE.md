# Istruzioni per Claude — GestionaleCloud (Ceraldi ERP)

<!-- gestionalecloud-doc
status: current
reviewed_at: 2026-09-17
storage_architecture: supabase
-->

Aggiornato il 20/08/2026 sul codice di `main` del repository canonico
`ceraldicontabilita/GestionaleCloud`.

**Questo file è l'unico documento normativo di GestionaleCloud** (unificato
il 17/09/2026: prima le regole erano sparse fra CLAUDE.md, PROMPT_MASTER.md,
AGENTS.md, DESIGN.md, PRODUCT.md, LOGICA_FUNZIONAMENTO.md e una decina di file
in `docs/`/`memoria/`; i file autonomi sono stati assorbiti qui e cancellati).
`PROMPT_MASTER.md` resta a parte solo perché è **generato dal codice**
(`scripts/genera_prompt_master.py`, catalogo pagine/variabili/endpoint): non
va letto come specifica normativa, si rigenera da solo e non si edita a mano.

Il codice corrente, i test e la configurazione effettiva di produzione hanno
sempre precedenza sui report storici presenti più sotto in questo file.

Indice delle sezioni normative: [Prodotto](#prodotto) ·
[Design system](#design-system) · [Logica di funzionamento](#logica-di-funzionamento) ·
[Regola fissa — attese](#regola-fissa--fatti-obblighi-attese-ed-evidenze) ·
[Autorità del repository](#autorità-del-repository) ·
[Fornitori](#fornitori--regola-canonica) · [Mappa dei moduli](#mappa-dei-moduli) ·
[Cedolini](#cedolini-regola-del-netto-pagabile) ·
[Policy contabile fiscale](#policy-contabile-fiscale-documentale) ·
[MCP](#mcp--specifica-e-runbook) · [Runbook Render/RT](#runbook-render--calderone) ·
[Disaster recovery](#disaster-recovery--archivio-supabase-e-originali-drive) ·
[Cronologia](#autorità-del-repository) (a seguire, sezioni datate).

## Lingua e risultato atteso

- Rispondi e documenta in italiano.
- Porta a termine una funzione alla volta: analisi, modifica, test, verifica
  e pubblicazione richiesta dall'utente.
- Non dichiarare completato un flusso basandoti soltanto su HTTP 200, build o
  presenza della pagina. Verifica dati, relazioni, deduplica e risultato live.
- Esponi all'utente il risultato e gli eventuali blocchi, non una sequenza di
  pulsanti tecnici da premere.

## Prodotto

`PROMPT_MASTER.md` resta come appendice meccanica rigenerata dal codice
(catalogo pagine, variabili ed endpoint, tramite `scripts/genera_prompt_master.py`):
non va editato a mano. La specifica normativa è questo documento (CLAUDE.md).

GestionaleCloud è l'ERP interno di Ceraldi Group S.R.L. Unisce documenti,
fatture, fornitori, Prima Nota, banca, fisco, personale, flotta e
riconciliazioni in un solo grafo operativo consultabile.

- Produzione: `https://impresasemplice.online`
- Repository: `ceraldicontabilita/GestionaleCloud`
- Utenti: amministrazione e team interno Ceraldi Group
- Perimetro fiscale predefinito: P.IVA `04523831214`

### Obiettivo

Ogni fatto economico deve essere acquisito una sola volta, conservare la
propria prova e risultare navigabile nelle sezioni collegate. Il gestionale
deve automatizzare i casi certi, mostrare le ambiguità e impedire duplicati e
scritture incoerenti.

```text
Documento originale
  -> entità amministrativa
     -> operazione canonica
        -> Prima Nota
           -> prova bancaria
              -> riconciliazione e stato finale
```

### Principi di prodotto

1. Una sola identità per operazione (`canonical_id` + `operation_id`).
2. Originali immutabili e provenienza sempre visibile.
3. Automatizzare soltanto corrispondenze certe e idempotenti.
4. Mostrare candidati e motivazione nei casi ambigui.
5. Un alert senza lista dei record interessati non è utile.
6. Le pagine collegate devono mostrare lo stesso stato senza ricaricamenti o
   manutenzioni manuali.
7. Supabase è il registro operativo unico; Drive conserva gli originali.

### Motore delle attese

Ogni fatto validato crea immediatamente le attese obbligatorie del proprio
flusso. Documenti e movimenti arrivati dopo sono evidenze: soddisfano un'attesa
esistente, non la inventano. Il processo è chiuso soltanto quando tutte le
attese obbligatorie sono `SODDISFATTO`, `NON_APPLICABILE` o `SUPERATO`.
Dettagli e test richiesti sono in `docs/REGOLA_FISSA_ATTESE.md`.

### Stato dell'architettura dati

In produzione il backend è `supabase`: `gestionale.documents` conserva le
collezioni logiche e `gestionale.blobs` i binari deduplicati. Il processo web
non serve dati da una cache idratata: legge la collezione richiesta dal
database e rende visibile una mutazione soltanto dopo conferma remota. Drive
resta l'archivio degli originali documentali. Sheets è solo un fallback di
sviluppo e non è la fonte della produzione.

### Fonti dati per dominio

Il prodotto aggrega fatti economici e documentali da sorgenti diverse. Le
fonti operative sono queste:

- Documenti: upload manuale, cartelle Drive configurate, email autorizzate e API dei gestori.
- Fatture e fornitori: XML/P7M da Drive o SDI, anagrafiche e alias normalizzati.
- Prima Nota: fatture, corrispettivi, banca, versamenti contanti, POS, cedolini e F24.
- Riconciliazione: estratti conto, movimenti bancari, CRO/TRN, descrizioni normalizzate e riferimenti del gestore.
- Fisco: modelli F24, codici tributo, quietanze, dichiarazioni e cartelle Drive dedicate.
- Flotta e verbali: email autorizzate, verbali PDF, ZIP, contratti, storico assegnazioni e prove di pagamento.
- Corrispettivi e POS: XML RT, chiusure terminale, accrediti del gestore e commissioni separate.

Il criterio è invariabile: i documenti originali restano immutabili, gli
importi non bastano da soli a provare un'associazione e i casi ambigui devono
mostrare candidati, non collegamenti silenziosi.

Albero Drive previsto:

```text
Radice GestionaleCloud
├── REGISTRO DATI
│   └── Ceraldi ERP - Registro dati
├── PARTENOPAY
├── CODICI TRIBUTO
├── QUIETANZE
└── DICHIARAZIONI
```

Il registro contiene 23 archivi canonici espliciti e può includere gli altri
archivi logici scoperti nel database durante la migrazione. Ogni foglio ha un
progressivo proprio e conserva il payload ricostruibile.

### Albero funzionale

Il catalogo macchina contiene 66 schermate operative.

I riferimenti più delicati del catalogo sono:

- Coerenza POS: pagina 40, nel ramo Riconciliazione.
- Elaborazioni amministrative: pagina 56.
- Elaborazioni legacy: pagina 57.

```text
Ceraldi ERP
├── Accesso
│   ├── Login
│   └── Gestione riservata
├── Dashboard e inserimento
│   ├── Dashboard
│   └── Inserimento rapido
├── Fatture e fornitori
│   ├── Archivio fatture
│   ├── Corrispettivi
│   ├── Fornitori
│   └── Verifica fatture estere
├── Prima Nota e personale
│   ├── Prima Nota Cassa/Banca
│   ├── Pulizia e controllo duplicati
│   ├── Cedolini e salari
│   └── Ritenute
├── Flotta e verbali
│   ├── Flotta noleggio
│   ├── Verbali noleggio
│   ├── Dettaglio verbale
│   └── Riepilogo costi
├── Contabilità e fisco
│   ├── Piano dei conti e libro giornale
│   ├── Bilancio e verifica
│   ├── Controllo mensile e calendario fiscale
│   ├── IVA, F24, ritenute e situazione fiscale
│   ├── Cespiti, finanziaria, mutui e chiusura
│   └── Budget, utile, previsioni acquisti e dati ISA
├── Riconciliazione
│   ├── Banca e documenti
│   ├── F24 e stipendi
│   ├── Bonifici e assegni
│   ├── PayPal e PagoPA
│   ├── Coerenza POS
│   └── Movimenti banca
├── Documenti e Drive
│   ├── Import documenti
│   ├── Archivio documenti
│   ├── Indice documentale Drive
│   └── Atti amministrativi
├── Strumenti e integrazioni
│   ├── Verifica coerenza
│   ├── Commercialista, pianificazione e visure
│   ├── OpenAPI e mittenti email
│   ├── Learning Machine e agenti
│   └── Impostazioni F24/AI
├── App del gruppo portate pari pari (pagina intera, login proprio)
│   └── HACCP Lotti (/lotti), HR (/hr), Menu (/menu)
└── Amministrazione
    ├── Sistema e Registro Drive
    ├── MFA ed utenti
    └── Elaborazioni e batch
```

### Flussi principali

#### Fattura fornitore

```text
Drive/SDI -> XML/P7M -> deduplica -> fornitore -> fattura
-> scadenza -> pagamento -> Prima Nota -> movimento banca -> riconciliata
```

#### Corrispettivi e POS

```text
XML RT -> ricavo/cassa
SumUp API -> totale giornaliero -> trasferimento SumUp atteso
chiusura Numia manuale serale -> trasferimento Numia atteso
export storico Numia Drive -> deduplica + totale giornaliero -> trasferimento Numia atteso
accredito gestore -> riconciliazione del trasferimento
commissione -> costo separato
```

#### Versamento contanti

```text
Versamento -> uscita Cassa + entrata Banca (stesso operation_id)
-> movimento estratto conto -> riconciliazione
```

#### F24

```text
Modello F24 -> righe per codice tributo -> quietanza
-> movimento bancario -> stato riconciliato
```

#### PartenoPay e verbali

```text
Email/ZIP -> verbale -> targa -> storico driver
-> pagamento/quietanza -> banca -> eventuale trattenuta
```

### Requisiti trasversali

- Import idempotente tramite hash e identità canonica.
- Relazioni bidirezionali navigabili.
- Importi contabili al centesimo e date utente in formato italiano.
- Prove distinte: documento, disposizione, ricevuta, quietanza, banca.
- Log di audit per ogni modifica significativa.
- Nessun pagamento automatico.
- Nessuna associazione definitiva ambigua.
- Nessuna eliminazione degli originali.

### Esperienza utente

- Interfaccia semplice, densa ma leggibile.
- Stato record visibile a colpo d'occhio.
- Azioni vicine al dato interessato.
- Rosso = errore, verde = verificato, oro = attenzione.
- Liste raggruppate per giorno quando la data è la chiave di lettura.
- Modali chiudibili da pulsante, overlay ed Escape, con documento leggibile.
- Desktop e mobile senza overflow; target touch minimo 44–48 px.
- La manutenzione tecnica resta in Admin e non sostituisce l'automazione.

### Non obiettivi

- Eseguire pagamenti in autonomia.
- Inventare classificazioni o legami mancanti.
- Considerare una quietanza equivalente al movimento bancario.
- Usare un importo come unica chiave di riconciliazione.
- Conservare per sempre un archivio operativo non portabile.
## Design system

Design system operativo del frontend. La fonte eseguibile dei token è
`frontend/src/lib/utils.js`; questa sezione spiega come usarli senza creare
varianti locali.

L'interfaccia deve sembrare un gestionale contabile, non una plancia di
comandi. Ogni pagina deve aiutare a capire subito:

1. quale periodo e archivio si stanno consultando;
2. quali dati sono certi, attesi, riconciliati o da verificare;
3. quale documento o movimento è l'origine del dato;
4. quale azione è automatica e quale richiede una scelta umana.

### Token ufficiali

| Uso | Valore |
|---|---|
| Primario navy | `#0f2744` |
| Primario chiaro | `#1e3a5f` |
| Accento oro | `#b8860b` |
| Sfondo pagina | `#f1f5f9` |
| Superficie/card | `#ffffff` |
| Bordo | `#e2e8f0` |
| Testo | `#0f172a` |
| Testo secondario | `#64748b` |
| Successo | `#15803d` |
| Avviso | `#b45309` |
| Errore | `#b91c1c` |
| Informazione | `#1d4ed8` |

- Font: stack di sistema definito in `FONT.family`.
- Numeri, importi e identificativi: `FONT.mono` quando l'allineamento aiuta il
  confronto.
- Spaziature: `4, 8, 12, 16, 20, 24, 32 px` (`SPACING`).
- Raggi: `6–14 px` per controlli e contenitori; pill solo per badge/stati.
- Ombre: usare esclusivamente `SHADOWS`, con tinta navy.

### Struttura delle pagine

- Usare `PageLayout`/`PageHeader` e i componenti condivisi già presenti.
- Mostrare prima riepilogo e anomalie realmente azionabili, poi filtri, poi
  dati.
- Raggruppare i movimenti per giornata quando la sequenza temporale conta.
- Un alert numerico deve aprire sempre l'elenco dei record che lo compongono.
- Evitare pulsanti diagnostici all'utente finale: deduplicazione, import e
  collegamenti certi devono essere idempotenti e automatici.
- La navigazione tra fattura, documento, pagamento e registrazione deve
  mantenere l'ID operazione canonico e offrire link bidirezionali.

### Stati e semantica

| Stato | Colore | Regola |
|---|---|---|
| Riconciliato/pagato verificato | verde | Esiste una prova collegata e identificabile. |
| Atteso | blu | Registrazione prevista, non ancora riscontrata. |
| Da verificare | arancio | Mancano dati o vi sono più candidati. |
| Errore | rosso | Il flusso non può proseguire senza correzione. |
| Informativo | grigio/blu | Non richiede un'azione immediata. |

Gli stati di processo sono obbligatoriamente distinti. `ATTESO`,
`DA_VERIFICARE`, `IN_ELABORAZIONE` ed `ERRORE` sono aperti; `SODDISFATTO`,
`NON_APPLICABILE` e `SUPERATO` sono terminali positivi. La UI non mostra un
processo come chiuso finché una sua attesa obbligatoria è aperta.

Non usare il colore come unica informazione: ogni badge deve avere testo
esplicito. `Attesa quietanza` è lo stato documentale corretto per i verbali;
non usare `attesa fattura` come sinonimo.

### Tabelle, importi e date

- Date visibili: `gg-mm-aaaa`; date API: ISO `aaaa-mm-gg`.
- Importi: due decimali, separatori italiani e segno coerente con Dare/Avere.
- Mostrare sempre origine, ID operazione e collegamenti alle prove.
- Non fondere righe diverse solo perché hanno stesso importo.
- Le liste grandi devono avere ricerca, filtri, paginazione e stato vuoto
  esplicito.

### Modali e documenti

- Il visualizzatore deve stare sopra ogni altro dialog, con `z-index` coerente.
- Deve chiudersi con pulsante evidente, `Esc` e ritorno del focus al comando
  che lo ha aperto.
- Il contenuto non deve apparire sotto una finestra precedente né lasciare
  overlay bloccati.
- Per PDF e fatture privilegiare una vista ampia, responsiva e stampabile.

### Responsive e accessibilità

- Desktop: sfruttare la larghezza senza perdere la gerarchia visiva.
- Tablet/mobile: trasformare le tabelle dense in card leggibili e mantenere le
  azioni primarie raggiungibili.
- Tutti i controlli devono avere etichetta, focus visibile e area cliccabile
  adeguata.
- Non introdurre Tailwind o un secondo sistema di token.

### Verifica di una modifica UI

1. test Vitest interessati;
2. build Vite senza errori;
3. prova della pagina con dati, vuoto, errore e caricamento;
4. controllo modali, focus, filtri, anno globale e link bidirezionali;
5. nessuna informazione critica disponibile soltanto tramite colore.
## Logica di funzionamento

Regole operative correnti di Ceraldi ERP. Codice, test e configurazione di
produzione prevalgono sui report storici. Questa sezione è la specifica
normativa unica per la logica applicativa: ogni modifica di logica va
riflessa qui.

### Principio generale

Il gestionale trasforma documenti e fonti esterne in un grafo di fatti
consultabile:

```text
originale Drive/email/import
        ↓
documento indicizzato e deduplicato
        ↓
fatto di dominio (fattura, F24, verbale, cedolino, movimento...)
        ↓
relazioni certe tramite operation_id
        ↓
Prima Nota, riconciliazione, stato e prove
```

L'automazione esegue solo operazioni deterministiche. Se più candidati sono
plausibili, conserva il documento, mostra l'elenco e richiede una scelta.

La regola trasversale obbligatoria è `docs/REGOLA_FISSA_ATTESE.md`: il fatto
owner crea subito obblighi e attese; le evidenze future possono soltanto
soddisfarle o lasciarle aperte. Nessun processo è chiuso se una sua attesa
obbligatoria è ancora `ATTESO`, `DA_VERIFICARE`, `IN_ELABORAZIONE` o `ERRORE`.

### Archivio Supabase e originali Drive

Supabase è l'unico registro operativo di produzione. La destinazione è:

- Google Drive per documenti originali e allegati;
- `gestionale.documents` per registri strutturati e collezioni logiche;
- `gestionale.blobs` per binari deduplicati;
- relazioni tra entità tramite `operation_id` e ID specifici.

Il registro usa collezioni logiche esplicite, tra cui:

```text
Documenti                 Fatture ricevute       Fatture emesse
Fornitori                 Dipendenti             Cedolini
Estratti conto            Movimenti bancari      Prima Nota Cassa
Prima Nota Banca          Bonifici               Assegni
Corrispettivi             F24                    Quietanze F24
PayPal                    Scadenze fornitori     Relazioni
Codici tributo            Import PartenoPay      Email PartenoPay
Verbali PartenoPay
```

Sotto la radice Drive il sistema riconosce la tassonomia:

```text
REGISTRO DATI/
PARTENOPAY/
CODICI TRIBUTO/
QUIETANZE/
DICHIARAZIONI/
```

I file originali non vengono eliminati automaticamente. Nel workflow
`00 - CALDERONE`, Render sposta atomicamente il contenitore originale dopo un
esito completo: `99 - ELABORATE`, `90 - DA ELABORARE` oppure `98 - ERRORI`.
Un ZIP parziale resta in `01 - IN ARRIVO`. L'indice conserva Drive ID,
percorso, origine, hash e data di acquisizione.

#### Stato dell'archivio

`render.yaml` imposta `DATA_BACKEND=supabase`. Il runtime verifica il catalogo
all'avvio ma non copia i documenti nella RAM: ogni lettura ricarica la singola
collezione richiesta e ogni scrittura è confermata dall'RPC prima di essere
considerata riuscita. L'health check prova lettura e percorso di scrittura
remoti. Gli scheduler usano lease distribuite fuori dalle collezioni aziendali.

La migrazione dei dati storici è conclusa solo quando:

1. tutti i fogli richiesti esistono e sono accessibili;
2. la copia iniziale è completa e senza collisioni irrisolte;
3. lettura, inserimento, aggiornamento e ricerca funzionano su Supabase;
4. un confronto end-to-end dimostra equivalenza dei risultati;
5. è provata la ricostruzione completa partendo da Drive e registro;
6. produzione ha un registro esplicitamente configurato e i controlli
   post-deploy passano.

Il fallback Sheets resta disponibile soltanto per sviluppo e test.

### Identità, hash e duplicati

Ogni riga del registro contiene almeno:

- `progressivo` stabile del foglio;
- `canonical_id` del fatto;
- `operation_id` comune ai fatti collegati;
- data, anno, tipo, importo e stato;
- ID documento, fattura e movimento bancario quando presenti;
- origine, hash file, data aggiornamento e payload completo.

La chiave di deduplicazione dipende dal dominio:

- documenti: hash del contenuto più ID esterno/provenienza;
- fatture: identificativo SDI o chiave emittente-numero-data-tipo;
- movimenti bancari: ID estratto/CRO-TRN, conto, data, importo e descrizione
  normalizzata;
- PayPal/SumUp: ID transazione del gestore;
- F24/quietanze: identificativo documento, periodo, delega e hash;
- verbali: numero normalizzato, ente, targa, data/ora e hash.

Stesso importo non significa stessa operazione. Le ricorrenze legittime
(canoni, assegni, rate, bonifici periodici) restano record distinti.

L'import calcola prima la chiave. Se esiste, aggiorna provenienza o metadati;
non inserisce una seconda scrittura. Eventuali duplicati storici certi vengono
nascosti/accorpati automaticamente con audit, mentre i casi dubbi restano in
una lista visibile.

### Import documenti

Le fonti ammesse sono upload manuale, cartelle Drive configurate, email e API
dei gestori. Ogni ingest segue lo stesso contratto:

1. conserva l'originale;
2. calcola hash e identità;
3. verifica se il documento è già indicizzato;
4. estrae dati e registra la provenienza;
5. crea o aggiorna il fatto di dominio;
6. collega automaticamente solo le corrispondenze certe;
7. espone gli ambigui come candidati selezionabili;
8. restituisce un riepilogo con inseriti, aggiornati, duplicati e scartati.

Il comando di import deve sempre salvare; una modalità di sola anteprima deve
essere esplicitamente etichettata come simulazione.

### Fatture e fornitori

- Le fatture ricevute derivano dagli XML e conservano documento, fornitore,
  imponibile, IVA, totale, scadenza e metodo previsto.
- Il fornitore canonico è identificato prima dalla P.IVA/codice fiscale e poi
  da alias normalizzati; il nome da solo non crea duplicati.
- Una fattura risulta pagata solo quando esiste una prova collegata.
- Dalla pagina fatture è possibile correggere l'imputazione tra Cassa e Banca
  senza cercare manualmente la scrittura nella Prima Nota.
- Se la banca contiene un riferimento stabile (SDD, PayPal, CRO/TRN), la regola
  del fornitore può usarlo nei successivi abbinamenti.
- Un'associazione incerta presenta `Scegli fattura`; non viene salvata come
  definitiva.

### Prima Nota Cassa e Banca

Le due sezioni mostrano movimenti raggruppati per giorno, con totale della
giornata e link alle prove.

#### Versamento contanti

Un versamento genera una sola operazione logica con due lati:

```text
Prima Nota Cassa: uscita "Versamento in banca"
Prima Nota Banca: entrata attesa "Versamento da Cassa"
```

Le due righe condividono `operation_id`. Quando il movimento compare
nell'estratto conto, l'entrata attesa viene riconciliata: non viene creata una
terza registrazione. Il fatto owner è il versamento registrato in Cassa; se la
banca arriva senza quell'attesa resta `DA_VERIFICARE` e non inventa il
versamento mancante.

#### POS e SumUp

- Le vendite POS appartengono al giorno delle transazioni.
- SumUp corrente arriva automaticamente dall'API ufficiale: le transazioni
  sono deduplicate per ID, aggregate per giorno e creano il credito bancario
  atteso verso SumUp.
- Numia corrente non arriva da API: l'operatore inserisce la chiusura dei
  terminali ogni sera e quel totale crea il credito bancario atteso Numia.
- Per il pregresso Numia, gli export operativi CSV/XLSX nella cartella Drive
  dedicata sono deduplicati per ID transazione e accorpati per giorno vendita;
  il totale di ogni giorno diventa l'attesa bancaria Numia. Non sono estratti
  conto bancari.
- L'accredito bancario è un fatto successivo e separato.
- In Banca si mostra l'importo atteso finché non arriva il movimento effettivo.
- Commissioni e scostamenti restano componenti identificabili.
- L'accredito riconcilia gli attesi tramite ID del gestore e composizione del
  lotto; non sostituisce o duplica i corrispettivi.
- Numia accorpa per giorno vendita letto da `DEL gg/mm/aa` le componenti
  `AMEX`, `INTER`, `BNCMT` e `PGBNT`; commissioni, fatture gestore e spese carta
  restano escluse. Senza una sola attesa terminale la banca non crea il POS.

#### Estratto conto

Al caricamento il sistema:

1. deduplica le righe prima di scriverle;
2. importa i nuovi movimenti mantenendo la provenienza;
3. riconcilia versamenti, POS, bonifici, assegni, SDD e pagamenti certi;
4. marca pagate le fatture solo con prova coerente;
5. lascia in elenco gli abbinamenti ambigui;
6. produce un resoconto navigabile dei risultati.

La coerenza tra corrispettivi RT, chiusure POS, accrediti dei gestori e
movimenti bancari è esposta nella pagina dedicata alla Coerenza POS del
catalogo, mentre Prima Nota Cassa/Banca conserva le scritture contabili
distinte e collegate.

### PayPal, bonifici e assegni

- Una transazione PayPal mantiene il proprio ID e può collegarsi sia alla
  fattura sia al movimento bancario SDD; le tre viste condividono
  `operation_id`.
- Le regole note del beneficiario o del riferimento bancario valgono per tutti
  i movimenti futuri, ma non superano un conflitto di identità.
- I bonifici ai dipendenti prima del giorno 25 sono normalmente riferiti al
  cedolino del mese precedente; dal giorno 25 possono riferirsi al mese
  corrente. La regola propone il periodo e salva la scelta, senza inventare un
  cedolino non ancora disponibile.
- Gli assegni ricorrenti con importo uguale ma numero/data differenti non sono
  duplicati.

### Corrispettivi

ZIP e singoli file importati vengono indicizzati, deduplicati e caricati nella
Prima Nota Cassa. La data del corrispettivo determina la giornata; totale
giornaliero, contanti, elettronico e scostamenti devono essere verificabili
contro POS e accrediti.

### F24, quietanze e codici tributo

F24, quietanza e movimento bancario sono tre prove distinte:

```text
modello F24 → righe/codici tributo
quietanza   → prova documentale dell'esecuzione
banca       → prova finanziaria dell'addebito
```

La pagina F24 mostra tutti i modelli presenti in Drive/import/email, i codici
tributo, il periodo, i PDF collegati e lo stato di riconciliazione. La ricerca
per codice tributo risale all'F24 e al PDF. Un F24 non deve risultare pagato
solo perché esiste una quietanza scollegata o un movimento dello stesso
importo.

### Cedolini e personale

- Cedolini e bonifici restano archivi distinti e collegabili.
- Il periodo associato è persistente e visibile dopo il refresh.
- Descrizioni e note operative spiegano pagamenti effettuati con carta o da un
  socio quando la sola causale non basta.
- Le associazioni automatiche richiedono dipendente, periodo e importo
  compatibili; i conflitti restano manuali.

### PartenoPay, verbali, veicoli e driver

- La ricerca email usa l'intera casella (`in:anywhere`) e conserva Gmail ID,
  hash, allegati e provenienza.
- I documenti PartenoPay sono archiviati in Drive e indicizzati nei fogli
  dedicati.
- Il PDF del verbale è la fonte per numero, importo, targa, data/ora, ente,
  trasgressore e stato; l'importo non si deduce dal nome file.
- Lo stato documentale dopo il pagamento è `Attesa quietanza` finché la prova
  non è collegata.
- Targa e driver si associano automaticamente solo quando fattura/contratto e
  storico assegnazioni determinano un unico conducente alla data del verbale.
- Se il trasgressore è Ceraldi Group S.r.l. viene mostrato come tale, senza
  inventare un driver.
- Le schede veicolo vengono compilate dai dati di fatture e contratti; una
  scheda incompleta non va mostrata come veicolo operativo.
- L'assenza apparente di fatture recenti è un alert solo dopo la scansione di
  tutte le fonti configurate.

### Relazioni e navigazione

Il registro `Relazioni` descrive i collegamenti tra entità. Ogni vista deve
consentire di passare, quando disponibili, tra:

```text
documento ↔ fattura ↔ pagamento gestore ↔ movimento bancario
          ↔ Prima Nota ↔ quietanza/prova
```

Un link mostra sempre tipo, ID, data, importo e origine della destinazione.

### Fonti dati per area

Questa sezione riassume da dove il sistema prende i dati per ogni area
funzionale. Le sorgenti sono sempre le stesse: Drive, email autorizzate,
upload manuali e API dei gestori. Registri e relazioni risiedono in Sheets;
gli originali risiedono in Drive.

| Area | Fonti | Dato operativo risultante |
|---|---|---|
| Documenti | cartelle Drive configurate, email autorizzate, upload manuale, API dei gestori | documento indicizzato con hash, origine e classe dominio |
| Fatture ricevute | XML/P7M da Drive/SDI, anagrafiche fornitore, mapping alias | fattura con fornitore canonico, importo, scadenza e stato |
| Fornitori | fatture, documenti ricevuti, alias normalizzati e anagrafiche già presenti | fornitore univoco per P.IVA/codice fiscale |
| Prima Nota Cassa/Banca | fatture, corrispettivi RT, movimenti bancari, versamenti contanti, POS, cedolini, F24 | scritture distinte collegate da `operation_id` |
| Estratti conto | file banca importati, movimenti con CRO/TRN o descrizioni normalizzate | movimenti bancari deduplicati e riconciliati |
| F24 e quietanze | modelli F24, codici tributo, quietanze PDF e movimenti bancari | delega, riga tributo, quietanza e addebito restano entità separate |
| Corrispettivi e POS | XML RT, chiusure terminale, accrediti gestore, commissioni | ricavo RT e accredito POS separati, con riconciliazione finale |
| Cedolini | file paga, anagrafiche dipendenti, bonifici salario | cedolino collegato al dipendente e al periodo corretto |
| PartenoPay e verbali | email autorizzate, ZIP, verbali PDF, ricevute e storico assegnazioni veicolo | verbale collegato a targa, driver e pagamento quando univoci |
| Amministrazione e audit | configurazione, inventory, log, report storici e test | tracciabilità e verifica, non scrittura dei fatti di dominio |

La logica resta idempotente: lo stesso hash o la stessa identità canonica non
deve generare una seconda operazione. Quando l'oggetto non è certo, il sistema
espone i candidati e chiede una scelta manuale.
Modificare una relazione aggiorna tutte le viste che la leggono; non crea copie
locali scollegate.

### Alert e azioni utente

- Ogni numero di anomalie è cliccabile e apre la lista completa.
- Gli errori certi e recuperabili vengono corretti dal sistema durante
  l'import o da una migrazione controllata.
- La manutenzione tecnica non deve diventare una sequenza quotidiana di
  pulsanti.
- Gli ambigui restano visibili con motivazione e candidati.
- Nessuna associazione ambigua, pagamento, eliminazione o spostamento di
  originale avviene automaticamente.

### Accesso, audit e sicurezza

- Autenticazione e autorizzazione proteggono tutti gli endpoint riservati.
- La sessione è scorrevole e scade dopo il periodo d'inattività configurato.
- Segreti e ID privati vivono nelle variabili Render, mai nei documenti o nel
  codice.
- Import, associazioni, correzioni e migrazioni registrano autore, momento,
  origine e risultato.
- Le automazioni periodiche usano lock/lease per evitare esecuzioni concorrenti.

### Verifica end-to-end

Un flusso è completato soltanto se sono provati:

1. acquisizione dell'originale;
2. persistenza dopo refresh e riavvio;
3. deduplicazione al secondo import;
4. correttezza degli importi al centesimo;
5. visibilità in tutte le sezioni collegate;
6. link bidirezionali e stesso `operation_id`;
7. comportamento sicuro sui casi ambigui;
8. test backend, test/build frontend, CI e verifica live post-deploy.

Un HTTP 200 o una pagina che si apre non dimostrano la correttezza dei dati.

### Documenti di riferimento

- `README.md`: avvio e deploy.
- `CLAUDE.md` (questo file): unica specifica normativa corrente.
- `docs/MARKDOWN_INVENTORY.md`: stato di tutti i documenti Markdown residui.
- `memoria/INDEX.md`: indice tecnico rapido.
- `PROMPT_MASTER.md`: appendice meccanica generata dal codice.
## Regola fissa — fatti, obblighi, attese ed evidenze

Obbligatoria per ogni pagina, import, job, router e servizio di GestionaleCloud.

### Regola centrale definitiva

Quando entra un fatto validato da una fonte autorevole, il sistema crea subito
tutti gli obblighi e tutte le attese obbligatorie che quel fatto comporta. Una
prova arrivata dopo non crea retroattivamente l'attesa: può soltanto
soddisfarla, lasciarla aperta oppure segnalarla come ambigua.

```text
FONTE
  -> DOCUMENTO
  -> CLASSIFICAZIONE
  -> FATTO CANONICO
  -> OBBLIGHI
  -> EXPECTATION
  -> EVIDENZE FUTURE
  -> RICONCILIAZIONE
  -> PRIMA NOTA
  -> CONTABILITA
  -> CONTROLLO
  -> CHIUSURA
```

Ogni fatto ha un solo owner autorevole. Ogni attesa conserva tipo, owner,
`source_fact_id`, `operation_id`, stato ed evidenze collegate. Tutte le
relazioni sono bidirezionali e auditabili.

### Stati obbligatori

Stati aperti:

- `ATTESO`
- `DA_VERIFICARE`
- `IN_ELABORAZIONE`
- `ERRORE`

Stati terminali positivi:

- `SODDISFATTO`
- `NON_APPLICABILE`
- `SUPERATO`

Un processo è chiuso soltanto quando ogni sua attesa obbligatoria è in uno
stato terminale positivo. `ERRORE` non chiude il processo e non equivale a
`NON_APPLICABILE`.

### Regola di acquisizione

- successo: originale conservato, fatto indicizzato e instradato nel dominio;
- errore tecnico: originale conservato in `Errori`, stato `ERRORE` e dettaglio;
- classificazione ambigua: originale in `Da elaborare`, stato
  `DA_VERIFICARE`, candidati visibili e nessun ciclo automatico infinito;
- elaborazione completata: stato nel registro e collocazione `Elaborate` senza
  eliminare o sovrascrivere l'originale.

Upload, Drive ed email devono passare dalla stessa pipeline idempotente.

### Applicazione per dominio

- Fattura fornitore: crea debito, scadenza, metodo atteso, pagamento atteso e
  relative attese documentali/finanziarie.
- Fattura cliente: crea credito, scadenza e incasso atteso.
- Corrispettivo RT/POS: crea giornata fiscale, ricavo, IVA, quota contanti,
  chiusure Numia/SumUp, credito per gestore, accredito bancario atteso,
  commissioni attese e controlli RT-POS-banca.
- Movimento bancario/carta: è evidenza; cerca attese esistenti e non inventa
  fatture, chiusure POS, pagamenti o obblighi mancanti.
- F24: crea attese di quietanza e prova bancaria distinte.
- Cedolino: crea netto dovuto, bonifico atteso, prova bancaria e registrazione
  contabile; la regola del periodo non inventa un cedolino futuro.
- ADER/PagoPA: collega atto, avviso, ricevuta e banca come prove separate.
- Assegno/bonifico/PayPal: conserva l'identità propria e soddisfa soltanto
  debiti o attese deterministiche.
- Noleggio/verbale: collega contratto, targa e driver valido alla data; crea
  pagamento e quietanza attesi senza dedurre il driver dall'intestatario.
- Finanziamento soci: distingue ogni movimento bancario reale tramite identità,
  data e riferimento; l'importo ricorrente non è un duplicato.

### Vincoli POS non negoziabili

Non esiste una generica regola “un file POS crea l'attesa”. Le fonti owner sono
tre e devono restare riconoscibili:

1. **SumUp corrente:** l'API ufficiale acquisisce automaticamente le
   transazioni, deduplica per ID del gestore, somma il netto per giorno vendita
   e crea/aggiorna l'attesa bancaria SumUp.
2. **Numia corrente:** l'operatore inserisce ogni sera la chiusura dei
   terminali; il totale manuale del giorno crea/aggiorna l'attesa bancaria
   Numia e resta provvisorio finché non è confermato da una fonte più forte.
3. **Numia storico:** gli export operativi Numia CSV/XLSX nella cartella Drive
   dedicata vengono deduplicati per `ID Transazione`, ricostruiti e accorpati
   per giorno vendita; ogni totale giornaliero crea/aggiorna la stessa attesa
   Numia. Questi file non sono estratti conto bancari.

Ognuno dei tre fatti crea immediatamente la coppia con un solo `operation_id`:

```text
Prima Nota Cassa: uscita POS del circuito
Prima Nota Banca: credito gestore / accredito atteso
```

L'estratto conto bancario non è mai owner del fatto POS. Raggruppa le
componenti dello stesso giorno vendita letto
dalla causale `DEL gg/mm/aa` (`NUMIA-AMEX`, `NUMIA-INTER`, `NUMIA-BNCMT`,
`NUMIA-PGBNT`), ne somma l'importo al centesimo e soddisfa l'attesa esistente.
Se l'attesa manca o ce ne sono più di una, le righe bancarie restano
`DA_VERIFICARE`; la banca non crea la chiusura terminale mancante.

Commissioni, fatture del gestore e spese con carta sono fatti distinti e non
entrano nel totale dell'accredito POS.

### Criterio di accettazione

Per ogni modifica deve esistere almeno un test che dimostri:

1. il fatto autorevole crea le attese prima delle prove future;
2. il reimport non duplica né il fatto né le attese;
3. la prova certa soddisfa l'attesa e conserva gli ID delle evidenze;
4. prova assente, discordante o ambigua non crea dati mancanti;
5. la chiusura fallisce finché esiste un'attesa obbligatoria aperta.

### Provenienza della regola

Regola consolidata il 21/08/2026 dai materiali forniti dall'utente:

- albero JSON, SHA-256
  `BA26ED5419258C766AF130FB0460AC3AF977914E5716B5E316B1FBDDE1FF4DFE`;
- albero HTML, SHA-256
  `C2ED6696B43B7E0E37E114CD08117BEB507AC5082E2ED3EC0D5E62AB68D925CD`;
- regola centrale testuale, SHA-256
  `B641ACDC39B13D8BB183AD3D5F17B83F7A1EC8E2CCE06FC0794F9E755328979A`.

I materiali descrivono la regola; codice, test e configurazione corrente
restano l'autorità eseguibile.

## Autorità del repository

- Repository: `https://github.com/ceraldicontabilita/GestionaleCloud`.
- Checkout canonico Windows: `C:\Users\ceral\Documents\GESTIONALE CLOUD 2`.
- Branch operativo: `main`.
- Non usare repository privati non canonici, ZIP o vecchi checkout come autorità.
- Prima di intervenire confronta sempre `HEAD` con `origin/main`.
- Il worktree può contenere modifiche dell'utente: non cancellarle, non
  ripristinarle e non includerle nei commit.
- Mai `git add -A`: aggiungere solo i file pertinenti e verificati.

## Fonti di verità

1. Originali Drive e identificatori delle fonti esterne.
2. Codice, test e configurazione live correnti.
3. `PROMPT_MASTER.md` per tutte le regole normative e i divieti.
4. `page_catalog.json` e mappe generate per la superficie tecnica.

Una prova successiva non crea mai l'obbligo che dovrebbe dimostrare. Il fatto
autorevole crea subito l'attesa; la prova la soddisfa o la lascia
`DA_VERIFICARE`.

I JSON in `memoria/pagine/` e `memoria/popup/` sono mappe tecniche generate:
si aggiornano con `scripts/refresh_json_docs.py`, non a mano.

## Fornitori — regola canonica

L'anagrafica fornitori vive nella collezione logica `fornitori` del registro
(`gestionale.documents` su Supabase in produzione; foglio Sheets solo come
fallback di sviluppo). La logica applicativa non deve dipendere dal supporto
fisico.

### Identità

Ordine di autorità:

1. partita IVA normalizzata;
2. codice fiscale normalizzato;
3. identificativo esterno verificato;
4. alias/ragione sociale normalizzati come supporto, mai come unica prova in
   caso di omonimia.

Il `canonical_id` del fornitore è stabile. Rinominare la ragione sociale non
crea una seconda anagrafica.

### Campi minimi

- progressivo del foglio;
- `canonical_id`;
- partita IVA e codice fiscale come testo;
- ragione sociale corrente;
- alias conosciuti;
- contatti e coordinate di pagamento verificate;
- metodo di pagamento previsto;
- riferimenti bancari/SDD/PayPal riconosciuti;
- stato attivo/cessato;
- origine, hash o documento fonte e data aggiornamento.

### Import e aggiornamento

Prima di inserire un fornitore, il sistema cerca l'identità fiscale e poi gli
alias. Se trova un record certo lo aggiorna e aggiunge la provenienza; non crea
un duplicato. Dati discordanti vengono mostrati come conflitto.

Le API continuano a esporre il dominio fornitori (`/api/suppliers` e router
correlati) indipendentemente dal backend selezionato.

### Relazioni contabili

- Fatture, pagamenti, documenti e movimenti bancari puntano al medesimo
  `fornitore_id` canonico.
- Un riferimento SDD o conto PayPal può diventare una regola verificata del
  fornitore.
- La corrispondenza per importo da sola non è sufficiente.
- Se più fatture sono compatibili, mostrare `Scegli fattura`.
- Una fusione di duplicati mantiene alias, ID precedenti, provenienza e audit.

### Migrazione

Eventuali riferimenti storici a legacy DB o a Sheets sono conservati solo come
contesto. La destinazione corrente è la collezione `fornitori` in
`gestionale.documents` (Supabase, `DATA_BACKEND=supabase`): conteggi, identità
fiscale, relazioni e capacità di ricostruzione vanno provati sul backend live.
Sheets resta solo fallback di sviluppo.

## Mappa dei moduli

Mappa narrativa del repository canonico. Per l'elenco meccanico dei router e
degli endpoint usare `memoria/MAPPA_ROUTER.md`, `memoria/MAPPA_ENDPOINT_COMPLETA.md` e
`memoria/ENDPOINT_CLASSIFICAZIONE_FINALE.md`, rigenerati dagli script in `scripts/`.

Non esiste più una mappa delle collezioni come documento operativo: in
produzione il contratto dati è Supabase (`gestionale.documents` +
`gestionale.blobs`, adattatore `app/services/supabase_runtime_database.py`);
il registro Sheets (`app/services/google_sheets_ledger.py`) resta solo come
fallback di sviluppo.

### Albero applicativo

```text
GestionaleCloud
├── Dashboard
├── Documenti
│   ├── Import manuale
│   ├── Drive e indice documentale
│   ├── Email/Gmail
│   └── Elaborazioni e anomalie
├── Fatture
│   ├── Ricevute/emesse
│   ├── Fornitori
│   ├── Scadenze e pagamenti
│   └── Documenti e associazioni
├── Prima Nota
│   ├── Cassa
│   ├── Banca
│   ├── Corrispettivi/POS/SumUp
│   └── Pulizia e controllo coerenza
├── Riconciliazione
│   ├── Estratti conto
│   ├── Bonifici e assegni
│   ├── PayPal
│   ├── F24/quietanze
│   └── Registro relazioni
├── Fisco e contabilità
│   ├── IVA, ritenute e calendario fiscale
│   ├── Libro giornale/mastro
│   ├── Bilancio, cespiti e chiusura
│   └── Dichiarazioni e codici tributo
├── Personale
│   ├── Dipendenti
│   ├── Cedolini
│   └── Associazione bonifici/periodi
├── Flotta e PartenoPay
│   ├── Veicoli e contratti
│   ├── Targa ↔ driver
│   ├── Verbali e quietanze
│   └── Riepilogo costi
└── Amministrazione
    ├── Utenti e sicurezza
    ├── Configurazione Drive/Sheets
    ├── Integrazioni e scheduler
    └── Audit e diagnostica
```

### Backend

```text
app/
├── main.py                         bootstrap FastAPI
├── config.py                       configurazione ambiente
├── database.py                     selezione runtime dati
├── routers/                        API per dominio
├── services/                       logica, import, matching e integrazioni
│   ├── supabase_runtime_database.py  adapter registro Supabase (produzione)
│   └── google_sheets_ledger.py       contratto registro Sheets (fallback dev)
├── models/                         modelli dati
└── middleware/                     sessione, sicurezza e osservabilità
```

I router non devono conoscere il supporto fisico. Accedono all'interfaccia del
database e ai servizi di dominio; nuovi flussi persistenti devono funzionare con
`DATA_BACKEND=supabase` in produzione (Sheets resta un fallback di sviluppo,
`SHEETS_REGISTRY_NAME=GestionaleCloud`).

### Frontend

```text
frontend/src/
├── App.jsx
├── components/
├── hooks/
├── lib/
└── pages/
```

Il catalogo delle schermate è `page_catalog.json`. Il design system è descritto
in `DESIGN.md` e implementato in `frontend/src/lib/utils.js`.

### Registro Supabase e originali Drive

In produzione il registro è `gestionale.documents` (una collezione logica per
entità, stesso schema di campi: progressivo, identità, relazione, provenienza,
hash e payload) + `gestionale.blobs` per i binari deduplicati. Google Drive resta
l'archivio degli originali documentali. Le cartelle Drive canoniche sono:

```text
REGISTRO DATI
PARTENOPAY
CODICI TRIBUTO
QUIETANZE
DICHIARAZIONI
```

L'elenco delle collezioni e la loro corrispondenza col dominio sono versionati
nel codice, non duplicati in una mappa manuale soggetta a divergenza.

### Flussi trasversali

#### Import

`fonte → hash/ID → deduplica → estrazione → fatto → relazioni → riepilogo`

#### Riconciliazione

`documento/fattura ↔ gestore pagamento ↔ banca ↔ Prima Nota ↔ prova`

#### Ambiguità

`più candidati → nessun collegamento definitivo → lista + scelta manuale`

#### Pubblicazione

`test → diff/staging mirato → main → CI → deploy Render → verifica live`

### Fonti di dettaglio

- API: mappe generate in `memoria/`.
- Regole di dominio, prodotto e architettura: le altre sezioni di questo
  documento (CLAUDE.md).
- Stato dei documenti Markdown residui: `docs/MARKDOWN_INVENTORY.md`.

## Cedolini: regola del netto pagabile

```text
Correggi e rendi verificabile l'intero flusso cedolini di GestionaleCloud usando
Google Drive come archivio canonico dei PDF e la Prima Nota salari
(`/api/prima-nota-salari`) come vista contabile dei soli importi dimostrati.
(La pagina `/salari` è stata rimossa il 03/09/2026: i cedolini si consultano
nell'app HR a `/hr`.)

============================================================
1. VERIFICA INIZIALE
============================================================

- Sincronizza il repository canonico `ceraldicontabilita/GestionaleCloud` e
  verifica `origin/main`, stato locale, test e configurazione Drive corrente.
- Preserva tutte le modifiche locali non pertinenti.
- Riusa `Documenti`, la pipeline cedolini, `prima_nota_salari` e gli indici
  Drive esistenti; non creare un archivio parallelo.
- Non usare filename, importi vicini, OCR isolato o dati aggregati come prova
  del netto del cedolino.

============================================================
2. REGOLA CANONICA PER IL NETTO
============================================================

Il netto pagabile deve provenire esclusivamente dalla cella graficamente
associata a una delle etichette canoniche del cedolino, per esempio:

- `TOTALE NETTO`;
- `NETTO DEL MESE`;
- `NETTO IN BUSTA`, se presente nel modello verificato.

La lettura deve usare posizione e struttura della pagina PDF, non soltanto
l'ordine del testo estratto.

Non confondere mai il netto con:

- `ARR. PREC.` o `ARR. ATTUALE`;
- totale competenze o totale trattenute;
- detrazioni, ritenute, imponibili, TFR o fringe benefit;
- arrotondamenti;
- un numero vicino alla parola `NETTO` ma collocato in un'altra colonna;
- un importo già presente nel nome del file.

Se la cella del netto è vuota, il valore deve restare nullo. Non sostituirlo
con zero e non scegliere il candidato numerico più vicino.

============================================================
3. STATI OBBLIGATORI
============================================================

Ogni PDF deve ricevere uno dei seguenti stati espliciti:

- `NETTO_VERIFICATO_DA_CEDOLINO`: un solo importo nella cella canonica;
- `NETTO_NON_PRESENTE_O_NON_LEGGIBILE`: cella vuota, PDF non leggibile o
  modello non riconosciuto;
- `MULTIPLE_NETS_DA_VERIFICARE`: più netti legittimi nello stesso PDF;
- `ERRORE_PARSER`: errore tecnico con dettaglio auditabile.

Soltanto `NETTO_VERIFICATO_DA_CEDOLINO` può alimentare automaticamente Salari
e la tabella dei bonifici da assegnare.

============================================================
4. NOMI FILE E INDICE DRIVE
============================================================

Per un netto verificato usa:

`Nome Dipendente - YYYY-MM - EUR 1.234,56.pdf`

Per una cella vuota o non leggibile usa:

`Nome Dipendente - YYYY-MM - NETTO NON PRESENTE.pdf`

Non rinominare un documento ambiguo con un importo non verificato.

Ricrea `INDICE_CEDOLINI_PAGA.xlsx` con le sole colonne:

`employee | source | year | month | net_amount | net_candidates | status`

Requisiti dell'indice:

- `source` deve essere un collegamento cliccabile al file Drive tramite ID
  stabile, mai un percorso locale Windows;
- `net_amount` deve essere numerico soltanto per i netti verificati;
- `net_candidates` serve esclusivamente per la revisione dei casi multipli;
- il nome del PDF non è una fonte per calcolare `net_amount`;
- rinominare il file non deve rompere il collegamento Drive.

============================================================
5. SALARI E BONIFICI DA ASSEGNARE
============================================================

Ricrea `SALARI_E_BONIFICI_DA_ASSEGNARE.xlsx` con:

1. `Indice`: tutte le righe e i relativi stati;
2. `Salari`: soltanto netti verificati, con collegamento Drive al PDF;
3. `Bonifici da assegnare`: somma dei netti verificati per dipendente, anno e
   mese, mantenendo il numero dei cedolini sorgente.

La tabella `Bonifici da assegnare` è una proposta di importo dovuto. Non è una
prova di pagamento e non deve impostare automaticamente:

- bonifico eseguito;
- movimento bancario;
- data pagamento;
- riconciliazione bancaria;
- stato pagato.

Lo stato iniziale deve restare `DA_ASSEGNARE`. Un pagamento diventa verificato
soltanto tramite una prova bancaria reale e un collegamento bidirezionale
auditabile.

============================================================
6. DEDUPLICAZIONE
============================================================

- Il duplicato documentale certo richiede uguaglianza dell'hash del PDF.
- Dipendente, mese e importo uguali non bastano a eliminare un cedolino: nello
  stesso periodo possono esistere mensilita aggiuntive, arretrati, conguagli o
  documenti distinti.
- Conserva sempre file originale, ID Drive, hash, percorso sorgente e motivo
  della decisione.
- Ogni eliminazione deve essere recuperabile e registrata; non eliminare file
  soltanto per somiglianza del nome.

============================================================
7. CONTROLLI PRIMA DELL'IMPORTAZIONE
============================================================

Prima di scrivere in produzione:

- ricontrolla visivamente almeno un campione per ogni modello grafico;
- verifica che un netto vuoto non produca alcun importo;
- verifica che `ARR. ATTUALE` e `ARR. PREC.` siano sempre esclusi;
- confronta numero PDF, righe indice, netti verificati, casi multipli e casi
  non leggibili;
- verifica tutti i collegamenti Drive;
- verifica assenza di duplicati per hash;
- esegui test automatici su layout con netto valorizzato, netto vuoto,
  simbolo valuta corrotto nel testo estratto e PDF multipagina;
- mostra conteggio, totale e impatto all'utente;
- richiedi conferma immediatamente prima di trasmettere dati retributivi
  personali al gestionale di produzione.

In caso di dubbio, blocca l'importazione e conserva il documento in revisione.
È preferibile un importo nullo dichiarato a un importo plausibile ma inventato.
```

## Policy contabile fiscale documentale

Questa policy non registra scritture definitive. Dal PDF costruisce una
`journal_proposal` con fonte, versione parser, righe in centesimi, sezione di
bilancio candidata e stato di deducibilita'. La registrazione richiede
approvazione del commercialista e la relazione bidirezionale fra documento,
obbligazione, prova di pagamento e banca.

### Regole applicate ai campioni audit

| Documento/codice | Natura | Bilancio candidato | Deducibilita' automatica |
|---|---|---|---|
| F24 modello | predisposizione | nessuna scrittura | bloccata: non prova pagamento |
| 1040 | chiusura debito ritenute | Passivo D12 | non e' un costo nuovo |
| 7085 | tassa libri sociali | CE B14 / Passivo D12 | da verificare competenza e contabilizzazione pregressa |
| 3918 IMU | tributo locale/ravvedimento | CE B14 / Passivo D12 | da verificare immobile, uso e dettaglio ravvedimento |
| 3813 IRAP | acconto | credito/debito IRAP | da verificare liquidazione e periodo |
| 1993 | interesse ravvedimento | C17 o sottoconto dedicato | da verificare |
| 8907 | sanzione IRAP | B14 separato | indeducibile salvo diversa valutazione professionale |
| 1701/1704 | credito fiscale | Attivo CII | non e' IVA ne' costo; origine/residuo obbligatori |
| 1075 | codice non validato | nessuna | bloccato fino a validazione annuale |
| Nota rettifica INPS | obbligazione | Passivo D12 e costi separati | da verificare esercizio/OIC 29 |
| Avviso PagoPA/verbale | richiesta di pagamento | nessuna finche' non definita responsabilita' | nessun pagamento provato |

Le etichette “deducibile/indeducibile” non sostituiscono il giudizio sul caso
concreto: periodo d'imposta, natura del costo, uso del bene, registrazioni
precedenti, base IRES/IRAP e documentazione possono cambiare il trattamento.
Il sistema quindi espone `DEDUCIBILE`, `INDEDUCIBILE`, `LIMITATA` o
`DA_VERIFICARE` come esito versionato, senza trasformarlo in scrittura.

### Fonti di riferimento

- [Agenzia Entrate: codice 1040](https://www1.agenziaentrate.gov.it/servizi/codici/ricerca/SezioneErario.php?CT=1040&Ord=0492&Q1=Tutte&Q2=&Q3=IRPEF&Q4=Tutte)
- [Agenzia Entrate: codice 7085](https://www1.agenziaentrate.gov.it/servizi/codici/ricerca/SezioneErario.php?CT=7085&Ord=2487&Q1=&Q2=&Q3=&Q4=Tutte)
- [Agenzia Entrate: codice 1075](https://www1.agenziaentrate.gov.it/servizi/codici/ricerca/SezioneErario.php?CT=1075&Ord=0526)
- [OIC 25 - Imposte sul reddito](https://www.fondazioneoic.eu/wp-content/uploads/2011/02/2024-03-OIC-25-Imposte-sul-reddito.pdf)

## MCP — specifica e runbook

### Specifica di produzione

### Scopo e confine architetturale

`gestionale_cloud_mcp` espone agli agenti AI tutte le aree operative del GestionaleCloud senza creare un secondo ERP.

Il server MCP:

1. non apre connessioni Drive/Sheets;
2. non interroga direttamente Drive, Gmail, PayPal o SumUp;
3. usa le API HTTP già registrate dal backend come unico confine applicativo;
4. inoltra il JWT dell'utente al backend, che continua a verificare firma, scadenza, revoca e ruolo;
5. rende disponibili strumenti specifici e, per la copertura completa, le sole operazioni `GET` dichiarate dall'OpenAPI corrente;
6. rifiuta URL arbitrari, redirect, parametri non dichiarati, export e contenuti binari;
7. non abilita scritture finché non sono soddisfatti contemporaneamente configurazione, ruolo admin, MFA e conferma esplicita.

Questo evita letture Drive/Sheets duplicate, regole contabili divergenti e bypass dei middleware già presenti.

### Regole semantiche inderogabili

- Documento, fattura, movimento bancario, assegno, cedolino, F24, quietanza, liquidazione IVA, transazione POS e payout sono entità distinte.
- L'importo da solo non costituisce mai una corrispondenza sufficiente.
- Ogni collegamento mantiene identificativi e provenienza in entrambe le direzioni.
- Il movimento bancario importato è prova finanziaria immutabile; la Prima Nota lo rappresenta ma non lo sostituisce.
- Un F24 può contenere più codici tributo: stato e residuo si determinano per riga, non soltanto sul totale del modello.
- XML RT, Numia, SumUp e PayPal sono fonti indipendenti. XML RT non attribuisce il gestore POS; payout e accrediti non sono nuovi ricavi.
- SumUp corrente proviene dall'API, Numia corrente dalla chiusura manuale serale
  e Numia storico dagli export operativi del gestore su Drive aggregati per
  giorno. L'estratto conto bancario è solo evidenza di accredito e non crea il
  fatto POS mancante.
- Cassa configurata sul fornitore porta la fattura in Cassa; Banca resta Provvisoria finché non esiste un riscontro bancario valido.
- Un risultato ambiguo resta da verificare: l'MCP propone, non inventa.

### Tool pubblicati

| Tool | Area | Effetto |
|---|---|---|
| `gestionale_status` | sistema | verifica API, identità, ruolo, MFA e catalogo |
| `gestionale_list_capabilities` | sistema | elenca tool curati, GET OpenAPI e azioni confermate |
| `gestionale_read_api` | tutte | esegue una GET OpenAPI non binaria con validazione rigorosa |
| `gestionale_search_documents` | documenti | ricerca per anno, categoria, stato e testo |
| `gestionale_search_invoices` | fatture | ricerca fatture ricevute e relativi stati |
| `gestionale_get_invoice_context` | fatture | dettaglio, storia e prove di pagamento, senza file binari |
| `gestionale_list_bank_movements` | banca | movimenti estratto conto filtrati e paginati |
| `gestionale_get_prima_nota` | contabilità | Cassa, Banca o Provvisori, senza creare righe |
| `gestionale_get_checks` | assegni | assegni e proposte di associazione |
| `gestionale_get_payment_channel` | PayPal/POS | PayPal, SumUp o coerenza POS reale |
| `gestionale_get_payroll` | paghe | Prima Nota salari per dipendente/mese/anno |
| `gestionale_get_f24_status` | F24 | modelli, righe tributo, quietanze e banca |
| `gestionale_get_vat_period` | IVA | liquidazione mensile/annuale e anomalie |
| `gestionale_get_accounting_report` | contabilità | piano conti, bilancio, audit o discrepanze |
| `gestionale_get_operational_context` | operazioni | scadenze, PagoPA, noleggi, verbali, cespiti, bonifici |
| `gestionale_prepare_action` | workflow | crea una proposta a durata limitata senza eseguirla |
| `gestionale_execute_confirmed_action` | workflow | esegue una proposta solo dopo tutti i controlli |

#### Copertura completa senza tool duplicati

`gestionale_read_api` non accetta un percorso o un URL. Accetta esclusivamente un `operationId` presente nell'OpenAPI vivo del backend. Il gateway verifica:

- metodo `GET`;
- percorso interno `/api/...`;
- nomi dei parametri path e query;
- limiti di paginazione;
- assenza di endpoint PDF, download, export, template o XML originale;
- risposta JSON entro la dimensione configurata.

Questa soluzione copre le centinaia di letture esistenti senza generare centinaia di funzioni quasi identiche.

### Modello di autorizzazione

#### Trasporto `stdio`

È destinato allo sviluppo locale e ai client desktop. Il processo legge `GESTIONALE_MCP_API_TOKEN` e lo inoltra alle API. Il token non viene scritto nei log.

#### Trasporto Streamable HTTP

Il gateway richiede:

- metadata dell'authorization server e del resource server;
- protezione DNS rebinding con allowlist di host e origin;
- JWT valido del GestionaleCloud;
- scope MCP `gestionale:read` per ogni tool;
- ruolo `admin`, MFA attiva e verificata per le mutazioni.

La verifica del bearer token viene delegata a `/api/auth/verify`, quindi include il controllo di revoca già implementato dal gestionale.

#### Mutazioni

Le modifiche sono disabilitate per impostazione predefinita. Per abilitarle serve `GESTIONALE_MCP_ALLOW_WRITES=true`.

Il flusso è sempre a due passaggi:

1. `gestionale_prepare_action` valida l'azione contro una lista chiusa e crea una proposta con hash SHA-256 e scadenza;
2. `gestionale_execute_confirmed_action` accetta soltanto la frase esatta `CONFERMO <proposal_id>`, poi ricontrolla admin e MFA.

Non sono presenti strumenti di cancellazione definitiva. Le azioni ammesse riguardano soltanto conferme o collegamenti già supportati dalle API: Provvisori, assegni, PayPal, cedolini, F24, PagoPA e fatture-banca.

### Protezione dei dati

- Log: nome tool, operation ID, nomi dei parametri, esito, durata e trace ID; mai valori, credenziali o documenti.
- Output: token, password, segreti, chiavi API, base64, contenuto PDF e XML originale sono oscurati.
- Dimensione: massimo 2 MB per risposta per impostazione predefinita.
- Liste: massimo 500 elementi per impostazione predefinita.
- Errori: nessuno stack trace o URL sensibile restituito all'agente.
- Test: soltanto risposte HTTP sintetiche; nessun fixture contiene dati aziendali reali.

### Contratto delle azioni consentite

| Action ID | Endpoint esistente | Vincolo |
|---|---|---|
| `prima_nota_confirm_pending` | `POST /api/prima-nota/provvisori/conferma` | conferma metodo |
| `prima_nota_wait_bank` | `POST /api/prima-nota/provvisori/attendi-banca` | non crea pagamento |
| `prima_nota_mark_uncertain` | `POST /api/prima-nota/provvisori/segnala-dubbio` | segnala anomalia |
| `check_confirm_proposal` | `POST /api/assegni/conferma-proposta/{proposta_id}` | proposta preesistente |
| `paypal_link_transaction` | `POST /api/paypal-statements/transazione/{transaction_id}/associa` | entità preesistenti |
| `payroll_reconcile` | `PUT /api/prima-nota-salari/salari/{record_id}/riconcilia` | cedolino/bonifico |
| `f24_reconcile` | `POST /api/f24/riconcilia` | righe tributo preservate |
| `pagopa_link_receipt` | `POST /api/pagopa/ricevute/associa-manuale` | ricevuta/verbale |
| `invoice_reconcile_bank` | `POST /api/fatture-ricevute/riconcilia-con-estratto-conto` | prova bancaria |

### Accettazione tecnica

1. Ogni endpoint curato deve esistere nell'OpenAPI corrente con il metodo atteso.
2. Le operazioni generiche non possono chiamare POST, PUT, PATCH o DELETE.
3. Path traversal, URL assoluti, header injection e parametri sconosciuti devono fallire.
4. Redirect, file, output non JSON e risposte oltre limite devono fallire.
5. Le proposte devono essere allowlistate, scadere e poter essere consumate una sola volta.
6. Scritture disabilitate, ruolo non admin o MFA non verificata devono fallire chiuso.
7. Tutti i tool devono avere annotazioni MCP corrette.
8. La suite di valutazione read-only deve contenere almeno dieci casi stabili e sintetici.

### Riferimenti

- [MCP Python SDK 2.0](https://github.com/modelcontextprotocol/python-sdk)
- [Documentazione SDK Python](https://py.sdk.modelcontextprotocol.io/)
- [MCP authorization](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization)
- [MCP tools](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)

### Runbook operativo

### Installazione isolata

L'SDK MCP 2.0 usa dipendenze ASGI più recenti di quelle del backend FastAPI 0.110. Per questo il gateway deve avere un ambiente Python separato.

PowerShell:

```powershell
python -m venv .venv-mcp
.\.venv-mcp\Scripts\python.exe -m pip install -r gestionale_mcp\requirements.txt
```

Non installare `gestionale_mcp/requirements.txt` nell'ambiente del backend in produzione.

### Configurazione minima locale

```powershell
$env:GESTIONALE_MCP_API_BASE_URL = "http://127.0.0.1:8000"
$env:GESTIONALE_MCP_API_TOKEN = "<JWT del Gestionale>"
.\.venv-mcp\Scripts\python.exe -m gestionale_mcp --transport stdio
```

Il token viene usato soltanto per le chiamate al backend e non appare nei log.

### Configurazione Streamable HTTP

```powershell
$env:GESTIONALE_MCP_API_BASE_URL = "https://impresasemplice.online"
$env:GESTIONALE_MCP_HOST = "127.0.0.1"
$env:GESTIONALE_MCP_PORT = "8765"
$env:GESTIONALE_MCP_ISSUER_URL = "https://impresasemplice.online"
$env:GESTIONALE_MCP_RESOURCE_SERVER_URL = "https://mcp.example.it"
$env:GESTIONALE_MCP_ALLOWED_HOSTS = "mcp.example.it,127.0.0.1:*"
$env:GESTIONALE_MCP_ALLOWED_ORIGINS = "https://mcp.example.it"
.\.venv-mcp\Scripts\python.exe -m gestionale_mcp --transport http
```

Esporre la porta soltanto dietro TLS e reverse proxy. Il percorso MCP è `/mcp` e il server usa risposte JSON stateless.

### Variabili

| Variabile | Default | Significato |
|---|---:|---|
| `GESTIONALE_MCP_API_BASE_URL` | `http://127.0.0.1:8000` | backend canonico |
| `GESTIONALE_MCP_API_TOKEN` | vuoto | JWT per `stdio` |
| `GESTIONALE_MCP_TIMEOUT_SECONDS` | `30` | timeout API |
| `GESTIONALE_MCP_MAX_RESPONSE_BYTES` | `2000000` | limite risposta |
| `GESTIONALE_MCP_MAX_ITEMS` | `500` | limite liste |
| `GESTIONALE_MCP_ALLOW_WRITES` | `false` | abilita il secondo passo mutativo |
| `GESTIONALE_MCP_PROPOSAL_TTL` | `900` | durata proposta in secondi |
| `GESTIONALE_MCP_ALLOWED_HOSTS` | localhost | protezione host |
| `GESTIONALE_MCP_ALLOWED_ORIGINS` | localhost | protezione origin |

### Collaudo

```powershell
.\.venv-mcp\Scripts\python.exe -m pip install -r gestionale_mcp\requirements-dev.txt
.\.venv-mcp\Scripts\python.exe -m pytest -q tests\test_mcp_gateway.py
python -m pytest -q tests\test_mcp_openapi_contract.py
```

Il test non deve richiedere legacy DB (non più supportato), Drive, Gmail, PayPal, SumUp o produzione.

La pipeline `.github/workflows/mcp-ci.yml` verifica separatamente il contratto
FastAPI e il runtime MCP. Questa separazione evita di aggiornare Starlette nel
servizio backend soltanto per soddisfare le dipendenze del gateway.

Checklist prima dell'attivazione remota:

- test MCP verdi;
- suite backend verde;
- token non presente nei file o nei log;
- HTTPS attivo;
- host/origin espliciti;
- scritture ancora disabilitate;
- `gestionale_status` mostra ruolo e MFA corretti;
- almeno le dodici valutazioni in `gestionale_mcp/evals/read_only_evals.json` verificate;
- attivazione delle scritture separata e approvata.

### Diagnostica

- `Token ... assente/scaduto/revocato`: generare una nuova sessione ERP; non copiare password nel client MCP.
- `Endpoint non disponibile`: il backend e il catalogo MCP sono disallineati; eseguire il test OpenAPI.
- `Risposta troppo grande`: usare anno, mese, stato, `limit` e `skip`/`offset`.
- `Il tool MCP non trasferisce file`: aprire il documento tramite l'interfaccia del gestionale, che applica autorizzazioni e audit dedicati.
- `Scritture MCP disabilitate`: comportamento previsto finché non è stata autorizzata l'attivazione.

## Runbook Render — Calderone

### Risultato operativo

Render legge esclusivamente `00 - CALDERONE/01 - IN ARRIVO`, confronta gli
SHA-256 con l'indice canonico Drive/Sheets, usa l'anteprima obbligatoria del
Gestionale e, dopo l'esito completo del file o ZIP, sposta il contenitore nella
cartella corretta. Non elimina originali.

| Esito complessivo | Destinazione |
|---|---|
| tutti i membri importati o duplicati esatti | `99 - ELABORATE` |
| almeno un membro richiede revisione, senza errori | `90 - DA ELABORARE` |
| almeno un errore tecnico | `98 - ERRORI` |
| ZIP parziale o limite raggiunto | resta in `01 - IN ARRIVO` |

L'errore prevale sulla revisione. Il contenitore non viene mai suddiviso: uno
ZIP viene spostato una sola volta. Ogni spostamento aggiorna nella stessa
richiesta Drive lo stato, l'ora UTC di controllo e lo SHA-256 della sorgente.

### Task Render

- `calderone_documenti_preview(max_documents)`: sola lettura, nessun invio o
  spostamento.
- `calderone_lifecycle_preflight()`: controlla cartelle e permessi senza
  scrivere.
- `calderone_documenti_ingest(confirm, max_documents)`: importa e completa
  automaticamente il lifecycle del lotto autorizzato.
- `calderone_lifecycle_reconcile(confirm_move, max_sources)`: sposta il
  pregresso già presente nell'indice senza ritrasmettere documenti.

### Protezioni

L'import richiede `confirm=true`, `ENABLE_RENDER_CANONICAL_INGEST=true`, il
segreto condiviso e `ENABLE_RENDER_DRIVE_MOVES=true`. La riconciliazione richiede
`confirm_move=true`. Le cartelle devono essere tre destinazioni distinte e
figlie dello stesso Calderone dell'inbox. Se la verifica fallisce, il file resta
in `01 - IN ARRIVO` e viene contato come `SPOSTAMENTO_FALLITO`.

### Procedura di collaudo

1. Eseguire `calderone_lifecycle_preflight` e verificare che tutte le sorgenti
   siano modificabili.
2. Eseguire un'anteprima con limite `1`.
3. Eseguire l'ingestione con conferma e limite `1`.
4. Controllare `IMPORTATO` o `DUPLICATO_*` e `SPOSTATO_DONE=1`.
5. Verificare su Drive che il file non sia più nell'inbox e sia in Elaborate.
6. Ripetere la scansione: il file non deve essere riprocessato.

## Acquisizione serale RT locale

Render non puo raggiungere `192.168.1.19`, perche e un indirizzo della rete privata del locale.
Il raccoglitore deve girare su un PC collegato alla stessa LAN e deve solo trasferire i file
originali nella cartella Drive `Corrispettivi/Da elaborare`.

Variabili locali, mai da inserire su Render:

- `RT_LOCAL_BASE_URL=http://192.168.1.19/www/dati-rt/`
- `RT_DRIVE_INBOX=C:\...\Il mio Drive\GESTIONALE\Corrispettivi\Da elaborare`
- facoltativa `RT_SYNC_STATE_FILE`, se si desidera spostare il registro degli hash

Esecuzione di prova:

```powershell
python scripts\sync_rt_to_drive.py --preview
```

Esecuzione reale:

```powershell
python scripts\sync_rt_to_drive.py
```

Lo script seleziona la cartella giornaliera piu recente, ignora gli XML `ESITO`, calcola SHA-256
e copia atomicamente solo i file nuovi. La pipeline Drive del gestionale esegue parsing e seconda
deduplica, poi sposta i documenti in `Elaborate` o `Errori`.

Per l'esecuzione ogni sera usare Utilita di pianificazione di Windows sul PC del locale. Le
credenziali Google non servono allo script: Google Drive Desktop sincronizza la cartella. legacy DB non è usato.

## Disaster recovery — archivio Supabase e originali Drive

Procedura di ripristino dell'archivio operativo di GestionaleCloud. Google
Drive conserva gli originali documentali (invariato). Il registro operativo
in produzione è **Supabase** (progetto `GestionaleCloud`, `gestionale.documents`
+ `gestionale.blobs`): questa sezione sostituisce la vecchia procedura basata su
workbook Google Sheets (superata dalla decisione del 03/09/2026, vedi cronologia
più sotto), corretta alla luce dell'incidente reale del 14/09/2026.

### Obiettivi

- ricostruire il registro Supabase senza perdere identità/relazioni;
- non modificare o perdere documenti originali su Drive;
- provare completezza, integrità e leggibilità;
- mantenere `canonical_id`/`operation_id` stabili;
- rendere ogni operazione di recupero verificabile e ripetibile.

### Componenti da proteggere

1. progetto Supabase `GestionaleCloud` (schema `gestionale`, `hr`, `lotti`, `menu`);
2. radice Drive e cartelle canoniche (originali documentali);
3. configurazione (`SUPABASE_URL`, segreto runtime, ID cartelle Drive) su Render;
4. credenziale del service account Drive e permessi sulle cartelle;
5. codice, schema e migrazioni nel repository (`supabase/migrations/`);
6. manifest di file, hash e provenienza.

Le credenziali non devono essere salvate nel repository. **Nessun agente o
sessione automatica deve avere la password Postgres**: solo l'API con il
segreto runtime, che cancella per id (regola introdotta il 14/09/2026 dopo
l'incidente; la password va ruotata se è stata usata da una sessione
automatica).

### Guardia preventiva (attiva dal 14/09/2026)

Migrazione `supabase/migrations/20260914160000_guardia_cancellazioni_massive.sql`:
l'applicazione non cancella mai con un filtro, passa sempre da
`gc_delete_documents` / `gc_delete_blobs` / `lotti_delete_*` con id espliciti.
La guardia blocca `DELETE`/`TRUNCATE` eseguiti a mano su `gestionale.documents`,
`gestionale.blobs`, `lotti.lotti_documents` e sullo schema `legacy_staging`,
indipendentemente dal numero di righe. Per una manutenzione deliberata, nella
stessa transazione: `select gestionale.consenti_cancellazione();`.

### Verifiche periodiche

- l'app legge/scrive Supabase con il ruolo previsto (`hr_app` per i grant
  minimi sulle tabelle dedicate, mai grant estesi non necessari);
- `/api/health` verifica dal vivo catalogo e RPC di scrittura;
- ogni collezione richiesta esiste ed è accessibile;
- `canonical_id`/`operation_id` sono univoci;
- i documenti referenziati esistono ancora su Drive;
- hash e dimensioni dei blob corrispondono al manifest (`gestionale.blobs`,
  chiave SHA-256, conteggio riferimenti);
- le relazioni non puntano a record mancanti;
- un import ripetuto non crea duplicati (idempotenza per `collection`+`id`).

### Ricostruzione controllata

**PITR (Point-in-Time Recovery)**: verificare che l'add-on sia acceso *prima*
che serva — l'incidente del 14/09/2026 ha mostrato che senza PITR attivo in
anticipo l'unico ripristino possibile è dal backup fisico giornaliero più
recente, con perdita di tutte le scritture successive a quel backup.

1. Bloccare temporaneamente le scritture applicative che si sospettano
   compromesse (o isolare l'incidente per finestra oraria).
2. Fotografare configurazione, `SUPABASE_URL`, ID cartelle Drive e versione
   schema senza esportare segreti nei log.
3. **Mai un restore in place**: dal pannello Supabase, "Restore to new
   project" su un backup fisico precedente l'incidente, verso un progetto di
   recupero separato. Un restore in place riporterebbe indietro anche
   eventuali fusioni di schema o migrazioni fatte dopo il punto di ripristino.
4. Nel progetto di recupero, confrontare conteggi per collezione contro lo
   stato corrente: le collezioni realmente svuotate dall'incidente hanno un
   conteggio inferiore lì rispetto a prima dell'incidente; le collezioni già
   vuote in origine (funzionalità mai popolata, non incidente) hanno lo stesso
   conteggio (zero) anche nel backup — non vanno trattate come dati persi.
5. Reinserire solo gli id realmente mancanti con `gc_upsert_documents`
   (idempotente per `collection`+`id`): mai una copia bulk indiscriminata.
6. Ricostruire le relazioni soltanto dopo la presenza di entrambe le entità.
7. Eseguire conteggi e confronti per collezione, anno, importo e stato.
8. Verificare i flussi end-to-end e solo dopo dichiarare chiuso l'incidente.
9. Eliminare il progetto Supabase di recupero temporaneo una volta concluso
   (ha un costo mensile proprio) da Project Settings → General → Delete
   project (non disponibile via MCP, richiede tier free e azione manuale).

### Criteri di accettazione

- nessun originale Drive mancante o illeggibile;
- zero collisioni non spiegate di `canonical_id`/`operation_id`;
- conteggi per collezione uguali alla fonte verificata (distinguendo
  esplicitamente "svuotata dall'incidente" da "mai popolata");
- somme monetarie uguali al centesimo;
- link documento-fattura-pagamento-banca-Prima Nota navigabili;
- test di creazione, modifica, ricerca e deduplicazione riusciti;
- report firmato con data, punto di ripristino usato e responsabile del controllo.

### Rollback

Se la verifica fallisce, lasciare invariati gli originali Drive e il progetto
Supabase di produzione; il progetto di recupero resta la sola area di lavoro
finché il nuovo stato non supera tutti i criteri. Non eliminare registri o
progetti di recupero finché la verifica non è conclusa.

### Sheets: solo fallback di sviluppo

Il fallback `DATA_BACKEND=sheets` resta disponibile per sviluppo e test, non
per il recupero di produzione: un workbook Sheets non riceve le scritture
reali dal 03/09/2026 in poi e non è quindi una fonte di ripristino valida per
i dati recenti. legacy DB è stato rimosso come backend supportato e non va
usato in nessuna procedura di recupero.

## Archivio dati: stato reale e destinazione

### Decisione 03/09/2026 (titolare): Supabase è l'archivio unico

- Il titolare ha deciso di fondere le app del gruppo (AppDipendenti, Menu,
  Lotti) dentro GestionaleCloud e di usare **Supabase** (progetto
  `GestionaleCloud`, tabella `gestionale.documents` + `gestionale.blobs`)
  come unico archivio: `render.yaml` imposta `DATA_BACKEND=supabase`.
- Il runtime Sheets resta nel codice solo come fallback di sviluppo; la
  sezione "Destinazione Drive-only" qui sotto descrive l'assetto precedente
  ed è superata per la persistenza dei dati (Drive resta la fonte degli
  originali documentali, non il database).
- I PDF del modulo HR (cedolini, bonifici, documenti: ~500 MB in base64 nel
  vecchio database, di cui ~800 copie duplicate) NON vengono idratati in
  memoria: vivono in `gestionale.blobs` con chiave = SHA-256 del contenuto e
  conteggio dei riferimenti (un PDF identico citato da più documenti occupa
  spazio una volta sola; sparisce solo all'ultimo riferimento). L'adattatore
  `app/hr/db_adapter.py` li carica solo su richiesta.
- **[15/09/2026]** `app/services/supabase_runtime_database.py` non idrata più
  le collezioni nella RAM del processo: il bootstrap legge soltanto il
  catalogo e ogni operazione rilegge da Supabase la collezione richiesta.
  Le scritture sono immediate anche dentro `batch_writes`; un errore RPC
  ripristina lo snapshot locale di lavoro e non lascia dati fantasma. `/api/health`
  verifica dal vivo catalogo e RPC di scrittura. Gli scheduler acquisiscono
  una lease distribuita in `gestionale.runtime_scheduler_leases`; il lock
  locale resta soltanto per il fallback Sheets di sviluppo.

### 14/09/2026 — cancellazione di massa e guardia permanente

**Incidente.** Fra le 00:44 e le 00:54 UTC, col ruolo `postgres` (SQL diretto,
non l'applicazione), è stata eseguita quattro volte
`delete from gestionale.documents where collection not like 'menu%'`:
**53.172 righe cancellate**, le collezioni popolate scese da **83 a 5**. Il
re-import successivo ne ha ricostruite 21. Restano a zero le scritture che
nessuna fonte esterna sa ricostruire: `assegni`, `cespiti`, `f24_models`,
`f24_unificato`, `quietanze_f24`, `scadenzario`, `scadenziario_fornitori`,
`riconciliazioni`, `riconciliazioni_match`, `partite_aperte`,
`movimenti_contabili` (libro giornale), `piano_conti`,
`dettaglio_righe_fatture`, `prima_nota`, `prima_nota_righe`, `note_credito`,
`documents_inbox`, `magazzino`, `warehouse_inventory`, `veicoli_noleggio`,
`verbali_noleggio`, `regole_categorie`, `learned_patterns`, `settings`,
`indice_documenti`. **Vanno recuperate da un restore del backup** (PITR
attivo: WAL archiviato ogni 120 s, `failed_count` 0) fatto **verso un progetto
separato** — un restore in place riporterebbe indietro anche la fusione degli
schemi, fatta dopo le 00:44. Poi reinserimento dei soli id mancanti con
`gc_upsert_documents` (idempotente per `collection`+`id`).

**Guardia** (`supabase/migrations/20260914160000_guardia_cancellazioni_massive.sql`).
L'applicazione non cancella mai con un filtro: passa sempre da
`gc_delete_documents` / `gc_delete_blobs` / `lotti_delete_*` con gli id
espliciti. La guardia distingue quindi per **origine**, non per numero di
righe: nessun limite all'app, blocco totale di `DELETE` e `TRUNCATE` eseguiti
a mano su `gestionale.documents`, `gestionale.blobs`, `lotti.lotti_documents`
e su tutto lo schema `legacy_staging` (118 trigger, 59 tabelle). Per una
manutenzione deliberata, nella **stessa transazione**:
`select gestionale.consenti_cancellazione();`. Collaudata sui dati reali il
14/09: inserimento libero, `DELETE` a mano bloccata, percorso applicativo
invariato, `TRUNCATE` bloccato.

**Regola operativa.** Nessun agente e nessuna sessione automatica deve avere
la password Postgres: solo l'API con il segreto runtime, che cancella per id.
La password Postgres va ruotata (è stata usata da una sessione automatica).

### 14/09/2026 — protocollo-indice vivo dei documenti su Drive

- **Problema**: l'indice documentale esisteva solo come file statici (quattro
  copie su Drive: `INDICE.xlsx`, `_drive_map.json`, `INDICE_GESTIONALE.html`,
  manifest) più l'Excel letto da `app/services/drive_document_index.py`, la
  cui radice `DRIVE_DOCUMENT_INDEX_ROOT_FOLDER_ID` **non esiste più su Drive**.
  Fotografie vecchie di settimane, che non sanno di file aggiunti o tolti.
- **Soluzione**: `app/services/drive_protocollo.py` + tabella relazionale
  `gestionale.protocollo_drive` (asyncpg, NON `gestionale.documents`: 30.000
  righe di inventario non vanno idratate in memoria a ogni avvio). Il giro
  periodico (`scheduler.py`, ogni 6 ore, primo giro 8 minuti dopo l'avvio;
  bottone "Aggiorna indice adesso" nel tab Indice Drive del hub Documenti)
  **riconcilia** Drive con la tabella: file nuovo → riga nuova; cambiato →
  aggiornata; sparito → `stato='rimosso'` con la data, **mai cancellato** (è
  un protocollo: deve ricordare che il documento è esistito, con il suo hash).
  L'MD5 arriva dall'API Drive (`md5Checksum`): i duplicati certi si trovano
  senza scaricare nulla; la copia canonica è deterministica (mai in
  `90_ARCHIVIO_STORICO`, `00_DA_CLASSIFICARE` o quarantena, poi la più vecchia).
  Le impronte dei documenti già in archivio (cedolini e bonifici HR, allegati
  fattura via `gestionale.impronte_fatture()`) stanno in `protocollo_impronte`:
  ogni file Drive viene collegato al documento del gestionale **per contenuto**,
  non per nome. Duplicati → **quarantena** (`GOOGLE_DRIVE_QUARANTENA_FOLDER_ID`)
  solo su richiesta esplicita, mai la canonica, mai una cancellazione.
- Env Render: `GOOGLE_DRIVE_GESTIONALE_ROOT_FOLDER_ID` (radice da percorrere),
  `GOOGLE_DRIVE_QUARANTENA_FOLDER_ID`, `PROTOCOLLO_DRIVE_ENABLED`. Il ruolo
  Postgres dell'app è `hr_app`: ha i grant minimi sulle tre tabelle del
  protocollo, **non** legge `gestionale.documents`.
- Endpoint admin: `GET /api/documenti/drive/protocollo/{status,search,
  documento/{id},duplicati}`, `POST .../sync`, `POST .../quarantena`.
  Il tab "Documenti" dell'Indice Drive legge il protocollo; F24 e dichiarazioni
  restano sull'Excel finché non hanno una sorgente propria.
- **Trovato durante il censimento Drive (14/09)**: `03_BANCHE_E_PAGAMENTI/
  BONIFICI` è **vuoto** in tutte e tre le cartelle di stato (i bonifici
  stanno per persona in `05_PERSONALE_E_CEDOLINI/BONIFICI DIPENDENTI`);
  `03/ESTRATTI CONTO/DA ELABORARE` contiene **334 file mai lavorati** (72 MB:
  estratti conto BNL/BPM/Nexi/Worldline/PayPal/Satispay, 54 ricevute di
  bonifico finite lì per sbaglio, CSV, una fattura fornitore) e un solo file
  in ELABORATE — l'ingest estratti conto non ha mai girato su quella cartella.
  Le vecchie cartelle HR (`1XVdb…` cedolini, `1yl55…` bonifici) non esistono
  più: i default in `app/hr/services/google_drive_sa.py` puntano nel vuoto.

**Schemi dopo la fusione** (un solo progetto Supabase `GestionaleCloud`):
`gestionale` (ERP: `documents`, `blobs`), `hr` (29 tabelle `app_*`), `lotti`
(`lotti_documents`), `menu` (9 tabelle + bucket `menu-images`),
`legacy_staging` (56 tabelle, archivio CeraldiFatture con
`_migration_manifest`: hash SHA-256 e `source_count = target_count` per
tabella). Solo `menu` e `public` sono raggiungibili da `anon`/`authenticated`;
`gestionale`, `hr`, `lotti`, `legacy_staging` non lo sono.

### 14/09/2026 — Drive 05: UN fascicolo per dipendente

Prima cedolini, bonifici e certificazioni uniche della stessa persona stavano
in tre alberi paralleli (`CEDOLINI PAGA/<persona>`, `BONIFICI DIPENDENTI/
<persona>`, `CERTIFICAZIONI UNICHE/<persona>`) con elenchi di persone diversi
(50/37/22) e cartelle `VARI` che contenevano documenti veri (tutta la storia
cedolini di D'Alma Vincenzo, 100+ bonifici a fornitori, CU di 5 persone).
Struttura definitiva (autorizzata dal titolare, "sei autorizzato a creare,
eliminare le cartelle"):

```
05_PERSONALE_E_CEDOLINI/
  DIPENDENTI/                      ← id 1EfO5-9Cs-h7cIUOKoWdL_O_E1speoccY (era "CEDOLINI PAGA":
    <COGNOME NOME>/                   stesso id, la radice dell'ingest cedolini non cambia)
      DA ELABORARE | ELABORATE | ERRORI      ← cedolini (canale cedolini, profondità 2)
      BONIFICI/DA ELABORARE | ELABORATE | ERRORI  ← bonifici della persona (canale bonifico, prof. 3)
      CERTIFICAZIONI UNICHE/                  ← CU (nessun ingest)
  CERTIFICAZIONI UNICHE COLLABORATORI/  ← CU di non dipendenti (Avv. Carini ...)
  CONTRATTI DIPENDENTI/ UNILAV E PRATICHE LAVORO/ DOCUMENTI DIPENDENTI/ INPS/ INAIL/  (invariate)
  INPS/CONTENZIOSO INPS - CEDOLINI D'ALMA 2023/   ← era CEDOLINI PAGA/PER CONTENZIOSO INPS
03_BANCHE_E_PAGAMENTI/BONIFICI/DA ELABORARE | ELABORATE | ERRORI ← i bonifici NON stipendio
                                    (fornitori, consulenti, INPS...) che stavano in BONIFICI DIPENDENTI/VARI
07_CONTRATTI_E_FORNITORI/CONTRIBUTI E BANDI/FONDO NUOVE COMPETENZE/, UTENZE E ADDEBITI/BONUS UTENZE/
```

- 51 fascicoli (48 esistenti + IAZZETTA FRANCESCO, PANE GIUSEPPINA, D'ALMA
  VINCENZO creati); rinominati IACOVELLI EMANUELE→MANUELE e POSLIGUA
  OROSCO→OROZCO (fonte: cedolini). 19 fascicoli sono di ex dipendenti pre-2021
  assenti dall'anagrafica HR (hanno cedolini su Drive: vanno importati, non
  cancellati).
- Cestinate (reversibili) SOLO cartelle vuote: le tre `VARI`, le tre lifecycle
  vuote di 03/BONIFICI, `BONIFICI DIPENDENTI` (dopo lo switch env, vedi sotto).
- Env Render: `GOOGLE_DRIVE_CEDOLINI_FOLDER_ID` = `GOOGLE_DRIVE_BONIFICI_FOLDER_ID`
  = DIPENDENTI; `GOOGLE_DRIVE_BONIFICI_FOLDER_IDS` = "DIPENDENTI,03/BONIFICI"
  (1raKJxMV1YSjRdVwhuqh8kGddmWvNWHHl). Il canale `bonifico` accetta una inbox
  diretta sotto una radice dedicata o, più in profondità, solo dentro
  `BONIFICI`; con radice condivisa non crea mai una inbox legacy.
  **Attenzione**: NON puntare `GOOGLE_DRIVE_BONIFICI_FOLDER_ID` a DIPENDENTI
  con un backend precedente a questa modifica (profondità 2 senza vincolo =
  leggerebbe i cedolini come bonifici).
- Anagrafica HR da sistemare (trovato durante il lavoro): "Ceraldi Antonella"
  (senza CF, nessun cedolino) è probabilmente un refuso di "Ceraldi Antonietta";
  "Dalma Vincenzo" (nome/cognome invertiti) e "D'Alma Vincenzo" condividono lo
  stesso `dipendente_id` nei cedolini, con 48 righe = doppioni per anno/mese;
  "Stasio Salvatore" su Drive è "DI STASIO". Sankapala 14ª 2025 caricata due
  volte (stesso PDF).

### 14/09/2026 — audit E2E e integrità dati in produzione: cosa è stato corretto

Rapporto completo (399 righe, 70 finding con query e numeri) prodotto in sessione;
qui solo ciò che è stato **cambiato** e dove sta il backup (tutto reversibile):

| Cosa | Prima | Dopo | Backup |
|---|---|---|---|
| Scheduler produzione | `ENABLE_SCHEDULER=false` dal 14/09 00:52 (spento durante l'unificazione Codex): **nessun job periodico** (44 job ERP + HR) per 16 ore | riattivato con lo switch env del fascicolo Drive | — |
| Storage `menu-images` | nessuna policy su `storage.objects`: ogni upload dal ponte Lotti→Menu rifiutato | policy "menu app full access" (solo bucket menu-images, ruolo anon = chiave server) | migrazione `20260914190000` |
| PayPal `sync/incremental` | 500 (404 PayPal su finestre di secondi) | finestra minima 5 min, errore PayPal → 502 leggibile | — |
| HR `app_bonifici` | 887 righe, **239 PDF byte-identici duplicati** (€ 283.995) | 648 righe, 0 gruppi md5 duplicati | `hr.app_bonifici_duplicati_20260914` (id, doc, canonico_id) |
| HR `app_paghe_mensili` | 36 righe sul dipendente fuso "Vincenzo Dalma" (9a0e68a7) doppie di quelle di D'Alma (df37ac5a) | rimosse | `hr.app_paghe_mensili_rimosse_20260914` |
| HR `app_dipendenti` | D'Alma attivo senza CF; Antonietta Ceraldi "cessato" con cedolini fino a 07/2026; "Ceraldi Antonella" attiva senza CF/cedolini | D'Alma cessato 13/06/2024 + CF dai cedolini; Antonietta attiva; Antonella disattivata con nota (riattivare se persona diversa) | `hr.app_dipendenti_modifiche_20260914` |
| `fornitori` | BIG FOOD Srl id 229 (0 fatture) doppione di BIG FOOD SRL id 381 | rimosso | `gestionale.documents_rimossi_20260914` |
| `invoices` | 1776634697838: stesso XML della 1785273160323 ma attribuita a PIETRO CASTALDO (l'XML dice GIUSEPPE GARGIULO) | rimossa (786 fatture) | `gestionale.documents_rimossi_20260914` |
| `corrispettivi` | 181 chiusure legacy con **l'imponibile in `totale_iva`/`iva10`** (totale/1,1): la liquidazione IVA (`iva_liquidation_query.py`) sommava € 471.708 di "IVA" su gen–ago | `totale_imponibile`/`imponibile10` = totale/1,1, `totale_iva`/`iva10`/`iva_da_versare10` = totale − imponibile (**aliquota 10% presunta**, resta DA_VERIFICARE finché non arriva l'XML RT); IVA totale € 47.170,88; il frontend (#442) legge `totale_imponibile` e non applica più l'euristica | `gestionale.corrispettivi_iva_prima_20260914` |

Primo giro reale dopo lo switch (17:25 UTC): scheduler avviato, ingest Drive
fatture (975 in coda, 25 archiviate per giro), estratti conto (291 documenti
pre-2026 lasciati fermi per scelta, 39 in coda), cedolini (49 inbox = i
fascicoli, 0 nuovi), canale bonifici sul fascicolo (`VESPA VINCENZO/BONIFICI/
DA ELABORARE/...` importati), sync paghe HR (1.175 cedolini, 648 bonifici).
Il protocollo Drive è fallito al primo giro: `postgres_diretto.ENV_DSN`
leggeva prima `SUPABASE_DB_URL`, che su Render punta ancora a un progetto
Supabase **morto** (`postgres.jqguwrahxeilcikplaxi`); ora l'ordine è quello
del deposito HR (`HR_SUPABASE_DB_URL` prima). **Da fare sul pannello Render:
aggiornare o togliere `SUPABASE_DB_URL`** (l'ERP usa `SUPABASE_URL` + segreto
runtime, non la DSN).

Verificato e lasciato com'è: i 68 movimenti banca `_dupN` hanno `legacy_row_hash`
diversi dalla riga base → righe legacy distinte (es. due commissioni uguali lo
stesso giorno), non doppioni.

**Aperto (serve codice o dati che non ci sono)**: 158 fatture `riconciliata`
con movimento `riconciliato=false` e 180 righe hub senza `fattura_id` (stato
riconciliazione incoerente dopo la ricostruzione del 14/09: da rigenerare col
motore, non a mano); corrispettivi/POS senza **febbraio** e 26/01–08/03,
15–23/08 (i file, se esistono, entrano dall'ingest Drive ora che lo scheduler è
attivo); archivio bonifici HR fermo al 09/04/2026 (paghe apr–giu in attesa,
€ 45.598): serve il ponte gestionale→HR per bonifici ed estratto conto; 38
bonifici HR con `cedolino_id` legacy orfano; 119 in "bonifici da associare"
(14 con PDF già in esiti); 8 persone dei cedolini mai in anagrafica; 10
tabelle attese dall'app HR assenti (turni_config, onomastici, richieste, ...).

### 14/09/2026 — ponte gestionale→HR per i PAGAMENTI (bonifici ed estratto conto)

Un solo punto di ingresso per i pagamenti stipendio: il gestionale legge i PDF
dei bonifici (fascicolo Drive `DIPENDENTI/<persona>/BONIFICI/DA ELABORARE`,
Import documenti, upload dalla pagina salari) e gli estratti conto; l'archivio
che si vede in `/hr/dipendenti/paghe-bonifici` viene alimentato da
`app/services/hr_pagamenti_deposito.py` attraverso il database HR in-process
(stesso adattatore e stesse funzioni dell'app HR: `_indici_dipendenti`,
`_ricalcola_stato_paga`, `_e_movimento_non_stipendio` — niente copie).

- Ingressi: `bonifici_transfers` (dopo `importa_pdf_bonifico`, chiave HR
  `gc:<sha256 PDF[:24]>`, PDF allegato) e `estratto_conto_movimenti` (uscite
  "FAVORE <dipendente>", chiave `ecm:<id movimento>`, `cro` dal "RIF. …").
  Scrive `pagamenti_esiti` + `paghe_mensili` (stato ricalcolato dal motore
  unico HR) oppure la coda HR `bonifici_da_associare`.
- Regole: dipendente da CF → nome completo univoco → cognome univoco; il
  fascicolo Drive della persona vale come identità E come segnale "stipendio"
  (le causali dei PDF reali sono `AGGIUNTIVA`/`ricevuta per ordinante`); dalla
  banca serve la parola stipendio/stip/salario/acconto/saldo in causale
  OPPURE un **lotto paghe** (bonifici ad almeno 3 dipendenti diversi lo
  stesso giorno: negli estratti conto gen–apr 2026 la descrizione è solo
  `FAVORE TAIANO LUIGI - ADD.TOT`, 12 righe lo stesso giorno = acconti/saldi
  del mese), altrimenti coda — e il giro successivo riesamina le righe in
  coda "senza segnale" se il giorno è diventato un lotto (ritira la riga
  dalla coda HR); `BENEFICIARI VARI/DIVERSI` (cumulativo senza nomi, anche
  se la causale libera cita una persona: "Vincenzo ceraldi stipendi" 4.600 €
  era per più dipendenti) → coda, e il giro toglie l'esito se era stato
  attribuito a qualcuno; TFR, fatture, commissioni, fornitori mai (nemmeno in coda);
  competenza da causale/nome file, altrimenti regola del giorno 25
  (`stipendi_bonifici.competenza_bonifico_stipendio`); stesso pagamento visto
  da PDF e da banca (stesso dipendente, importo, data ±3 gg) → un solo esito,
  arricchito (cro/hash/PDF), mai duplicato; stesso hash già in HR (importer
  Drive HR `drive:`) → duplicato.
- Ogni documento sorgente riceve `hr_deposito` (`esito`, `key`,
  `dipendente_id`, `at`): il job scheduler `hr_pagamenti_deposito` (ogni 15
  min, primo giro avvio+6 min) riprende solo i documenti senza marcatore, per
  qualunque punto di inserimento. Backfill/prova a mano: `POST
  /api/prima-nota-salari/deposita-pagamenti-hr?dry_run=true` (admin).
- Rimosso il doppione HR `POST /hr/api/dipendenti-cloud/paghe/importa-bonifici-drive`
  (+ `_parse_bonifico_pdf`, bottone "📥 Importa bonifici da Drive" in Paghe e
  bonifici): leggeva la cartella Drive per conto suo, non ricorsiva, quindi con
  la radice DIPENDENTI trovava 0 file. Un solo sistema: il ponte. Il link
  "📁 Fascicoli Drive" resta (`/paghe/bonifici-drive-config`).
- Fix a latere: `document_data_saver.save_estratto_conto_to_gestionale` usava
  `hash()` di Python nell'id (cambia a ogni riavvio del processo → il controllo
  duplicati non funzionava mai fra riavvii); ora `sha1` stabile.

### 14/09/2026 — dimissioni telematiche → adempimenti; giorni di chiusura attività

- **Dimissioni** (richiesta del titolare: "quando trovi in posta un allegato del
  genere è la conferma delle dimissioni, ho 5 giorni per comunicarlo al
  consulente del lavoro"). Il gestionale riconosce già il "Modulo Recesso
  Rapporto di Lavoro" (`fiscal_domain` → `dimissioni_telematiche`, parser
  `administrative_document_parser.parse_dimissioni`, archiviato da
  `documenti._archive_non_payment_document`). Nuovo
  `app/services/dimissioni_adempimenti.py`, agganciato lì: dipendente HR per
  CF → `dimissioni{...}` + `data_cessazione_prevista` sull'anagrafica, alert HR
  `DIP_DIMISSIONI_RICEVUTE` (critico, Pannello di controllo) con la checklist
  degli adempimenti, scadenza `notifiche_scadenze` tipo `UNILAV_CESSAZIONE` alla
  data decorrenza + 5 gg. Regole: UNILAV di cessazione entro **5 giorni** dalla
  cessazione (D.Lgs. 181/2000 art. 4-bis) via consulente; revoca del lavoratore
  entro **7 giorni** dalla trasmissione (D.Lgs. 151/2015 art. 26); idempotente per
  `codice_modulo`; modulo vecchio (limite passato da >60 gg) di un cessato →
  solo archivio, niente alert. Rimosso il doppione HR `routers/dimissioni.py`
  (lettore IMAP proprio, mai usato dal frontend): l'unica posta letta è quella
  del gestionale.
- **Giorni di chiusura** (titolare: ristrutturazione dal 26/01 all'8/03/2026,
  febbraio compreso — confermato dal POS: ultima transazione 25/01, prima 09/03;
  15–23/08 ferie — non sono corrispettivi mancanti). Registro unico
  `chiusure_attivita` (`app/services/chiusure_attivita.py`): periodi confermati
  seminati dal job `chiusure_attivita` (ogni 6 h), colonne "Periodo di
  inattività da/a" del CSV AdE (`/api/corrispettivi/import-csv`: il RT le
  dichiara alla riapertura), ferie collettive nelle presenze HR (≥80% degli
  attivi in ferie e nessun corrispettivo quel giorno → chiusura `presenze_hr`),
  API `GET/POST/DELETE /api/corrispettivi/chiusure`. `iva_liquidation_query.
  corrispettivi_periodo` toglie questi giorni da `giorni_senza_corrispettivo`
  (nuovo campo `giorni_chiusura`).
- Anagrafica HR: "Ceraldi Antonella" confermata = Antonietta Ceraldi (unita:
  `merged_into`, 11 presenze spostate). Render: `SUPABASE_DB_URL` svuotata
  (puntava a un progetto morto; il codice legge prima `HR_SUPABASE_DB_URL`).
- **HR Paghe e bonifici, modifiche a mano** (titolare 14/09/2026): `PUT
  /hr/api/dipendenti-cloud/paghe/pagamento-esito/{key}` sposta un pagamento
  a un altro periodo e/o ne corregge l'importo (stessa chiave/PDF/CRO, storia
  in `modifiche_manuali`, entrambi i mesi ricalcolati da
  `_ricalcola_bonifico_periodo` = somma esiti + motore unico); `PUT
  /paghe/importo-busta` corregge l'importo della busta (`origine: manuale`,
  `importo_busta_originale`, nota) e la sincronizzazione dai cedolini non lo
  sovrascrive (`saltati_manuali`). Nella pagina: ✎ sulla cella busta, «Sposta /
  modifica» in ogni riga di bonifico dei dettagli.
- Anagrafica HR completata il 14/09 dai cedolini e da «Lista dipendenti
  Ceraldi_Group_SRL.xlsx» (Drive 12_EXCEL): 6 persone esistenti senza CF ora
  con CF/nascita/livello/periodo, 7 create (storiche, cessate), cedolini
  collegati per CF; i 16 attivi hanno IBAN/matricola/telefono/email/nascita/
  indirizzo (mancava tutto; resta senza IBAN solo Iazzetta Francesco, non in
  Excel). Backup `hr.app_dipendenti_prima_20260914b`.
- Cedolini con CF senza anagrafica HR (13 persone, elenco in chat del 14/09, TUTTE sistemate il 14/09 sera):
  Sankapala Arachchilage (2025-06→2026-02, 11 buste), De Simone Mariano,
  Stasio Salvatore, Posligua Orozco William, Iacovelli Manuele, Lubrano
  Cristian, Thalwattage Sajeewani, Giattini Ilenia, Rabukkana Kusal,
  Pellegrino Salvatore, Tramontano Giuseppe, Bettipilippuge Viraj, Mauro
  Mariano — da creare/collegare in anagrafica (decisione del titolare).

### 14/09/2026 — bonifica design (colori)

Skill `bonifica-design` applicata a tutto il repo: 128 colori freddi (blu/
indaco/viola) in 37 file delle 4 app rimappati su salvia/sabbia, anello di
focus Tailwind del Menu a salvia (`tailwind.config.js` → `ringColor.DEFAULT`),
intestazioni PDF reportlab (report, presenze HR, bilancio, contabilità,
export fatture, noleggio, email ordini Lotti) da blu/viola/navy a salvia.
Verifica: 0 occorrenze nei bundle compilati. Scansione da ripetere dopo ogni
modifica frontend: `grep -rEn "5D29C7|1E1B4B|7c3aed|8b5cf6|6366f1|4f46e5|
violet-|indigo-|bg-blue-|bg-sky-|text-blue-|border-blue-|3b82f6|2563eb|1d4ed8"`
su `frontend*/src` e sui bundle. Il test `frontend/src/components/
AvvisoBonarioF24.test.jsx` vieta i colori freddi nel suo componente.

### 14/09/2026 — Personale: l'anagrafica HR comanda, Lotti legge (regole R1-R6 del titolare)

- **R1 — un solo elenco di persone.** `app/lotti/routers/tablet_operatori.py`
  non ha piu' un'anagrafica propria: `tablet_operatori` (Lotti) e' una
  proiezione di `hr.app_dipendenti` letta in-process
  (`sincronizza_operatori_da_hr`: all'avvio, ogni 10 min dallo scheduler
  Lotti, a ogni apertura della pagina Personale, a ogni login). Operatore =
  dipendente **in forza** in HR con `lotti_operatore` != false (spunta
  «Operatore in Lotti» nella scheda HR; Iazzetta, Sankapala e Antonietta
  Ceraldi sono a false per scelta del titolare). Nome = «Cognome Nome» da
  HR; ruolo amministratore = `ruolo_app: admin`; la postazione HACCP e'
  proposta dal ruolo HR (`postazione_da_ruolo`) e resta modificabile; le
  righe Lotti senza persona HR (Viviana, Kikko, Thimira) restano nel DB con
  `attivo=false, hr_stato=non_in_hr` (lo storico firmato non si tocca);
  «Lisina» = Lesina (`ALIAS_COGNOME`). Eliminati: «Nuovi dipendenti dal
  gestionale», «Collega esistente», blocco «PIN operatori», `NOMI_DEFAULT`,
  `ADMIN_PIN_RECOVERY`, gruppo PIN condiviso Vincenzo/Valerio.
- **R2/R3 — un PIN per persona, nella scheda HR** (`app/hr/services/
  auth_dipendenti.py`): vale per il portale e per firmare in Lotti. Nuovi PIN
  = bcrypt (`pin_hash`) + impronta HMAC `pin_lookup` (segreto = chiave JWT
  HR) per trovare la persona in una query; gli SHA-256 storici restano
  validi in lettura. `trova_dipendente_per_pin` (usata dal login del tablet
  Lotti) non restituisce mai un cessato; `imposta_pin` rifiuta un PIN gia'
  usato da un altro dipendente in forza; la cessazione revoca il PIN.
  Migrazione una tantum `migra_pin_in_hr` (avvio + job): i bcrypt di Lotti
  passano nella scheda HR della stessa persona se non ne ha gia' uno; Lotti
  poi cancella ogni campo PIN (`_CAMPI_PIN_LEGACY`). R4: il PIN condiviso
  degli amministratori non viene migrato; il PIN amministratore centrale
  (`PIN_HASH_ADMIN`) apre le pagine riservate ma NON e' un'identita' di firma
  sul tablet. Nel portale HR gli admin continuano a entrare solo col PIN
  centrale (test `test_hr_admin_personale_non_aggira_pin_centrale`).
- **Anagrafica HR** (`app/hr/routers/dipendenti_cloud/__init__.py`,
  `app/hr/services/stato_rapporto.py`): UN solo stato del rapporto
  (`attivo` | `cessato` con `data_fine_rapporto`, `motivo_cessazione` fra
  dimissioni/licenziamento/fine_contratto/risoluzione_consensuale/altro,
  `riferimento_cessazione`); `stato=inattivo` con `attivo=true` non esiste
  piu' (normalizzato a cessato). `POST /dipendenti/{id}/cessa` richiede data e
  motivo (modale dell'app, niente `confirm()`), revoca il PIN e propaga
  `DIPENDENTE_CESSATO`; `POST .../riattiva` conserva `cessazioni_precedenti`.
  `PUT /dipendenti/{id}` aggiorna SOLO i campi inviati (prima riscriveva
  matricola/nascita/indirizzo a None: successo a Moscato) e ignora `stato`.
  `POST/DELETE /dipendenti/{id}/pin`. `GET /dipendenti` espone `pin_impostato`,
  `lotti_operatore`, `data_fine_rapporto`, mai il PIN. `GET /documenti` senza
  `file_data` (era il «Caricamento…» di 5-10 s a ogni apertura); `POST
  /documenti` e' multipart con file facoltativo e tipi Dimissioni/UNILAV/
  Licenziamento — un modulo di dimissioni caricato qui passa da
  `registra_dimissioni` (alert + scadenza UNILAV). `frontend_hr`: la riga si
  aggiorna in linea (`aggiornaDipendente`), niente ricarica totale; link
  diretto `?dip=<id>` dalla pagina Personale di Lotti apre la scheda.
- **Cedolini & Bonifici = unica pagina paghe** (titolare: «Buste Paga» e
  «Cedolini & Bonifici» davano numeri diversi). Eliminata `BustePagaPage`
  (riscriveva a mano `importo_busta`/`bonifico_importo` in `paghe_mensili`,
  fuori dal motore unico) con `GET/POST/DELETE /paghe`; dentro
  `PagheBonificiPage` sono passati: menu «Importa» (Libro Unico, email, Drive,
  Prima Nota, CSV banca, archivio storico), acconti in contanti
  (`PUT /paghe/acconti`, solo il campo `acconti` + ricalcolo), prima nota per
  dipendente (clic sul nome), ricerca voci, riscansione, correzione acconti,
  simulazione F24, griglia annuale. La vecchia rotta `/hr/dipendenti/buste-paga`
  apre la pagina unificata.
- **Pannello HR, buste in attesa**: «Buste da pagare» = anno corrente; le
  buste degli anni precedenti con bonifico non agganciato sono contate a parte
  (`buste_storiche_non_agganciate`, sezione a scomparsa), non sono soldi da
  erogare.
- **PEC dimissioni** (`app/services/email_full_download.py`): la busta PEC
  (`posta-certificata@…`) vale col mittente del messaggio annidato
  (`postacert.eml`); mittente builtin `dimissionitelematiche@pec.lavoro.gov.it`
  e parole chiave «recesso rapporto di lavoro/dimission/unilav»; il PDF
  `<CF>_Dimissione.pdf` va in `_archive_non_payment_document` come
  `dimissioni_telematiche` (alert HR + scadenza UNILAV) invece che in
  `documenti_non_associati`. Trovato: `mittenti_email` in produzione e'
  VUOTA (persa il 14/09), quindi la posta non scarica nulla finche' non
  viene ripopolata (i builtin rientrano da soli all'avvio).
- Dati sistemati in produzione il 14/09 sera (backup
  `hr.app_dipendenti_prima_20260914c`): Moscato Emanuele cessato 01/07/2026
  (dimissioni, modulo 20260630102348083, PEC 30/06) con matricola/nascita/
  indirizzo/assunzione 13/03/2012 ripristinati dall'Excel; Pocci Salvatore
  cessato 31/08/2026 (dimissioni, modulo 20260730155946178, PEC 30/07,
  girate al consulente il 31/07). Per nessuno dei due c'e' in Gmail l'UNILAV
  di cessazione: da verificare col consulente (Ferrantini).

### 15/09/2026 — accessibilità WCAG 2.1 AA (punti 1-4 dell'audit) e cedolini storici via hub unico

- **Modali HR** (`frontend_hr/src/App.jsx`): un solo componente `Modal`
  (`role="dialog"`, `aria-modal`, titolo in `aria-labelledby`, focus portato
  dentro all'apertura, Tab intrappolato, Esc chiude, focus restituito a chi ha
  aperto, clic sullo sfondo chiude). Sostituisce le 4 `dc-modal-overlay` e le
  6 finestre "a mano" (`position: fixed` + `dc-card`: riduzione oraria,
  configura turni, sostituzione d'emergenza, correggi periodo TFR, prima nota
  dipendente, assumi dipendente). Non aggiungere nuove modali fuori da `Modal`.
- **Etichette**: i 29 gruppi `dc-form-group` sono `<label>` che avvolgono il
  campo (`<span className="dc-label">` per il testo); Lotti Personale e
  Stampanti usano `htmlFor`/`id` per riga (`postazione-<id>`, `libretto-<id>`,
  `azienda-<campo>`, `st-<campo>-<id>`). `aria-label` dinamici sui bottoni
  ripetuti (modifica/cessa/riattiva/elimina scheda, approva/rifiuta ferie,
  ‹/› mesi e settimane, ✎ busta e periodo, elimina documento, select
  dipendente/mese/anno in «Bonifici da associare», filtri paghe).
- **Griglie da tastiera**: le celle di Presenze e Ferie contengono un
  `<button className="dc-cell-btn">` con nome accessibile «Cognome Nome,
  gg/mm: stato»; in Presenze Invio/Spazio applica il pennello alla cella
  (il trascinamento col mouse resta sul `<td>`); i badge attenuati dal
  pennello usano `.dc-dimmed` (saturazione ridotta, non opacità 0,12).
- **Focus visibile**: `:focus-visible` salvia in `App.css` HR e regola
  esplicita in `frontend_lotti/src/index.css` per `.g-input/.g-select/
  .g-textarea` e le classi Tailwind `outline-none`. Home HR (`Landing.jsx`):
  le card sono `<Link>` veri, non `<div onClick>`.
- **Cedolini storici mancanti (63 PDF, 18 persone)** trovati confrontando
  l'archivio Drive `1lh7M9…/Cedolini` con `hr.app_cedolini`: copiati con
  l'API Drive nei fascicoli `DIPENDENTI/<PERSONA>/DA ELABORARE` (hub unico
  del gestionale: ingest orario → registro `cedolini` → deposito HR), **non**
  caricati da «Carica documenti» HR (regola del titolare: un solo motore di
  import per ogni sezione). Appuhamy, Aurigemma, Vitiello e Dell'Aquila non
  hanno anagrafica HR: il deposito le crea/collega per codice fiscale solo se
  la persona esiste, quindi vanno create come storiche cessate dopo l'ingest.

### 15/09/2026 — cessazione automatica da cedolino: guardia e riallineamento con HR

- **Trovato** importando l'archivio storico (63 buste 2018-2022) dai fascicoli
  Drive: `salari_unificati_v2.processa_cedolino_v2` (e il fallback V1 in
  `cedolini_manager`) marcava cessato nella copia `dipendenti` del gestionale
  chi aveva una busta con dicitura di cessazione (TFR, «licenz.», «data
  cessazione»), senza guardare se esistono buste successive. Risultato: in
  pochi minuti Carotenuto, Capezzuto, Guarino (in forza, buste fino al
  2026-07), Dias, Liuzza, Lubrano, D'Alma, Solla ecc. risultavano cessati
  nel gestionale con date di anni fa. L'anagrafica HR non e' stata toccata.
- **Guardia** (`app/services/cessazione_da_cedolino.py::busta_successiva`):
  la cessazione letta in una busta vale solo se non esiste una busta
  successiva della stessa persona nel registro `cedolini` del gestionale o
  nel deposito HR (`app_cedolini`, per CF); altrimenti viene ignorata e
  loggata (`cessazione_storica_ignorata` nell'esito).
- **Riallineamento** (`riallinea_cessazioni_automatiche`, job scheduler
  `riallinea_cessazioni_auto` ogni 6 ore, primo giro avvio+2 min): per i
  record con `cessato_automaticamente=True` l'anagrafica HR comanda (R1): HR
  in forza → riattivato, HR cessato → data di HR. I cessati a mano non si
  toccano. Passa dall'app (store in memoria coerente), non da SQL a mano.
- `documents_inbox` del gestionale ha ~3.970 documenti da rielaborare (il
  registro `cedolini` era a 206 righe dopo l'incidente del 14/09): il giro
  orario dell'ingest li sta rilavorando; il deposito HR li deduplica per
  (CF, anno, mese, tipo).

### 15/09/2026 — censimento Supabase e integrazione dell'archivio legacy (richiesta: «fallo tu, non delegare»)

Censimento (numeri reali): `legacy_staging` completo (55 tabelle,
`source_count = target_count` + hash); `hr` 43 dipendenti / 1.317 cedolini
con PDF / 648 bonifici / 502 documenti; `lotti` 23.783 documenti in 57
collezioni; `menu` 325 prodotti + 249 immagini. **Non integrato** prima di
questo intervento: dal legacy al gestionale era passato solo il 2026
(`canonical_2026`), restavano 455 fatture 2025 (+2 del 2024) e 77 chiusure
2025; il **modulo presenze** del vecchio gestionale (lug-ago 2026: 407
timbrature, 443 turni tutti in bozza, 66 acconti per € 26.948,60, 10
liquidazioni) non era in HR (`paghe_mensili` con 0 acconti); 18 versamenti
contanti (€ 71.000) senza prima nota; 54 ordini fornitori storici assenti da
Lotti; Lotti aveva 20 fatture 2026 su 1.085.

- **Feed fatture → Lotti** (`app/routers/lotti_integration.py::_xml_of`): le
  fatture legacy tengono l'XML in `fattura_allegata`; il feed guardava solo
  `xml_raw` e Lotti le scartava come «senza XML». Ora accetta il primo campo
  che contiene una FatturaElettronica. Le 12 fatture gia' ricevute cambiano
  `source_hash` e finiscono in `conflitto_hash` nelle ricevute Lotti: sono
  gia' collegate, nessuna azione.
- **`app/services/integrazione_legacy.py`** + job scheduler
  `integrazione_legacy` (ogni 6 h, primo giro avvio+5 min), idempotente per
  `legacy_row_hash`/`legacy_id`, legge `legacy_staging` con la DSN
  dell'app (`hr_app` ha i grant sull'archivio):
  fatture e chiusure degli anni non migrati → `invoices`/`corrispettivi`
  nella stessa forma dei documenti 2026 (`fonte legacy_staging_<anno>`, IVA
  10% presunta, DA_VERIFICARE; una chiusura non entra se la giornata e' gia'
  registrata da un'altra fonte); versamenti → prima nota cassa (uscita) +
  banca (entrata) con `scrivi_movimento` (`id legacy-vers-<id>`); acconti in
  contanti e saldi in contanti delle liquidazioni → `paghe_mensili.acconti`
  di HR (13ª/14ª = mese 13/14) + `_ricalcola_stato_paga`; timbrature →
  `timbrature` (entrata/uscita in ora di Roma) + `presenze_cloud` solo dove
  il giorno non esiste gia'; anagrafica HR creata per un profilo legacy con
  movimenti, solo se ha il CF (Strazzullo, Rossi); ordini storici →
  `ordini_fornitori` di Lotti (`inviato_fornitori`, `source
  storico_gestionale_legacy`).
  Regole: dipendente per CF, poi «Cognome Nome» univoco (Lesina e Murolo
  hanno CF diversi fra legacy e HR: match per nome), altrimenti saltato e
  contato; gli acconti pagati con **bonifico** e `acconto_tfr` NON diventano
  acconti HR (il bonifico arriva dall'estratto conto); i turni legacy (tutti
  bozze) non si importano.
- Pulizia: le 584 righe `menu_*` di `gestionale.documents` (modulo Menu
  riscritto e poi eliminato il 03/09) rimosse con la guardia; backup in
  `gestionale.documents_menu_rimossi_20260915`.
- **Non fattibile da qui**: il restore PITR (`settings`, `veicoli_noleggio`,
  `fatture_emesse`, `scadenzario`, `riconciliazioni`, `f24_models`,
  `note_credito`, `dettaglio_righe_fatture`, `magazzino`, `prima_nota`,
  `regole_categorie`, `learned_patterns`, `indice_documenti` azzerate il
  14/09) si fa solo dal pannello Supabase (Database → Backups → Point in
  time, 14/09/2026 00:40 UTC): l'MCP non ha quel comando.

### 15/09/2026 — correzione: fatture e chiusure degli anni pregressi NON vanno nel gestionale

Il titolare ha corretto lo scopo dell'integrazione appena fatta: «a me
interessa l'anno 2026, solo i cedolini e gli F24 degli anni pregressi devono
essere nel gestionale». Rimossi da `app/services/integrazione_legacy.py`
(mai andati in produzione: il job non aveva ancora girato, verificato prima
di rimuoverli — zero righe con `integrato_da = integrazione_legacy_2026-09-15`
in `invoices`/`corrispettivi`) `doc_fattura_legacy`, `doc_chiusura_legacy`,
`integra_fatture`, `integra_chiusure` e i test relativi: le 455 fatture e le
77 chiusure 2025 (+2 fatture 2024) restano **solo** nell'archivio
`legacy_staging`, non entrano in `invoices`/`corrispettivi`. Il job
`integrazione_legacy` fa solo versamenti (18, tutti 2026, verificato),
presenze/acconti/timbrature in HR, ordini storici in Lotti. Cedolini
(deposito HR) e F24 (ingest Drive) restano gli unici dati storici attivi nel
gestionale, e funzionano già per conto loro indipendentemente da questo
modulo.

### 15/09/2026 — restore su progetto separato: le 13 collezioni erano già vuote prima dell'incidente

Il titolare ha attivato lui stesso "Restore to new project" dal pannello Supabase
(PITR non disponibile: l'add-on non era mai stato acceso, quindi nessun WAL
prima di oggi) sul backup fisico del 13/09/2026 04:50 UTC — l'ultimo certamente
precedente all'azzeramento delle 00:44-00:54 UTC del 14/09. Progetto di
recupero: `ampnwwusybxhevtvxeng` (org `fatture`, eu-central-1).

**Esito: nessun dato da recuperare.** Le 13 collezioni segnalate a zero
nell'audit del 14/09 (`settings`, `veicoli_noleggio`, `fatture_emesse`,
`scadenzario`, `riconciliazioni`, `f24_models`, `note_credito`,
`dettaglio_righe_fatture`, `magazzino`, `prima_nota`, `prima_nota_righe`,
`regole_categorie`, `learned_patterns`, `indice_documenti`) risultano vuote
**anche nel backup del 13/09**, un giorno intero prima dell'incidente
(confermato: i dati del backup coprono fino alle 04:47 UTC del 13/09, coerente
con l'orario dichiarato). Non erano quindi svuotate dal `delete` di quella
notte: erano già senza righe. Verificato anche nel codice attuale: `settings`,
`veicoli_noleggio`, `fatture_emesse`, `dettaglio_righe_fatture`,
`prima_nota_righe`, `scadenzario`, `regole_categorie` hanno ancora un punto di
scrittura vivo (si ripopolano da sole con l'uso, se la funzione viene
esercitata); `riconciliazioni`, `f24_models`, `note_credito`, `magazzino`,
`prima_nota`, `learned_patterns`, `indice_documenti` non hanno più NESSUN
punto di scrittura nel codice: nomi di collezione morti, non funzionalità
attive da recuperare. La frase dell'audit del 14/09 "restano a zero le
scritture che nessuna fonte esterna sa ricostruire" andava quindi corretta:
per queste 13 non è un dato perso dall'incidente, è una funzionalità che non
aveva ancora prodotto dati (o è stata sostituita da altre collezioni: es.
`riconciliazioni_match`, `warehouse_inventory`, `prima_nota_cassa/banca/
salari`, `regole_categorizzazione` coprono lo stesso bisogno e hanno righe
vere). Il progetto di recupero non serve più: da eliminare dal pannello
Supabase (Project Settings → General → Delete project) per fermare il costo
di circa 10,18 $/mese — non è pausabile da MCP (richiede tier free) e non
esiste un comando di eliminazione via MCP.

### 15/09/2026 — Cassetto Fiscale (770/IVA/IRAP/LIPE/Redditi SC) → fiscal_documents, dichiarazioni agganciate ai F24/quietanze

Richiesta del titolare: cartella Drive con l'export del Cassetto Fiscale
2005-2026, «aggancia gli importi alle quietanze con link al PDF dal
gestionale». La cartella indicata è risultata essere `10_BILANCI_
DICHIARAZIONI/DICHIARAZIONI FISCALI/DA ELABORARE` — un canale già nella forma
standard DA ELABORARE/ELABORATE/ERRORI, semplicemente non ancora agganciato a
nessun motore. Due pezzi mancanti, entrambi risolti riusando sistemi già
esistenti (nessun sistema parallelo):

- **Ingest**: nuovo canale `dichiarazione_fiscale` in
  `app/services/drive_documenti_ingest.py` (motore generico esistente, stesso
  di `dichiarazione_iva`/`cartella_esattoriale`/`avviso_bonario`), cartella
  `GOOGLE_DRIVE_DICHIARAZIONI_FISCALI_FOLDER_ID` (id non segreto, hardcoded
  come `DRIVE_FISCAL_ROOT_FOLDER_ID`), spento di default
  (`ENABLE_DRIVE_DICHIARAZIONI_FISCALI_SYNC`, da accendere via Render dopo il
  deploy). A differenza degli altri canali fiscali non passa un
  `category_hint`: la cartella mescola piu' tipi (770/IVA/IRAP/LIPE/Redditi
  SC), decide `classify_document()` dal contenuto. Filtro solo sul nome file
  (`_da_ingerire_dichiarazione_fiscale`, mai sul contenuto): scarta i singoli
  quadri componenti la dichiarazione ricomposta (`01_Frontespizio...`,
  `0N_Quadro_XX_modulo_N...` — ridondanti, lo stesso dato è già nel PDF
  intero) e i documenti finiti lì per errore (proposte assicurative, avvisi
  bonari, cartelle esattoriali/rottamazione: hanno già un proprio canale) —
  spostati comunque in ELABORATE per non ririleggerli ogni giro.
- **Vista dichiarazioni → F24/quietanze**: `GET /api/fiscal/declarations`
  (tab "Dichiarazioni" di Situazione Fiscale) leggeva il vecchio indice
  Excel/Drive (`drive_document_index.list_declarations`), la cui radice non
  esiste più su Drive dal 03/09 — restituiva sempre lista vuota con avviso.
  `app/services/declaration_registry.py::list_declaration_dossiers` (motore
  Supabase-based che incrocia `fiscal_documents` con
  `TaxPaymentQueryService`/`f24_unificato` per codice tributo + anno
  d'imposta, espone `f24_links` con quietanza e stato banca) esisteva già,
  importato ma mai richiamato da nessun endpoint: codice morto. L'endpoint
  ora chiama quella funzione: il frontend (`SituazioneFiscale.jsx`) era
  *già* pronto a renderla (branch su `item.source_kind` per il vecchio Drive
  vs `openDocument(item.id)` → `GET /api/fiscal/documents/{id}/content` per
  il nuovo, blocco `item.f24_links` già scritto) — bastava collegare i due
  pezzi. Il drill-down "Verifica campi e F24"
  (`/declarations/{id}/field-certainty`, estrazione campi + riconciliazione
  gestionale LIPE/770) resta sul vecchio motore Drive-index: è una funzione
  più ampia, già rotta allo stesso modo per la stessa causa, fuori perimetro
  di questa correzione.
- Non affrontato in questo intervento: il `INDICE.csv` e la sottocartella
  `770/` descritti nel `LEGGIMI.txt` della cartella non esistono nella
  cartella reale (solo file sciolti) — enumerazione fatta per nome file, mai
  indovinata dal contenuto.

#### Quadratura documentale 15/09/2026

- Il protocollo Drive censisce 190 file attivi nel fascicolo canonico
  `10_BILANCI_DICHIARAZIONI/DICHIARAZIONI FISCALI`: 86 PDF erano ancora in
  `DA ELABORARE`, 100 in `ELABORATE` e il registro `fiscal_documents`
  conteneva soltanto 22 dichiarazioni. Il canale va quindi tenuto abilitato in
  produzione fino all'esaurimento della coda.
- Una sola copia byte-identica era collocata nel fascicolo sbagliato: un avviso
  bonario già presente nel canale canonico `04_F24_E_TRIBUTI/AVVISI BONARI`.
  La copia è stata spostata nella quarantena recuperabile, non eliminata.
- `drive_documenti_ingest` non materializza più tutti gli hash di
  `documents_inbox` e non crea più una riga preliminare con `pdf_data` prima
  del registro fiscale. Ogni file usa lookup indicizzati SHA-256/MD5 e passa
  direttamente dall'unico writer `FiscalDocumentIngestionService`.
- Una stessa impronta incontrata in più posizioni non genera un secondo
  documento/versione: tutte le provenienze vengono conservate in
  `source_occurrences` con ID Drive, parent, percorso e hash.

### 16-17/09/2026 — collaudo funzionale E2E sul vivo e stabilità di produzione

Richiesta del titolare: collaudo dell'intera applicazione (ERP, HR, Lotti,
Menu) su dati reali via API autenticata, entità di prova "ZZZ TEST", ogni
passo fallito = bug da correggere subito. Cosa è stato trovato e cambiato
(PR #464-#469, tutte su `main`):

- **Produzione instabile (riavvii ogni ~9 min)**, tre cause distinte, tutte
  chiuse: (1) l'avvio abbandonava dopo 3 tentativi di lettura del catalogo
  Supabase sotto carico → `_MANIFEST_RETRIES = 12` con backoff (#465);
  (2) `/api/health` rispondeva 503 (o restava appeso fino allo statement
  timeout) quando la probe Supabase era lenta → Render lo interpretava come
  servizio morto e riavviava. Ora la liveness risponde **entro 2 s** anche
  con la probe appesa (`_HEALTH_PROBE_TIMEOUT`), stato `degraded` con
  `archivio_errore` invece di 503; `?strict=true` per chi vuole il 503
  (#465, #468); (3) il job "Protocollo-indice documenti Drive" (8 min dopo
  l'avvio) portava la RAM a 1,57 GB su un piano da 2 GB → **spento via env
  Render `PROTOCOLLO_DRIVE_ENABLED=false`**: da riaccendere solo dopo aver
  ridotto la memoria del giro (oggi carica l'intero inventario). Dopo i fix:
  health 200 continuo per tutta la durata del pregresso (6 min) e nei
  controlli successivi.
- **Pregresso nel libro giornale** (#464, #467): il giro ricaricava il
  giornale a ogni documento (~1,4 s l'uno) e girava dentro la richiesta
  HTTP; ora i già registrati si leggono una volta, `force=True` al motore,
  esecuzione in **background** con stato in `sistema_stato`
  (`POST /api/piano-conti/registra-pregresso`, `GET .../stato`), esito
  negativo annotato sul documento (`registrazione_contabile_esito`).
  Esito reale del 17/09: 595 fatture + 160 corrispettivi già in giornale con
  flag riallineati; 828 fatture processate → 3 registrate, 820
  "IVA detraibile non classificata", 5 importo nullo; corrispettivi 23 →
  21 "ripartizione contanti/POS non quadrata con il totale" (chiusure
  31/03-30/07/2026 da verificare), 2 importo nullo.
- **Classificazione manuale → registrazione** (#466): `PUT
  /api/invoices/{id}/classifica` ora calcola `iva_detraibile`/
  `imponibile_deducibile_ires` dal centro di costo e registra subito la
  fattura (prima la scelta manuale non sbloccava il gate IVA).
- **Fatture 2026 doppie legacy↔Drive** (#469). Le 767 fatture importate
  dall'archivio legacy il 14/09 (`source: xml_import`) avevano l'XML in
  `fattura_allegata` ma nessuna identità canonica (`invoice_key`,
  `supplier_vat`, `content_hash`): l'ingest Drive delle stesse fatture ne
  creava una seconda copia (**485 doppioni, 9 registrati due volte** nel
  giornale) e la dedup periodica non poteva né raggrupparle né provarle;
  in più 13 fatture 2025 dell'archivio storico erano entrate nel giornale
  (stato `archiviata` mancante dal filtro del pregresso). Ora
  `app/services/fatture_identita.py` ricava l'identità dall'XML con lo
  stesso parser/chiave/impronta dell'import (sha256 identico a quello
  Drive, verificato in produzione), `pulisci_duplicati_invoices` tiene la
  copia già nel giornale e **storna** la scrittura del doppione
  (`storna_registrazione_fattura`: originale marcata `stornato` +
  scrittura di storno, mai cancellata), il giro dedup ogni 30 min passa da
  `bonifica_identita_fatture`; `POST /api/invoices/bonifica-identita`
  (dry-run sincrono, reale in background) + `GET .../stato`. Delle 7
  coppie di doppioni interni a Drive, 4 hanno lo stesso hash (le risolve
  la dedup), 3 sono collisioni di identità con file diversi (restano in
  `duplicate_review_required`, decide un operatore).
- **Collaudi E2E riusciti** (dati "ZZZ TEST" creati e ripuliti): ERP
  fattura XML → classificazione → scrittura in partita doppia in
  quadratura → eliminazione; corrispettivo XML → registrazione; Lotti
  prodotto → carico → scarico oltre stock respinto → doppio tap respinto →
  bozza riordino con `richiesto_da` → pulizia; HR login/anagrafica/paghe;
  Menu pubblico e admin. F24: quadratura quietanze Drive 459 controllate,
  459 quadrate, 0 errori. PayPal: sync storico 02/2025→09/2026 a finestre
  di 30 giorni, transazioni 66 → 159 (113 uscite, 20 PagoPA).
- **Aperto, con causa nota** (non risolto in questa sessione): gli endpoint
  sincroni che ricaricano collezioni intere per ogni elemento vanno oltre
  i 5 minuti del proxy Render e cadono per statement timeout Supabase —
  `POST /api/paypal-api/riconcilia` (`_candidate_invoices` ricarica
  `invoices` per ogni transazione: 0 transazioni agganciate a fatture, 26
  a banca), `GET /api/paypal-api/account-ids-non-mappati`, `POST
  /api/admin/riallinea-pagamenti-fatture` (>170 s anche in dry-run), `POST
  /api/prima-nota-salari/deposita-cedolini-in-hr`. Stesso rimedio già
  applicato al pregresso: prefetch unico + esecuzione in background con
  stato. Banca 2026: 1.920 movimenti, 652 riconciliati, 26 agganciati a
  fatture, 1.765 senza categoria. Le 20 note di credito legacy
  (`tipo_documento` TD04) verrebbero registrate come costi dal motore, che
  non distingue il tipo documento: da trattare prima di classificarle.
  Il database Supabase (compute Micro, 1,9 GB di cui 1 GB `documents`) è
  il collo di bottiglia di tutto quanto sopra: l'adattatore rilegge intere
  collezioni con payload (XML, PDF) a ogni `find` non puntuale.
- **Cache incrementale del runtime** (PR #471, migrazione
  `20260917040000_gc_collection_versions.sql` applicata il 17/09 03:46 UTC).
  Richiesta del titolare: «il sito deve lasciare i dati scritti, non
  ricaricarli ogni volta da Supabase, altrimenti i costi aumentano». Dal
  15/09 ogni `find` non puntuale rileggeva l'intera collezione: nei log
  edge 1.400-2.300 letture complete ogni 10 minuti nei picchi. Ora
  `SupabaseTable` tiene in memoria la versione **leggera** di ogni
  collezione letta (senza i campi di `DOCUMENT_PAYLOAD_FIELDS`: XML, PDF,
  foto); prima di servirla chiede UNA firma per tutte le collezioni
  (`gc_collection_versions`: conteggio + ultimo `updated_at`) al più ogni
  15 s; firma diversa → solo i documenti modificati dopo l'ultima lettura
  (`gc_fetch_collection_since`), rilettura completa solo se il conteggio non
  torna. Le letture che vogliono il payload usano la cache per scegliere i
  documenti e li scaricano per id (`gc_fetch_documents_exact`, lotti da 500
  che si dimezzano sui timeout fino a 10 — PR #474: prima, oltre 1.000
  documenti si tornava alla lettura completa con payload, che sotto carico
  teneva il lock operativo per decine di minuti e fermava il job dedup
  fatture; un `find_one` per id con payload va dritto all'indice remoto,
  senza firma della cache e senza lock). Le scritture
  del processo aggiornano la cache dopo l'esito positivo dell'RPC. Trigger
  `documents_touch_updated_at` garantisce `updated_at` anche per scritture
  fatte fuori dall'app. Fallback automatico alla lettura completa se le RPC
  mancano o falliscono; `GC_RUNTIME_CACHE=0` la spegne. **Firma in tempo
  costante** (migrazione `20260917063000_collection_versions_table.sql`,
  applicata 06:35 UTC): la `group by` su tutta `documents` superava i 20 s
  con il disco saturo; ora `gestionale.collection_versions` (una riga per
  collezione: conteggio + ultimo `updated_at`) e' mantenuta dai trigger
  `documents_touch_updated_at` (before insert/update) e
  `documents_collection_versions` (after insert/update/delete) e
  `gc_collection_versions` la legge senza scansioni. Le letture leggere
  (`gc_fetch_collection_projected`, `_since`) restano costose lato
  database perche' `data - campi` deve comunque de-toastare il jsonb intero:
  la vera riduzione del costo Supabase arriva dalla cache (una lettura per
  collezione, poi solo delta). **Regole per chi
  scrive codice**: (1) per liste/conteggi/lookup usare sempre una
  proiezione di esclusione del payload (`metadata_projection(collection)`)
  o inclusiva senza payload: viene servita dalla cache senza RPC; (2) il
  payload si legge per id (`find_one({"id": …})`), mai con `find({})` su
  tutta la collezione; (3) `pulisci_duplicati_invoices` e
  `fatture_identita` sono già così. Attenzione alle migrazioni DDL su
  `gestionale.documents`: `create index`/`create trigger` prendono lock
  esclusivi e con le letture lunghe in corso hanno bloccato l'app per ~30 s
  (lock timeout 8 s del ruolo `authenticator`): farle a database scarico o
  con `create index concurrently`.
- **Timeout del ruolo `anon`** (migrazione `20260917030000_anon_statement_
  timeout.sql`, applicata in produzione il 17/09 02:52 UTC): PostgREST
  esegue TUTTE le RPC del runtime (`gc_*`, `lotti_*`) come ruolo `anon`, che
  su Supabase nasce con `statement_timeout = 3s`. Nei log: 272 "canceling
  statement due to statement timeout" in 17 minuti, ogni pagina fallita
  ritentata dall'app con lotti più piccoli (carico moltiplicato), e il
  `/lotti/api/health` rispondeva 500 (`select distinct collection` su 26.250
  righe oltre i 3 s a cache fredda). Ora 20 s (sotto i 60 s dei client
  HTTP); il ruolo `authenticator` resta a 8 s. Da rivedere se si cambia
  compute o si riduce il payload di `documents`.

### Stato precedente

- Il default del codice è `DATA_BACKEND=sheets`.
- legacy DB è stato rimosso come backend supportato e non va usato in produzione.
- Qualsiasi riferimento, variabile o script relativo a legacy DB è deprecato. Strumenti o script storici devono essere isolati, marcati come "legacy / solo per migrazione" e usati unicamente in procedure controllate e verificabili.
- La migrazione dei dati storici richiede confronto di conteggi e hash, ricostruzione completa e prove di scrittura; fino a verifica completa i dati storici non devono essere cancellati senza autorizzazione e checklist di cutover approvata.

### Destinazione Drive-only

La radice operativa deve contenere:

```text
REGISTRO DATI/
  Ceraldi ERP - Registro dati
PARTENOPAY/
CODICI TRIBUTO/
QUIETANZE/
DICHIARAZIONI/
```

La mappa privata delle cartelle è il foglio `_INDICE_DRIVE` del registro.
Per ogni area operativa contiene cartella canonica, `Da elaborare`,
`Elaborate`, `Errori` e nome della variabile Render. Non duplicare gli ID nei
file pubblici del repository e non reintrodurre alias Render per la stessa
cartella.

Il registro usa un foglio per archivio logico. Ogni riga conserva almeno:

- progressivo stabile del foglio;
- `canonical_id` dell'entità;
- `operation_id` per collegare fattura, pagamento, banca e Prima Nota;
- payload completo e ricostruibile;
- hash del payload e provenienza;
- data di acquisizione e versione del parser.

Regole del cutover:

1. deduplicare la sorgente per identità canonica e hash;
2. bloccare ID uguali con payload differenti;
3. copiare il dataset completo nel registro Drive;
4. confrontare conteggi unici e digest sorgente/destinazione;
5. ricostruire il runtime dai fogli e provarne la scrittura;
6. configurare esplicitamente il registro e verificare la produzione;
7. confermare che non esistano variabili o percorsi di persistenza alternativi.

La memoria del processo è soltanto una cache ricostruibile: Drive/Sheets resta
sempre la sorgente persistente.

## HR (AppDipendenti) portata pari pari — `app/hr/` + `frontend_hr/` a `/hr`

- **[03/09/2026]** I moduli riscritti `app/hr` + `frontend/src/hr` (rotte
  `/api/hr/...`, `/hr`, `/portale`, PIN unificato) sono stati **eliminati**:
  al loro posto c'è l'app AppDipendenti originale, così com'era. `app/hr/` =
  copia di `AppDipendenti/backend/app` con i soli import riscritti nel
  namespace `app.hr.*` (`app/hr/embed.py`: `hr_app`, `avvia_hr`/`arresta_hr`
  richiamati dal lifespan di `app/main.py` solo con scheduler attivo — ha un
  suo APScheduler — e `monta_frontend`). Montata in `app/main.py` a `/hr`
  PRIMA del catch-all della SPA dell'ERP: API a `/hr/api/...`
  (`/hr/api/health`, `/hr/api/auth/pin-login`, `/hr/api/dipendenti-cloud/...`).
- **Login proprio**, non quello del gestionale: tocca-il-nome + PIN personale
  per i dipendenti, "Accesso amministratore" con il PIN dell'env `HR_PIN_CODE`;
  JWT firmato con `HR_JWT_SECRET` (sessione dipendente e admin: 7 giorni,
  finché non si preme "Esci" — prima l'admin era 2 ore, cambiato il 04/09/2026
  perché `RequireRole` in `frontend_hr/src/main.jsx` controlla l'`exp` del
  JWT ad ogni cambio pagina, quindi bastava restare sull'app oltre le 2 ore
  perché la navigazione successiva rimandasse al PIN).
  Il middleware del gestionale non c'entra: `/hr/...` è fuori da `/api/`.
  I ruoli `dipendente`/`responsabile_turni` non esistono più in
  `app/utils/ruoli.py`.
- Dati: Postgres/Supabase dell'app originale via `HR_SUPABASE_DB_URL`
  (fallback `APPDIPENDENTI_DB_URL`, poi `SUPABASE_DB_URL`), tabelle `app_<nome>`
  con colonna `doc jsonb` (adattatore Mongo→Postgres `app/hr/db_supabase.py`).
  Nessun dato HR nel registro Drive/Sheets/`gestionale.documents`.
- `frontend_hr/` = copia di `AppDipendenti/frontend` (Vite, `base: '/hr/'`,
  build in `frontend_hr/dist` compilata su Render, non committata): gestione
  desktop a `/hr/`, portale mobile a `/hr/portale`. Voce "HR" (solo admin)
  nel menu Altro = link a pagina intera.

## Menu portato pari pari — `app/menu/` + `frontend_menu/` a `/menu`

- **[03/09/2026]** Il modulo riscritto `app/menu` + `frontend/src/menu`
  (rotte `/api/menu/...`, Tailwind, `/menu-banco`) è stato **eliminato**: al
  suo posto c'è l'app Menu originale. `app/menu/` = copia di `Menu/backend`
  con import nel namespace `app.menu.*` (`app/menu/embed.py`: `menu_app`,
  `avvia_menu`/`arresta_menu` no-op). `app/menu/server.py` monta da solo il
  build `frontend_menu/build` se esiste; `app/main.py` monta `menu_app` a
  `/menu` PRIMA del catch-all della SPA: API a `/menu/api/...`
  (`/menu/api/health`, `/menu/api/admin/login`).
- **Login admin proprio** username/password (`MENU_ADMIN_USERNAME`,
  `MENU_ADMIN_PASSWORD`, JWT `MENU_JWT_SECRET`), pagina `/menu/admin/login`.
- Dati nel progetto Supabase `Lotti-HACCP`, tabelle `menu_*`
  (`menu_categories`, `menu_subcategories`, `menu_products`, `menu_allergens`,
  `menu_orders`, `menu_sale`, ...) via client PostgREST `MENU_SUPABASE_URL` /
  `MENU_SUPABASE_KEY`; immagini nel bucket Storage `menu-images`.
- **Il menu vero si gestisce su Qromo** (`ceraldicaffe.qromo.it`): bottone
  "Sincronizza da Qromo" nel tab Prodotti dell'area admin →
  `POST /menu/api/admin/sync-qromo` (`app/menu/qromo_sync.py`, aggiunta
  GestionaleCloud: legge le costanti JavaScript della home Qromo, esclude le
  sottocategorie di cassa `BANCO - *`, riduce gli allergeni ai 14 UE,
  sostituisce per intero categorie/sottocategorie/prodotti; `GET
  .../sync-qromo/preview` = prova a secco). Test: `tests/test_menu_qromo_sync.py`.
- URL del menu per i clienti (QR al tavolo):
  `https://gestionalecloud.onrender.com/menu/`. `frontend_menu/` = copia di
  `Menu/frontend` (CRA, `PUBLIC_URL=/menu` e `REACT_APP_MENU_BACKEND_URL=/menu`
  in `.env.production`, tracciato apposta — **[FIX 04/09/2026]** rinominata da
  `REACT_APP_BACKEND_URL`: un env Render generico con quel nome, rimasto dal
  backend Lotti standalone, veniva letto da `process.env` al posto del valore
  del file durante la build condivisa (`build_frontends.sh`), mandando ogni
  chiamata admin del Menu a un host esterno spento — vedi la stessa nota su
  Lotti sopra, stesso bug, stesso fix; build compilata su Render). Voce "Menu"
  nel menu Altro = link a pagina intera su `/menu/admin`.
- **Prodotti da Lotti [03/09/2026, richiesta del titolare]**: ogni ricetta di
  Lotti viene replicata nel Menu con la stessa foto; il titolare sceglie se
  compare nel menu pubblico. Ponte `app/lotti/servizi/menu_bridge.py`
  (`pubblica_prodotto_nel_menu` / `rimuovi_prodotto_dal_menu`, client
  sincrono del Menu eseguito con `asyncio.to_thread`), agganciato in
  `app/lotti/routers/ricette.py` a `POST /lotti/api/ricette`, `PUT`/`PATCH`
  `/ricette/{id}`, `/prezzo-vendita`, `/reparto`, `POST /ricette/{id}/upload-foto`,
  `DELETE /ricette/{id}`; l'esito va nella risposta come `menu_sync`
  (`pubblicato` | `aggiornato` | `rimosso` | `non_configurato` senza
  `MENU_SUPABASE_URL` | `errore`) e non fa mai fallire l'endpoint Lotti.
  Campi: ricetta `menu_pubblico` (bool, default False, checkbox "Mostra nel
  menu pubblico" in `FormRicetta.jsx`; `PATCH` lo accetta) → `menu_products.
  visible`; `menu_products.origine = "lotti"`, `lotti_ref = "ricetta:<id>"`
  (chiave idempotente: update se esiste, altrimenti insert con id ≥ 1.000.000
  per non collidere con gli id Qromo). Categoria "Produzione Ceraldi" +
  sottocategoria per reparto (Pasticceria/Rosticceria/Bar/Altro), create al
  volo con `origine = "lotti"`. Prezzo `"3.50€"` da `prezzo_vendita`,
  allergeni Lotti → 14 id UE (`MAPPA_ALLERGENI_MENU`), descrizione = `descrizione`
  o `note`. Foto: byte da `foto_files` copiati nel bucket `menu-images` al
  percorso `lotti/<foto_id>.<jpg|png|webp>` (upsert), URL pubblico in `image`;
  non si ricarica se la riga punta già allo stesso `foto_id`. Il menu
  pubblico (`GET /menu/api/menu/`, `/subcategories/{id}`, `/products/{id}`,
  `/search`) esclude `visible=false`; `/admin/products/all` e il CRUD admin
  espongono/accettano `visible`. La sync Qromo cancella solo le righe con
  `origine IS NULL`: le righe di Lotti sopravvivono. Test:
  `app/lotti/tests/test_menu_bridge.py`, `tests/test_menu_public_visible.py`.

## App portate pari pari — `app/lotti/` + `frontend_lotti/`, `app/menu/` + `frontend_menu/`, `app/hr/` + `frontend_hr/`

- **[03/09/2026, decisione del titolare]** Le app del gruppo NON vanno
  ricostruite dentro il gestionale: si prende il repository originale e lo si
  porta dentro così com'è ("voglio l'app così come era"). Ogni app è un
  documento a sé: backend originale montato come sub-app FastAPI a
  `/<app>` (rotte `/<app>/api/...`, **proprio login**), frontend originale
  compilato con la propria toolchain e servito a `/<app>/` dalla stessa
  sub-app. Nessuna contaminazione di stile con il layout dell'ERP.
- **Lotti (HACCP)**: `app/lotti/` = copia di `Lotti/backend` con i soli import
  riscritti nel namespace `app.lotti.*` (`app/lotti/embed.py`: `lotti_app`,
  `avvia_lotti`/`arresta_lotti` richiamati dal lifespan di `app/main.py`
  perché Starlette non propaga lo startup alle sub-app, `monta_frontend`).
  Montata in `app/main.py` PRIMA del catch-all della SPA dell'ERP. Env
  namespaced per non collidere con quelle del gestionale:
  `LOTTI_SUPABASE_URL`, `LOTTI_SUPABASE_ANON_KEY`, `LOTTI_DB_SECRET`
  (progetto Supabase `Lotti-HACCP`, tabella `lotti_documents` + RPC
  `lotti_*`), `LOTTI_AUTH_SECRET` (fallback `AUTH_SECRET`), `LOTTI_DB_NAME`.
  Senza `LOTTI_SUPABASE_URL` l'archivio è in memoria (mongomock, non
  persistente: solo test/sviluppo). Il PIN admin di Lotti resta quello di
  Lotti. `frontend_lotti/` = copia di `Lotti/frontend` (CRA), build con
  `PUBLIC_URL=/lotti`, `REACT_APP_LOTTI_BACKEND_URL=/lotti` (`.env.production`,
  tracciato apposta — **[FIX 04/09/2026]** rinominata da `REACT_APP_BACKEND_URL`:
  un vecchio env Render generico con quel nome, rimasto dal backend Lotti
  standalone (`lotti-backend-2wwb.onrender.com`), veniva letto da `process.env`
  al posto del valore del file durante la build — e per lo stesso motivo da
  `frontend_menu` (vedi sotto, stesso nome generico, stesso fix), mandando
  ogni chiamata di entrambe le app a un host esterno spento: da fuori sembrava
  un server lento, in realtà la richiesta non arrivava mai al servizio giusto);
  le foto SAIMA sono referenziate dai dati come
  `/saima/...` e vengono servite dall'host da `frontend_lotti/build/saima`.
  Voce "HACCP Lotti" nel menu Altro (link a pagina intera). I test originali
  vivono in `app/lotti/tests` (`AUTH_SECRET=test python -m pytest app/lotti/tests`).
  La guardia `tests/test_drive_only_architecture.py` esclude `app/lotti`
  (usa l'API Mongo in memoria per progetto, non è l'archivio dell'ERP).
- **Menu e HR: fatto (03/09/2026)**, vedi le due sezioni qui sopra. I moduli
  riscritti `app/menu`, `frontend/src/menu`, `app/hr`, `frontend/src/hr`
  non esistono più (con i loro test, le pagine 67-76 di `page_catalog.json`
  e le voci `/hr`, `/portale`, `/menu*` del router React). Le guardie
  `tests/test_drive_only_architecture.py`, `tests/test_csrf_cookie_guard.py` e
  `tests/test_no_hardcoded_deprecated_collections.py` escludono `app/lotti`,
  `app/menu`, `app/hr` (codice di app esterne, non dell'ERP); i test delle
  app restano quelli originali (`app/lotti/tests`, `app/hr/tests`).
  `render.yaml` compila anche `frontend_menu` e `frontend_hr` e dichiara le
  env `LOTTI_*`, `MENU_*`, `HR_*` (`sync: false`).
- Fase successiva: consolidare i dati delle app nel progetto Supabase
  `GestionaleCloud`.

## Doppioni rimossi il 03/09/2026: HACCP nativo e pagina «Cedolini paga»

- **Ordine del titolare** («elimina bottone Tracciabilità e codice associato,
  `/salari` e `/tracciabilita`»), regola «un solo sistema per funzione».
- **HACCP nativo eliminato**: voce «Tracciabilità» della TopNav, route
  `/tracciabilita` + `frontend/src/pages/TracciabilitaHACCP.jsx`, router
  `app/routers/haccp.py` (`/api/haccp/*`), servizi
  `app/services/haccp_traceability.py` e `haccp_operations.py`, costanti
  `COLL_HACCP_*` in `app/db_collections.py`, indici `haccp_*` in
  `app/database.py`, fogli `haccp_*` di `PROMPT_MASTER.md`, i test
  `tests/test_haccp_*.py` e la pagina 66 del catalogo. Al suo posto c'è l'app
  Lotti a `/lotti`. **Resta** `app/routers/lotti_integration.py`
  (`/api/integrations/lotti/*`): è il feed fatture letto da
  `app/lotti/routers/gestionale_fatture.py`. `docs/ADR-001-HACCP-LOTTI-DRIVE-
  SHEETS.md` è conservato come documento storico.
- **Pagina «Cedolini paga» eliminata**: voce nel menu Altro, route `/salari`,
  `frontend/src/pages/CedoliniSalari.jsx` (+ test), pagina 10 del catalogo;
  in `MappaGestionale.jsx` l'area «Cedolini» apre `/hr/`. Con lei sono spariti
  i soli endpoint che esistevano per quella pagina: `GET /api/prima-nota-salari/
  salari-ricostruiti`, `GET .../export-appdipendenti/preview` e `.../download`
  (+ `app/services/appdipendenti_export.py`). **Resta tutto il resto** del
  router `/api/prima-nota-salari` (Prima Nota salari, import paghe/bonifici,
  PDF cedolino/bonifico per riga, riconcilia — usati da `primaNotaStore.js`,
  dal MCP e dai test), l'ingestione cedolini (`drive_cedolini`,
  `email_download`, `sync_prima_nota_salari_da_cedolini` in `app/main.py`),
  F24, TFR e `app/routers/employees/dipendenti.py`.
- Il catalogo canonico conta ora **64** schermate (id contigui).

## Cedolini: un solo sistema (HR)

- **[03/09/2026, decisione del titolare]** «Il gestionale scarica i dati dalla
  posta … portare i cedolini in HR; niente ponte; a cosa serve una sezione
  cedolini nel gestionale e un'altra in HR?». L'archivio cedolini che gli
  utenti vedono è **solo l'app HR** (`/hr`, tabella `public.app_cedolini`
  del Postgres HR, DSN `HR_SUPABASE_DB_URL` → fallback `APPDIPENDENTI_DB_URL`,
  `SUPABASE_DB_URL`, già dichiarate in `render.yaml`).
- Il gestionale continua a **scaricare** le buste (Drive:
  `app/services/drive_cedolini_ingest.py`; email: `app/routers/email_download.py`
  → `processa_nuovi_documenti` → `cedolini_manager` → `salari_unificati_v2`)
  e a ricavarne la **Prima Nota salari**: per questo il registro interno
  `cedolini` resta scritto, ma non ha più una pagina propria.
- **Deposito in HR**: `app/services/hr_cedolini_deposito.py::
  deposita_cedolino_in_hr(cedolino)` è richiamato, protetto da try/except,
  subito dopo OGNI scrittura di un cedolino nel gestionale
  (`salari_unificati_v2.processa_cedolino_v2`, `cedolini_manager.
  processa_cedolino_completo`, `post_download_pipeline.processa_cedolini_da_email`,
  `upload_ai_processor.process_upload_cedolino`, `ai_integration_service`,
  `document_data_saver.save_busta_paga_to_gestionale`, `email_full_download.
  smart_auto_associate`, `POST /api/dipendenti/buste-paga`, `POST
  /api/prima-nota-salari/salari/{id}/cedolino-pdf`). Scrive con asyncpg
  direttamente in `app_cedolini` (`id text` + `doc jsonb`, stessa forma
  dell'adattatore `app/hr/db_supabase.py`) senza toccare `app/hr/**`.
- Forma del documento = quella dei 1291 cedolini già in HR: `mese`/`anno`
  interi, `competenza` `"YYYY-MM"`, `tipo_cedolino` `ordinario` (il "mensile"
  del gestionale) / `tredicesima` / `quattordicesima`, `netto`, `lordo`,
  `competenze`, `trattenute`, `nome_dipendente` = `dipendente_nome`,
  `filename`/`pdf_filename`, `pdf_data` base64, `fonte` = `gestionale_cloud`,
  `parser_template` solo se è un modello noto all'HR (`zucchetti_new`,
  `zucchetti_classic`, `csc_napoli`, `teamsystem`), `giorni_lavorati`,
  `livello`; `dipendente_id`/`nome` risolti da `app_dipendenti` per codice
  fiscale (mai gli id del gestionale). Provenienza conservata in
  `gestionale_cedolino_id`, `gestionale_source`, `cedolino_dedup_key`.
- **Dedup, mai sovrascrittura**: un cedolino HR esistente con la stessa
  `cedolino_dedup_key`, oppure stesso (CF maiuscolo, anno, mese, tipo), non
  viene toccato (`esito: gia_presente`); 13ª/14ª dello stesso mese restano
  buste distinte. Senza DSN il deposito è un no-op segnalato una volta nel
  log (`hr_non_configurato`); un errore di rete non ferma mai l'ingestione.
- **Backfill**: `POST /api/prima-nota-salari/deposita-cedolini-in-hr` (admin,
  `?dry_run=true` per contare senza scrivere) deposita tutto il registro
  `cedolini` e ritorna `inseriti`/`gia_presenti`/`errori`/`saltati`; da shell
  `python -m app.services.hr_cedolini_deposito --dry-run`. Test:
  `tests/test_hr_cedolini_deposito.py`.

## Canali operativi e conoscenza

- Telegram è l'unico canale attivo per alert e notifiche operative.
- Non registrare router, webhook o fallback WhatsApp legacy.
- Obsidian è una proiezione consultiva della documentazione: non è un database,
  non riceve scritture contabili e non sostituisce Drive/Sheets.

## Identità, duplicati e relazioni

- Nessuna entità si associa per solo importo.
- Una relazione certa richiede identità/provenienza coerente e importo esatto
  al centesimo quando l'importo fa parte della prova.
- Nei casi ambigui mostra i candidati (`Scegli fattura`, `Scegli driver`,
  `Scegli verbale`) e non applicare il collegamento.
- Gli import sono idempotenti: stesso hash o stessa identità canonica non crea
  una seconda operazione.
- Fattura, disposizione, ricevuta, quietanza e movimento bancario sono prove
  distinte, collegate da `operation_id`, mai fuse in un solo record.
- I documenti originali restano immutabili. Conservare hash, fonte, versione,
  timestamp e log. I duplicati documentali si marcano; non si eliminano in
  modo permanente.

## Ingresso documenti e Drive

- `Documenti > Import` è l'unico ingresso manuale operativo.
- Le fatture elettroniche arrivano dal canale Drive/SDI configurato. Una
  fattura italiana trovata per email è un'anomalia, non una seconda fonte.
- Gmail/IMAP può acquisire F24, quietanze, cedolini e verbali soltanto dai
  mittenti/canali autorizzati.
- Le ricerche email complete usano `in:anywhere`, preservano message ID,
  thread ID e SHA-256 e non spostano né cancellano gli originali.
- Gli estratti conto confluiscono nell'area unica configurata; la fonte si
  determina da nome e contenuto. Se non è riconoscibile, il file va in errore
  con motivazione, mai classificato per supposizione.
- Gli ZIP vengono prima validati, deduplicati e inventariati; poi i documenti
  riconosciuti entrano nei rispettivi flussi.

## Regole contabili vincolanti

- Piano dei conti: solo CEE ufficiale in
  `app/services/piano_conti_ufficiale.py`; conversioni tramite
  `app/services/mapping_piano_conti.py`.
- Motore unico Prima Nota: `app/services/scritture_contabili.py`. Non creare
  nuovi `insert_one` diretti per scritture contabili.
- Libro giornale in partita doppia (`movimenti_contabili`): motore unico
  `app/services/registrazione_contabile.py`, alimentato **automaticamente**
  all'import di fatture (`fatture_upload`) e corrispettivi RT
  (`corrispettivi_helpers`, `CorrispettiviService`) tramite
  `registra_documento_import` (idempotente per documento con
  `idempotency_key = reg:<tipo>:<id>`, mai bloccante, esito negativo annotato
  in `registrazione_contabile_esito`). Il pregresso si recupera con
  `POST /api/piano-conti/registra-pregresso?dry_run=` (admin). Non aggiungere
  altri punti di scrittura.
- Navigazione tra contropartite: un solo componente
  `frontend/src/components/LinkContropartita.jsx` (`ROTTE_CONTROPARTITA`); i
  deep-link letti dalle pagine sono `/fatture?invoice_id=`,
  `/riconciliazione/banca?movimento=`, `/prima-nota#sezione=banca&selected=`,
  `/contabilita/verifica?conto=`, `/contabilita/giornale?conto=|scrittura=`.
- Ricavi: solo corrispettivi RT. Le fatture ricevute sono costi; gli accrediti
  POS e i payout non sono nuovi ricavi.
- POS: corrispettivo XML, chiusura terminale e accredito bancario sono tre
  fatti distinti. Numia e SumUp restano circuiti separati.
- SumUp corrente è acquisito dall'API; Numia corrente è la chiusura manuale
  serale; Numia storico è ricostruito dagli export operativi del gestore su
  Drive, deduplicati e accorpati per giorno. Tutte e tre le fonti creano
  l'attesa bancaria; l'estratto conto può soltanto riconciliarla.
- Un versamento contanti genera uscita Cassa e corrispondente entrata Banca con
  lo stesso `operation_id`; l'estratto conto riconcilia il trasferimento.
- Prima Nota Banca non è la copia dell'estratto conto: una riga entra quando è
  nota la causale contabile oppure appartiene alle categorie bancarie senza
  documento ammesse dal codice.
- F24, singole righe tributo, quietanza e movimento bancario sono entità
  distinte. La quietanza documenta il pagamento ma non sostituisce la prova
  bancaria.
- Cedolini e bonifici salario si associano per dipendente, periodo e regole
  temporali; non si richiedono importi identici quando esistono acconti o
  trattenute.
- Date mostrate all'utente: `gg/mm/aaaa`.

## PartenoPay, verbali e flotta

- Conservare email, verbale, avviso, ricevuta PagoPA/PayPal e movimento banca
  come prove separate.
- Associazione automatica driver: targa normalizzata + data/ora infrazione +
  storico assegnazioni del veicolo.
- Se targa, driver, verbale o pagamento non sono univoci, conservare il
  documento e chiedere una scelta manuale.
- Lo stato corretto dopo un pagamento privo di ricevuta ufficiale è
  `attesa quietanza`, non `attesa fattura`.
- Nessun pagamento automatico è autorizzato.

## Sicurezza

- **05/09/2026, scelta del titolare:** il PIN amministratore unico per ERP,
  Menu, Lotti e HR è quello già usato da ERP/Menu (`PIN_HASH_ADMIN` in Render).
  `app/services/admin_pin.py` è l'unica verifica; i vecchi PIN amministratore
  delle sotto-app non sono alternative. Nessuna copia o modifica degli hash
  salvati. Il modale comune è `frontend_shared/PinModal.js`, parametrizzato
  per colore. I PIN personali dei dipendenti restano distinti; non dichiarare
  completata la loro unificazione finché le identità HR/Lotti non sono verificate.

- Segreti solo nelle variabili d'ambiente/secret store di Render.
- Non stampare, committare o trasferire credenziali nei documenti.
- Non spostare né cancellare email e documenti originali.
- Eliminazioni reali, pagamenti e associazioni definitive ambigue richiedono
  conferma esplicita al momento dell'azione.

## Verifica e pubblicazione

Per ogni modifica pertinente:

1. test mirati;
2. `python -m pytest -q` quando il cambiamento backend lo richiede;
3. `yarn test` e `yarn build` in `frontend/` quando coinvolge il frontend;
4. `git diff --check`;
5. commit dei soli file pertinenti;
6. push su `main` solo quando richiesto;
7. CI verde e verifica `/api/health` sul commit pubblicato;
8. controllo live del flusso interessato senza mutare dati non autorizzati.


Regole aggiuntive per l'implementazione (da AGENTS.md, unificato qui):

- Riusa pagine, router, servizi, registri Drive/Sheets e viewer esistenti; non
  creare pipeline o archivi paralleli.
- Ogni scrittura deve essere idempotente, tracciabile e coperta da test sui casi
  positivo, nullo, ambiguo, multipagina ed errore parser.
- Prima del push controlla il diff e aggiorna l'inventario Markdown tramite
  `scripts/refresh_markdown_docs.py` quando aggiungi documentazione.
- Prima di dichiarare il lavoro live verifica test, build, CI, commit distribuito
  e comportamento reale dell'endpoint o della pagina interessata.

Un alert deve sempre mostrare l'elenco dei record coinvolti. Un comando di
manutenzione che l'utente deve ripetere per correggere duplicati prevedibili è
un difetto: la prevenzione per ID/hash deve stare nel flusso di importazione.
