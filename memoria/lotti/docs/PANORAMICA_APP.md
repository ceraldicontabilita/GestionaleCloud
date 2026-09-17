# Lotti — Gestionale HACCP relazionale di Ceraldi Group SRL

<!-- gestionalecloud-doc
status: historical
reviewed_at: 2026-09-17
storage_architecture: supabase
-->

> [!NOTE]
> Snapshot storico: non descrive lo stato operativo corrente. Per l'architettura Drive-only usare `README.md`, `PRODUCT.md`, `CLAUDE.md` e `LOGICA_FUNZIONAMENTO.md`.

### Brief professionale: cosa fa, come funziona, ambizione, punti di forza e debolezza, roadmap migliorativa

> Documento di sintesi (utilizzabile anche come prompt/brief per onboarding, audit
> o per istruire un assistente). Redatto incrociando il codice reale del repo
> `ceraldicontabilita/Lotti` (backend FastAPI, frontend React, MongoDB `Gestionale`).

---

## 1. Scopo e contesto

Lotti è il gestionale operativo di **Ceraldi Group SRL** (Napoli — pasticceria,
rosticceria, bar/banco). Nasce per coprire, in un'unica applicazione **mobile-first**
usata in laboratorio e al banco, l'intero ciclo:

**Acquisto → Magazzino → Produzione → Vendita → Tracciabilità HACCP**

Non è un semplice registro: è pensato per essere **relazionale**, cioè un dato
inserito in un punto si propaga ovunque senza riallineamenti manuali.

**Indipendenza dei dati (direzione architetturale).** A differenza di un semplice
modulo dell'ERP, Lotti viene **staccato dal database condiviso**: le fatture
elettroniche **non** vengono più sincronizzate automaticamente dalla collection
ERP, ma **importate manualmente** dai file XML (il vecchio sync è stato rimosso —
"fatture solo da import XML"). L'obiettivo è un perimetro dati proprio e
controllato, dove ogni dato entra in modo esplicito e verificabile.

## 2. Ambizione

«Far funzionare l'azienda da sola, partendo dalla fattura». L'obiettivo è che
**l'import di una fattura XML aggiorni automaticamente** giacenze, lotti,
allergeni, dizionario prodotti, anagrafica e prezzi fornitori; che la **produzione**
scali il magazzino in FIFO ed erediti gli allergeni; che le **giacenze sotto scorta**
generino riordini; il tutto alimentando i **registri HACCP** richiesti dalla
normativa. Una sola fonte di verità per ogni concetto, zero doppia digitazione.

**Decisioni d'acquisto guidate dagli incassi e dal calendario.** L'ambizione si
estende al *quando e quanto ordinare*. Una **sezione Corrispettivi dedicata**
permette al titolare di leggere ogni giorno l'andamento degli incassi; il sistema
**apprende dallo storico** per capire se l'aumento degli ordini è **giustificato
dall'aumento del venduto** e per **prevedere l'anno successivo** (se gli incassi
crescono, propone ordini via via maggiori nei periodi giusti). Inoltre incrocia il
**calendario delle festività** con le **date di consegna**: se un ponte/festivo fa
perdere giorni di consegna, l'app **ricorda che c'è la festività e propone di
anticipare un ordine maggiore**. L'ordine grosso non è più "a sensazione": è
motivato dal ricavo, dallo storico e dall'evento imminente.

## 3. Come funziona (architettura)

- **Backend**: FastAPI (prefix `/api`), ~80 router modulari, ~540 endpoint, su
  Render. Connessione MongoDB condivisa via modulo unico `db.py`. Scheduler
  (APScheduler) per job notturni (pulizia lotti, backup, normalizzazione,
  generazione HACCP, controllo scorte). Email via relay HTTPS (Google Apps
  Script, perché Render blocca SMTP).
- **Frontend**: React PWA (craco), mobile-first, design system Ceraldi
  (viola/navy/verde, font Plus Jakarta Sans). Navigazione a tab + dropdown
  raggruppati (HACCP, Altro). Card kiosk per tablet con accesso tramite **PIN**
  operatore.
- **Dati**: MongoDB `Gestionale` (157 collection, di cui ~50 di Lotti e il resto
  dell'ERP, da non toccare). Collezioni cardine: `fatture`/`invoices`,
  `lotti_fornitori` (17k lotti materie prime), `ricette`, `lotti`/`produzioni`,
  `prodotti_master` (catalogo unificato), `dizionario_prodotti`, `magazzino_*`,
  `ordini_fornitori`, registri HACCP (`temperature_*`, `sanificazione`, ecc.).

### Flussi relazionali principali
1. **Fattura XML → tutto**: per ogni riga crea/aggiorna il lotto fornitore,
   carica il magazzino, aggiorna allergeni, dizionario, anagrafica e prezzi
   (idempotente per numero fattura; prezzi "canonici" solo da acquisto reale).
2. **Ricetta → Produzione → Magazzino**: l'operatore sceglie ricetta e quantità
   sul tablet; il sistema scala le materie prime in **FIFO per data fattura**,
   crea il lotto di produzione con tracciabilità (operatore, lotti consumati,
   **allergeni ereditati**) e alimenta i registri HACCP.
3. **Catalogo unificato**: `prodotti_master` aggrega 6 fonti (fatture, listini,
   canonici, vendita, bar, acquaviva) in un solo catalogo.
4. **Scorte → Riordini → Ordini fornitori**: prodotti sotto soglia generano
   bozze d'ordine per fornitore; invio via WhatsApp o PDF email; "ricevuto"
   ricarica il magazzino.

## 4. Punti di forza

- **Visione relazionale concreta**: i flussi sopra esistono davvero nel codice
  (es. consumo FIFO in produzione, aggregazione magazzino per nome normalizzato,
  catalogo che aggrega 6 fonti). È il vero valore competitivo.
- **Aderenza al dominio reale**: regole pensate sul campo (es. "miglior prezzo =
  quello davvero pagato in fattura", conversioni uovo/tuorlo/albume, q.b.→grammi,
  normalizzazione unità di misura eterogenee delle fatture).
- **Architettura sana di base**: connessione DB centralizzata, router modulari,
  design system condiviso, scheduler con catch-up dei job mancati.
- **Mobile-first operativo**: accesso a PIN, card kiosk per laboratorio/banco,
  lavagna richieste — adatto all'uso reale senza PC.
- **HACCP integrato**: i registri non sono separati ma alimentati dalle
  operazioni, riducendo la compliance manuale.

## 5. Punti deboli

- **Frammentazione storica**: molte iterazioni hanno lasciato sistemi che
  *sembrano* paralleli (più pagine/route per la stessa area). Spesso non sono
  doppioni di dati ma di **interfaccia** → dispersione cognitiva.
- **Dipendenza dalla qualità del dato sorgente**: nomi prodotto e unità di misura
  delle fatture sono eterogenei; la normalizzazione (`prodotto_nome_norm`,
  dizionario, alias) è il punto critico su cui regge tutta la relazionalità.
  Se il match sbaglia, FIFO e prezzi ne risentono.
- **Assenza (finora) di automazioni di qualità**: nessun CI; bug come un import
  circolare o un job scheduler mai pianificato sono passati inosservati fino a
  un'ispezione manuale. *(Risolto in questa sessione con CI + fix.)*
- **Curva di scoperta**: tante funzioni utili sono "nascoste" in dropdown o
  raggiungibili solo via hash; un nuovo utente fatica a trovare i percorsi.
- **Verifica end-to-end difficile**: i test sono d'integrazione (richiedono
  backend live), quindi non girano in CI; la rete dell'ambiente di sviluppo non
  raggiunge sempre Atlas.
- **Acquisti non ancora correlati al ricavo**: oggi i riordini guardano solo le
  scorte; manca il legame con i **corrispettivi** (incassi) e con il **calendario
  festività**. L'app sa *cosa manca*, non ancora *se conviene/serve ordinarlo ora*.
- **Transizione all'indipendenza dei dati**: lo "stacco" dal DB ERP e il passaggio
  a import XML manuale eliminano l'auto-sync ma spostano sull'operatore la
  responsabilità dell'inserimento: serve un import a prova di errore (idempotente,
  con riscontro chiaro di cosa è entrato).

## 6. Considerazioni migliorative — lavoro più snello e interattivo

### A. Snellezza operativa
1. **Wizard relazionali espliciti**: trasformare le catene §3 in percorsi guidati
   ("Arrivata merce → conferma ricezione → carica magazzino → verifica scorte")
   con un solo flusso a step, invece di pagine separate.
2. **Home operativa per ruolo**: una dashboard che mostra *solo le azioni di oggi*
   (lotti in scadenza, scorte sotto soglia, produzioni pianificate, ordini da
   validare) con call-to-action dirette.
3. **Consolidamento UI continuo**: proseguire il raggruppamento per area (già
   fatto per "Prodotti & Listini") riducendo le voci di menu a poche, chiare.
4. **Qualità del dato assistita**: pannello che evidenzia prodotti non
   normalizzati/non classificati con suggerimenti 1-click (il motore canonico
   esiste già: renderlo proattivo).

### B. Interattività
5. **Ricerca universale**: una barra unica ("trova prodotto, lotto, fornitore,
   ricetta") con risultati cliccabili che portano al contesto giusto.
6. **Notifiche operative push** (PWA): scorte sotto soglia, lotti in scadenza,
   ordini da validare — già c'è il digest WhatsApp, estenderlo in-app.
7. **Feedback immediato sulle azioni**: ogni scarico/produzione/ordine mostra in
   tempo reale l'effetto a valle (es. "scaricati 3 lotti FIFO → nuova giacenza X,
   sotto scorta: genero bozza ordine?").
8. **Scansione codici**: lettura barcode/QR da fotocamera del tablet per
   carico/scarico e identificazione lotto, eliminando la digitazione.

### C. Decisioni d'acquisto intelligenti (incassi + calendario)

9. **Sezione "Corrispettivi" dedicata** (NON un widget accanto ai riordini): una
   pagina propria dove il titolare guarda **ogni giorno l'andamento degli incassi**
   — grafico giornaliero/settimanale/mensile, confronto con lo stesso periodo
   dell'anno precedente, media mobile. È lo strumento di lettura del ricavo, fine
   a sé stante.

10. **Correlazione incassi ↔ ordini (giustificazione)**: il sistema valuta se
    **l'aumento degli ordini è giustificato dall'aumento dell'incasso**. Se la
    spesa cresce ma i corrispettivi no, lo segnala; se gli incassi salgono in modo
    stabile, riconosce che ordini più grandi sono coerenti.

11. **Apprendimento dello storico (previsione anno successivo)**: il sistema
    **impara dallo storico** degli incassi e degli ordini per **anticipare l'anno
    dopo**. Se gli incassi crescono di anno in anno, propone in automatico ordini
    via via maggiori nei periodi corrispondenti, senza aspettare che l'operatore se
    ne accorga.

12. **Festività e "ponti" → compra di più, in anticipo**: l'app conosce il
    **calendario delle festività** (nazionali, locali napoletane, mobili come
    Pasqua) e ragiona sulle **date di consegna**. Esempio concreto: per il **2
    giugno**, se la consegna cadrebbe a cavallo di un **ponte/giorno festivo**
    (niente consegne), l'app **ricorda al titolare che c'è la festività e propone
    di anticipare un ordine maggiore**, così non ci si trova scoperti. La logica
    combina: festività imminente + giorni di consegna persi + storico dei picchi di
    quel periodo.

13. **Import XML manuale a prova d'errore**: drag-and-drop dei file, anteprima
    delle righe che verranno scritte (lotti, prezzi, allergeni), rilevamento
    duplicati per numero fattura, riscontro finale di cosa è entrato — coerente
    con lo stacco dal DB ERP.

### D. Affidabilità (abilita tutto il resto)
14. **CI + hook di avvio** (introdotti): mantenerli e aggiungere test unitari che
    non richiedano backend live (logica FIFO, normalizzazione, conversioni,
    correlazione corrispettivi↔ordini).
15. **Decisioni di consolidamento data-driven**: prima di unificare sistemi
    paralleli, misurare sull'uso reale (quali collection/flussi sono attivi) per
    non rimuovere ciò che serve.

---

## 7. In una frase

Lotti vuole essere il "sistema nervoso" della pasticceria Ceraldi: dalla fattura
(importata in proprio) al banco, ogni dato si muove da solo e lascia traccia
HACCP. La base relazionale c'è ed è solida; il prossimo salto è renderla **più
guidata, più interattiva e più affidabile** — e soprattutto **correlare gli
acquisti agli incassi e al calendario delle festività**, così ogni ordine è
giustificato dal venduto e anticipa i picchi, riducendo frammentazione e
digitazione manuale.
