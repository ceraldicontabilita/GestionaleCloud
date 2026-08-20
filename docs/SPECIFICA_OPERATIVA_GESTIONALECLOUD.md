# Specifica operativa canonica di GestionaleCloud

<!-- gestionalecloud-doc
status: historical
reviewed_at: 2026-08-20
storage_architecture: drive-only
-->

> [!NOTE]
> Snapshot storico: non descrive lo stato operativo corrente. Per l'architettura Drive-only usare `README.md`, `PRODUCT.md`, `CLAUDE.md` e `LOGICA_FUNZIONAMENTO.md`.

Ultimo riallineamento: 6 agosto 2026

Repository canonico: `https://github.com/ceraldicontabilita/GestionaleCloud`

Branch autorevole: `main`

Baseline verificata durante questa riscrittura: `19ee1832`

Catalogo delle schermate: [`page_catalog.json`](../page_catalog.json)
Registro di collaudo: [`COLLAUDO_PAGINE_E2E_2026-08-05.md`](COLLAUDO_PAGINE_E2E_2026-08-05.md)

## 1. Scopo e autorità

Questo documento definisce le regole operative, contabili e tecniche di GestionaleCloud. In caso di contrasto prevalgono, nell'ordine:

1. documenti e movimenti originali autorizzati;
2. stato corrente del database e delle integrazioni;
3. codice e test del branch `main` del repository canonico;
4. questa specifica;
5. audit e documentazione storica.

Un risultato storico non sostituisce mai una verifica sul codice e sui dati correnti. `GestionaleCloud-Private`, ZIP, bundle scaricati e vecchi cloni sono soltanto evidenze storiche, salvo richiesta esplicita.

## 2. Obiettivo del prodotto

GestionaleCloud deve trasformare documenti e movimenti reali in un quadro amministrativo italiano ordinato, verificabile e utile al confronto con il commercialista.

Il sistema deve:

- conservare l'originale e la provenienza di ogni dato;
- evitare duplicazioni tra documenti, fatti economici, pagamenti e scritture;
- collegare fatture, fornitori, scadenze, strumenti di pagamento e movimenti reali;
- distinguere dato dichiarato, fatto economico, disposizione, pagamento e riconciliazione;
- automatizzare soltanto operazioni idempotenti, motivate e reversibili;
- lasciare sospesi i casi ambigui;
- mostrare cosa manca per completare ogni relazione.

Non deve creare una contabilità immaginaria per far quadrare i numeri.

## 3. Stato corrente e linguaggio di collaudo

L'applicazione possiede 63 schermate funzionali distinte e una pagina tecnica 404. Redirect, alias e varianti con anno o mese non sono pagine aggiuntive.

Alla data di questa riscrittura il catalogo macchina registra:

- 5 pagine `verified`;
- 15 pagine `in_review`;
- 43 pagine `unverified`.

Il precedente test isolato aveva aperto 62/62 schermate senza 404, ErrorBoundary o errori API iniziali, ma non includeva Dati ISA. Il catalogo corrente contiene 65 schermate, comprese Dati ISA, Atti amministrativi e Situazione fiscale, e richiede l'apertura di tutte le voci presenti nel catalogo. Anche un passaggio completo dimostra il montaggio tecnico, non la correttezza contabile.

### 3.1 Definizioni obbligatorie

- **Raggiungibile**: route React e componente esistono.
- **Caricabile**: la pagina completa il caricamento iniziale senza errore.
- **Testata**: esistono test automatici pertinenti e verdi.
- **In revisione**: un difetto è stato riprodotto o una parte della logica è stata verificata, ma restano prove mancanti.
- **Verificata**: route, endpoint, dati, relazioni, casi limite, contatori e deploy sono stati controllati end-to-end.

Non usare “funzionante”, “completata” o “verificata” come sinonimo di HTTP 200.

### 3.2 Prova minima per chiudere una pagina

Una pagina può passare a `verified` solo quando risultano provati:

1. route canonica, componente e navigazione;
2. endpoint effettivamente montati e contratti frontend/backend coerenti;
3. filtro dell'anno globale e del periodo;
4. stati loading, empty, error e permission denied;
5. comportamento desktop e mobile;
6. calcoli e contatori ricostruibili dalle righe sorgente;
7. idempotenza e protezione dai duplicati;
8. relazioni bidirezionali con le altre entità;
9. casi ambigui lasciati sospesi;
10. test mirati, suite completa e build;
11. CI verde, merge in `main` e commit effettivamente servito dal deploy;
12. collaudo live in sola lettura con dati reali, quando autorizzato e necessario.

Il browser verifica rendering e interazione. Codice, endpoint, test, database e provenienza verificano la logica.

## 4. Regole assolute sui dati

### 4.1 Fonti e provenienza

Ogni valore derivato deve conservare, quando disponibile:

- identificativo del documento o movimento;
- hash del contenuto;
- cartella, email o canale di origine;
- pagina, foglio o riga;
- valore originale e valore normalizzato;
- parser e versione;
- data del job;
- livello di confidenza;
- regola, agente o operatore responsabile della decisione.

### 4.2 Entità che non devono essere confuse

- Il **documento** prova cosa è stato ricevuto.
- La **fattura** crea un costo o ricavo, un debito o credito e una scadenza.
- La **rata XML** indica un piano, non un pagamento.
- La **disposizione** prova l'ordine di pagamento, non l'esecuzione.
- L'**assegno emesso** prova l'emissione, non l'addebito bancario.
- Il **movimento di estratto conto** prova l'addebito o accredito effettivo.
- La **quietanza** prova l'esito dichiarato dall'ente o intermediario competente.
- La **riconciliazione** è la relazione motivata tra evidenze compatibili.
- La **Prima Nota** è una registrazione contabile e non deve duplicare la fonte finanziaria.

### 4.3 Deduplicazione

- Il solo importo non è mai una chiave sufficiente.
- Il filename non identifica il contenuto.
- L'hash identifica il documento, non sempre il fatto economico.
- La chiave naturale usa gli identificatori disponibili: soggetto fiscale, numero documento, data, conto, riferimento, valuta, importo con segno e descrizione normalizzata.
- Lo stesso file ricaricato non deve creare un nuovo fatto.
- La stessa riga bancaria non può essere usata due volte, salvo allocazione esplicita e tracciata.
- Copie identiche in cartelle diverse possono essere evidenze legittime del ciclo di vita: non vanno cancellate automaticamente.

### 4.4 Certezza

- **Certo**: identità, importo e relazione sono univoci e supportati da fonti compatibili.
- **Probabile**: esiste una proposta forte ma manca almeno una prova o sono presenti alternative.
- **Dubbio**: conflitto, dato mancante o più candidati equivalenti.

Solo il livello certo può essere candidato all'automazione. Una scrittura contabile o una modifica di dati reali richiede comunque il livello di autorizzazione previsto dal dominio.

## 5. Autonomia, sicurezza e modifiche reali

Il lavoro tecnico può procedere autonomamente su codice, test, branch, PR, CI e deploy quando le verifiche sono verdi e il rollback è disponibile.

Per dati aziendali reali:

- le letture e le anteprime sono consentite nel perimetro autorizzato;
- le associazioni certe possono essere proposte;
- scritture, fusioni, cancellazioni, spostamenti Drive e riconciliazioni definitive devono avere anteprima, bersaglio esatto, motivazione, conferma prevista e verifica successiva;
- le operazioni ambigue non si applicano;
- le operazioni distruttive globali sono vietate;
- password, token, hash di autenticazione e contenuti sensibili non entrano in chat, log, commit o report.

Ogni modifica deve registrare prima/dopo, autore, data, fonte, motivo e possibilità di annullamento quando applicabile.

## 6. Anno globale, periodo e UX

L'anno globale è un filtro obbligatorio per dashboard, fatture, corrispettivi, Prima Nota, riconciliazioni, assegni, F24, cedolini, verbali, IVA, scadenze e report.

Ogni pagina deve:

- mostrare anno e periodo attivi;
- propagare il cambio anno a KPI, tabella, filtri ed export;
- separare chiaramente “nessun dato” da “errore di caricamento”;
- rendere leggibili le tabelle come schede su schermi stretti;
- mantenere comandi pochi, chiari e coerenti;
- spiegare fonte, stato e azione successiva;
- non lasciare KPI con un anno e righe con un altro.

## 7. Grafo relazionale canonico

La catena operativa minima è:

```text
Documento originale
  -> entità canonica (fattura, F24, cedolino, verbale, estratto)
  -> soggetto (fornitore, cliente, dipendente, ente)
  -> obbligazione o scadenza
  -> strumento/disposizione (assegno, bonifico, PayPal, carta, PagoPA)
  -> movimento finanziario reale
  -> allocazioni
  -> riconciliazione
  -> Prima Nota e report contabili
```

Le relazioni devono essere bidirezionali. Un collegamento presente soltanto da un lato è incompleto e deve generare un controllo.

Le allocazioni sono molti-a-molti:

- un pagamento può coprire più fatture;
- una fattura può essere coperta da più pagamenti;
- la somma allocata non può superare pagamento o residuo, salvo rettifica esplicita;
- ogni quota conserva il documento e il movimento che la giustificano.

## 8. Documenti, Drive ed email

`/documenti/import` è l'unico ingresso operativo. Le altre pagine consultano o lavorano le entità prodotte dalla pipeline; non devono creare pipeline parallele.

Ordine obbligatorio:

1. ricezione e hash;
2. rilevamento del formato reale tramite contenuto;
3. classificazione;
4. estrazione in anteprima;
5. normalizzazione;
6. ricerca duplicati documento, evidenza ed entità;
7. proposta di associazione;
8. conferma o stato `da_verificare`;
9. creazione o aggiornamento idempotente;
10. eventuale registrazione contabile dopo i controlli.

Le cartelle Drive configurate restano fonti autorizzate. Non si eliminano documenti senza certezza del duplicato, prova di conservazione e conferma specifica.

Le email vengono analizzate soltanto dai mittenti attendibili configurati. Tra i mittenti richiesti figurano lo studio Marotta e `noreply.enelenergia@enel.com`. Un allegato rilevante deve essere classificato, conservato nell'app e copiato nella cartella Drive corretta; se manca la cartella, il sistema propone una categoria comprensibile senza creare strutture arbitrarie.

## 9. Fatture, fornitori e scadenze

### 9.1 Fatture

Per ogni fattura conservare:

- P.IVA/CF e denominazione delle parti;
- numero, data, tipo documento e SdI quando presente;
- righe, quantità, prezzi, sconti, imponibile, aliquota, natura e IVA;
- bollo, ritenute, cassa previdenziale, split payment e arrotondamenti;
- condizioni, metodo dichiarato e tutte le rate XML;
- documento XML/PDF e provenienza.

Il fornitore si identifica principalmente tramite P.IVA/CF. Il nome è un supporto, non la chiave definitiva.

Una fattura importata:

- crea il debito e le scadenze;
- non crea automaticamente un pagamento;
- può essere classificata riga per riga su più conti e centri di costo;
- diventa pagata solo quando allocazioni reali uniche coprono il dovuto;
- conserva residuo esatto, pagamenti parziali, anticipi e note di credito.

### 9.2 Regola stretta fattura-pagamento

L'associazione certa privilegia:

1. identità fiscale del fornitore;
2. numero fattura normalizzato presente nella causale o nel documento di pagamento;
3. importo esatto al centesimo o somma esatta di allocazioni dichiarate;
4. compatibilità di data, scadenza e metodo;
5. riferimento bancario o dello strumento.

Numero fattura e importo al centesimo sono la coppia operativa richiesta; senza identità del soggetto o con più candidati la relazione resta una proposta.

### 9.3 Scadenze

Ogni rata è una riga distinta con importo, data, fonte, residuo e stato. “Scaduta” non significa “non pagata” senza controllo delle evidenze. L'IVA operativa vive nella pagina unica `/iva`; `/scadenze` mostra obblighi e documenti ancora aperti.

## 10. Banca, cassa e Prima Nota

### 10.1 Banca

`estratto_conto_movimenti` è la fonte dei movimenti reali. Ogni riga conserva fingerprint, data, importo con segno, conto, saldo, descrizione e riferimento originali.

La pagina `/strumenti/movimenti-banca` deve diagnosticare e proporre. Non deve creare una seconda riga di Prima Nota quando la stessa operazione è già rappresentata.

### 10.2 Cassa

La cassa contiene soltanto operazioni realmente avvenute in contanti o scritture interne chiaramente dichiarate. Un movimento elettronico o XML non diventa cassa per inferenza.

### 10.3 Provvisori

Una fattura con pagamento non dimostrato resta provvisoria e mostra la prova mancante. I comandi Cassa, Banca e Parziale devono aggiornare immediatamente stato e contatore soltanto dopo un'operazione valida e idempotente.

La banca definitiva non nasce premendo un pulsante: nasce dal movimento reale o da una scrittura esplicitamente distinta e autorizzata.

## 11. Assegni

La pagina canonica è `/riconciliazione/assegni`. Deve distinguere carnet, emissione, documento, proposta fattura, addebito bancario, storno e sostituzione.

### 11.1 Carnet

- banca/conto, serie, primo e ultimo numero, data apertura e stato;
- generazione idempotente con controllo di numeri esistenti;
- zeri iniziali sempre conservati;
- numeri mancanti, duplicati e fuori sequenza segnalati;
- creazione rapida e risposta immediata, senza timeout silenziosi.

### 11.2 Emissione

Conservare numero, data, importo al centesimo, beneficiario, causale, conto, fattura/rata proposta, foto fronte/retro o PDF e allegati.

Un assegno emesso entra in `emesso_in_attesa_banca`; non genera un movimento bancario fittizio.

### 11.3 Collegamento assegno-fattura

Ordine delle evidenze:

1. numero fattura o rata;
2. P.IVA/CF e beneficiario/fornitore;
3. importo o somma esatti;
4. residuo e scadenza;
5. data, causale e documento dell'assegno.

Sono ammesse soltanto come proposte visibili:

- L1: un assegno per una fattura;
- L2: più assegni uguali per rate della stessa fattura;
- L3: più assegni diversi che coprono esattamente il residuo;
- L4: un assegno ripartito su più fatture dello stesso fornitore.

Pareggi, più combinazioni e importo senza fattura/soggetto restano ambigui.

### 11.4 Collegamento assegno-banca

La prova principale è numero assegno normalizzato più importo esatto e conto compatibile. Data e causale supportano la relazione. Se il numero manca, il sistema può soltanto proporre.

Dopo la conferma di una riga bancaria certa:

- collega assegno, movimento e fattura/rata in entrambe le direzioni;
- riusa la riga importata, senza crearne una seconda;
- aggiorna il residuo al centesimo;
- conserva la provenienza provvisoria come storico;
- impedisce il riuso della riga bancaria.

### 11.5 Annullamenti e storni

Un assegno riconciliato non si elimina. Annullamento, revoca, insoluto, storno e sostituzione sono eventi tracciati. Uno storno riapre solo la quota realmente riaccreditata.

## 12. Bonifici e PayPal

Bonifici a dipendenti non devono proporre fatture. Bonifici a fornitori non devono proporre salari. La classificazione del soggetto precede l'elenco dei candidati.

PayPal mantiene distinti:

- transazione;
- conversione valuta;
- commissione;
- fornitore;
- fattura;
- addebito bancario.

Il mapping del nome PayPal è sempre da confermare salvo identità fiscale certa. La riconciliazione PayPal-banca usa match biunivoci, importo EUR esatto, segno, data e/o riferimento; un pareggio resta sospeso. La fattura richiede numero, importo e fornitore compatibili.

## 13. Carte Nexi

Supportare PDF, XLS/XLSX e OOXML con estensione errata attraverso i parser e servizi esistenti. La stessa transazione presente in più statement produce un fatto con più evidenze.

Spesa, commissione, rimborso e addebito mensile sono entità distinte. La quadratura del ciclo usa il netto; non ricrea le singole spese in banca.

La cartella unica documentale deve rendere trovabili gli statement mancanti per periodo e collegarli agli addebiti già presenti, senza duplicare gli alert.

## 14. Corrispettivi e POS

Tre fonti diverse:

- XML RT: ricavo e IVA dichiarati;
- chiusura terminale: POS reale del giorno;
- estratto conto: accredito bancario effettivo.

Fase 1: confronto XML-POS.

Fase 2: confronto POS-banca.

Una chiusura manuale non prova l'accredito. Un accredito non modifica l'XML. Commissioni, DCC, rimborsi e storni restano separati.

Il calendario deve distinguere giorni operativi, festività, chiusure dichiarate, XML mancante, POS mancante, in transito e accredito mancante. L'assenza di un file non dimostra che l'attività fosse chiusa.

## 15. F24, IVA e ritenute

### 15.1 F24 multi-tributo

Un modello F24 è composto da righe tributo. Conservare sezione, codice, rateazione, anno/periodo, debito, credito e importo di ogni riga.

Un pagamento può coprire:

- l'intero saldo del modello;
- una combinazione esatta di righe;
- una sola riga tributo.

Il sistema deve allocare le righe coperte e lasciare aperto il residuo. Non deve perdere i tributi non pagati perché la banca contiene un importo inferiore al totale.

Ravvedimento, sanzioni e interessi sono righe distinte collegate all'obbligo originario.

### 15.2 IVA mensile

`/iva` è l'unica pagina operativa IVA. Deve unire:

- attribuzione e classificazione IVA delle fatture;
- liquidazione mensile versionata;
- confronto con l'F24 ricevuto dal commercialista;
- scadenze e stato documentale.

Non deve ripristinare una logica IVA trimestrale se l'impresa opera mensilmente.

L'importo IVA comunicato dal commercialista arriva dal modello F24 acquisito da mittente attendibile. Per il confronto gestionale non è obbligatorio trovarlo in banca. Lo stato “pagato” richiede invece la prova prevista, distinta dal confronto.

L'IVA a credito usa soltanto `iva_detraibile` esplicitamente classificata. L'IVA esposta non è automaticamente detraibile.

### 15.3 Ritenute

Ritenuta professionista, pagamento della fattura e versamento F24 sono tre relazioni distinte. Un F24 può contenere codice 1040 insieme ad altri tributi; l'associazione avviene a livello di riga, non soltanto sul totale.

## 16. Cedolini, dipendenti e salari

Il perimetro operativo dei cedolini parte dal 2018.

Per ogni documento conservare dipendente, CF/matricola, periodo, tipo, netto residuo, acconti, TFR, rettifiche e fonte.

```text
Totale spettante = netto residuo stampato + acconti espliciti
Saldo = totale spettante - pagamenti effettivi unici collegati
```

Più documenti dello stesso dipendente e mese possono essere legittimi. Non deduplicare soltanto per dipendente-mese.

Un bonifico paga un cedolino soltanto con identità non ambigua, importo/allocazioni e periodo coerenti. L'eccedenza resta acconto tracciato e non scompare.

## 17. Verbali, PagoPA e noleggio

Verbale, avviso PagoPA, ricevuta, fattura di noleggio, conducente e pagamento sono entità diverse.

Il conducente si determina dallo storico del veicolo alla data dell'infrazione. Un verbale non genera automaticamente una trattenuta al dipendente.

Documenti provenienti da mittenti attendibili devono essere classificati, collegati al veicolo e conservati in app e Drive. Il pagamento usa la ricevuta e/o il movimento reale; una fattura non si associa a un dipendente.

Canone, manutenzione, carburante, verbali e servizi devono restare costi separati. Percentuali fiscali di deducibilità e detraibilità sono profili da confermare, non valori inventati.

## 18. Contabilità, bilancio e cespiti

Una fattura definitiva deve essere leggibile in quattro prospettive:

1. documento e soggetto;
2. conto economico e centro di costo;
3. stato patrimoniale e debito/credito;
4. tesoreria e movimento che chiude il residuo.

Il pagamento non ricrea il costo: chiude il debito e muove banca/cassa.

Libro giornale e mastri usano scritture definitive, non proposte. Le scritture protocollate si rettificano con storico.

Un bene strumentale richiede classificazione, valore, entrata in funzione, vita utile, aliquota e metodo confermati. Più cespiti nella stessa fattura restano distinti.

## 19. Energia e dati gestionali ISA

Le bollette Enel Energia provenienti dal mittente attendibile vengono classificate mensilmente e collegate a periodo, POD, kWh, fasce F1/F2/F3, costi e documento.

Dashboard e sezione ISA possono mostrare consumi e indicatori gestionali, ma devono distinguere:

- dati estratti dalle bollette;
- calcoli interni;
- parametri ufficiali dell'Agenzia delle Entrate;
- previsioni o suggerimenti produttivi.

Orari e regole delle fasce devono provenire dal contratto o da fonti ufficiali aggiornate. I suggerimenti su quando produrre non modificano la contabilità.

## 20. Ricerca web e software open source

La ricerca esterna serve a migliorare UX, controlli e architettura, non a sostituire le regole aziendali.

Regole:

- usare documentazione ufficiale, repository originali e standard primari;
- verificare licenza, versione e data;
- confrontare almeno modello dati, idempotenza, audit, permessi e workflow;
- adattare i pattern al codice esistente invece di creare un secondo sistema;
- non copiare codice con licenza incompatibile;
- non introdurre funzioni soltanto perché presenti in un altro ERP;
- documentare fonte, decisione e differenze.

ERPNext, Odoo Community, Dolibarr e altri progetti possono essere studiati come riferimenti, ma il modello canonico resta quello di GestionaleCloud.

## 21. Regole di sviluppo

Prima di implementare:

1. aggiornare `origin/main` e verificare il clone canonico;
2. leggere route, endpoint, servizi, collezioni, indici e test già presenti;
3. riprodurre il difetto con una prova minima;
4. cercare chiamanti e flussi concorrenti;
5. preferire estensione e consolidamento;
6. scrivere il test che impedisce la regressione.

Non introdurre:

- una seconda pagina operativa per lo stesso processo;
- una seconda collezione senza migrazione motivata;
- endpoint duplicati;
- import circolari;
- scritture automatiche nascoste;
- timeout più lunghi come unica soluzione a query inefficienti.

Le query devono essere indicizzate, paginabili e limitate. I contatori devono derivare dalla stessa fonte delle righe mostrate.

## 22. Gate di qualità e pubblicazione

Per ogni correzione:

1. test mirati;
2. suite backend completa;
3. suite frontend completa;
4. build di produzione;
5. pulizia di `frontend/dist` e altri artefatti generati;
6. `git diff --check` e revisione del diff;
7. commit isolato su branch `codex/*`;
8. PR con prove e rischi residui;
9. CI verde;
10. merge in `main`;
11. verifica che `/api/health` esponga il commit atteso;
12. controllo del bundle e collaudo live in sola lettura;
13. aggiornamento di `page_catalog.json` e del registro soltanto quando le prove giustificano il nuovo stato.

Non dichiarare pubblicata una correzione presente soltanto in locale o in una PR non mergiata.

## 23. Report operativo obbligatorio

Ogni chiusura di attività deve indicare:

- esito concreto;
- anno e periodo;
- modulo e pagina;
- fonti controllate;
- relazioni trovate;
- duplicati, esclusioni e ambiguità;
- modifiche effettuate;
- test eseguiti;
- commit, PR e deploy, se presenti;
- dati reali modificati oppure conferma “sola lettura”;
- rischi residui e prossimo blocco.

Le affermazioni devono avere lo stesso perimetro delle prove. Un test unitario non dimostra l'intera pagina; 63 aperture non dimostrano 63 processi contabili corretti.

## 24. Ordine corrente del collaudo

L'obiettivo resta verificare tutte le pagine una per una. L'ordine operativo corrente è:

1. pagina 9 — Prima Nota: Cassa, Banca, Provvisori, Soci e anti-duplicato;
2. pagine 33-38 — riconciliazione banca, F24, stipendi, documenti e bonifici;
3. pagine 12-14 e 53 — noleggio, verbali e PagoPA;
4. pagine 31, 32 e 61 — scadenze, ritenute e IVA unica;
5. pagine 3-8 — dashboard, fatture, corrispettivi e fornitori;
6. restanti pagine `unverified` secondo dipendenze e rischio.

PayPal resta `in_review` finché fatture, fornitori e movimenti reali non risultano completamente collegati senza ambiguità.

## 25. Comando di ripresa

> Riprendi GestionaleCloud dal repository canonico e da `main`. Leggi questa specifica, `page_catalog.json` e il registro di collaudo. Verifica lo stato corrente prima di fidarti di audit storici. Continua dalla prima pagina non chiusa, riproduci gli errori nel codice e nei dati in sola lettura, correggi senza duplicare moduli, esegui tutti i gate, pubblica e aggiorna lo stato soltanto dopo il deploy verificato.
